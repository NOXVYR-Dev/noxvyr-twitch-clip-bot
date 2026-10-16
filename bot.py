#!/usr/bin/env python3
"""Multi-server Discord bot that forwards new Twitch clips to configured channels."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import discord
from discord import app_commands
from discord.ext import commands, tasks


def load_env_file(path: Path = Path(".env")) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_env_file()

TWITCH_API = "https://api.twitch.tv/helix"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
POLL_SECONDS = max(30, int(os.getenv("POLL_SECONDS", "60")))
OVERLAP_SECONDS = max(300, int(os.getenv("OVERLAP_SECONDS", "900")))
DB_PATH = Path(os.getenv("DB_PATH", str(Path(__file__).resolve().parent / "data" / "bot.sqlite3")))
LOG = logging.getLogger("twitch-clip-discord-bot")


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Die Einstellung {name} fehlt in der .env-Datei.")
    return value


def http_json(url: str, *, headers: dict[str, str] | None = None,
              body: dict | None = None, form: dict[str, str] | None = None) -> dict:
    data = None
    request_headers = {"Accept": "application/json", **(headers or {})}
    if form is not None:
        data = urlencode(form).encode("utf-8")
        request_headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    method = "POST" if data is not None else "GET"
    request = Request(url, data=data, headers=request_headers, method=method)
    with urlopen(request, timeout=20) as response:
        raw = response.read()
        return json.loads(raw) if raw else {}


def normalize_twitch_login(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^https?://(www\.)?twitch\.tv/", "", value, flags=re.IGNORECASE)
    value = value.lstrip("@/").split("/", 1)[0].split("?", 1)[0].lower()
    if not re.fullmatch(r"[a-z0-9_]{1,25}", value):
        raise ValueError("Bitte gib einen gültigen Twitch-Namen oder Twitch-Kanal-Link ein.")
    return value


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class TwitchClient:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = ""

    async def _new_token(self) -> None:
        form = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        }
        token_data = await asyncio.to_thread(http_json, TWITCH_TOKEN_URL, form=form)
        self.access_token = token_data["access_token"]

    async def get(self, path: str, params: dict[str, str]) -> dict:
        if not self.access_token:
            await self._new_token()
        url = f"{TWITCH_API}/{path}?{urlencode(params)}"
        headers = {
            "Client-Id": self.client_id,
            "Authorization": f"Bearer {self.access_token}",
        }
        try:
            return await asyncio.to_thread(http_json, url, headers=headers)
        except HTTPError as error:
            if error.code != 401:
                raise
            self.access_token = ""
            await self._new_token()
            headers["Authorization"] = f"Bearer {self.access_token}"
            return await asyncio.to_thread(http_json, url, headers=headers)

    async def broadcaster(self, login: str) -> dict | None:
        result = await self.get("users", {"login": login})
        users = result.get("data", [])
        return users[0] if users else None

    async def clips(self, broadcaster_id: str, started_at: datetime,
                    ended_at: datetime) -> list[dict]:
        clips: list[dict] = []
        cursor = ""
        while True:
            params = {
                "broadcaster_id": broadcaster_id,
                "started_at": iso_utc(started_at),
                "ended_at": iso_utc(ended_at),
                "first": "100",
            }
            if cursor:
                params["after"] = cursor
            result = await self.get("clips", params)
            clips.extend(result.get("data", []))
            cursor = result.get("pagination", {}).get("cursor", "")
            if not cursor:
                return clips


class ClipBot(commands.Bot):
    def __init__(self, twitch: TwitchClient | None = None):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.twitch = twitch
        self.db: sqlite3.Connection | None = None

    async def setup_hook(self) -> None:
        if self.twitch is None:
            self.twitch = TwitchClient(required_env("TWITCH_CLIENT_ID"), required_env("TWITCH_CLIENT_SECRET"))
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(DB_PATH)
        self.db.row_factory = sqlite3.Row
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL,
                twitch_login TEXT NOT NULL,
                broadcaster_id TEXT NOT NULL,
                broadcaster_name TEXT NOT NULL,
                last_checked TEXT NOT NULL
            )
        """)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS sent_clips (
                guild_id TEXT NOT NULL,
                clip_id TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, clip_id)
            )
        """)
        self.db.commit()
        await self.tree.sync()
        if not self.clip_poll.is_running():
            self.clip_poll.start()

    async def on_ready(self) -> None:
        LOG.info("Bot verbunden als %s; bereit für Clip-Abfragen.", self.user)

    async def close(self) -> None:
        if self.db is not None:
            self.db.close()
        await super().close()

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        if self.db is not None:
            self.db.execute("DELETE FROM guild_config WHERE guild_id = ?", (str(guild.id),))
            self.db.execute("DELETE FROM sent_clips WHERE guild_id = ?", (str(guild.id),))
            self.db.commit()

    @tasks.loop(seconds=POLL_SECONDS)
    async def clip_poll(self) -> None:
        if self.db is None:
            return
        configs = self.db.execute("SELECT * FROM guild_config").fetchall()
        for config in configs:
            try:
                await self.poll_guild(config)
            except Exception:
                LOG.exception("Clip-Prüfung für Server %s fehlgeschlagen.", config["guild_id"])

    @clip_poll.before_loop
    async def before_clip_poll(self) -> None:
        await self.wait_until_ready()

    async def poll_guild(self, config: sqlite3.Row) -> None:
        now = datetime.now(timezone.utc)
        last_checked = parse_time(config["last_checked"])
        start = max(last_checked - timedelta(seconds=OVERLAP_SECONDS), now - timedelta(days=7))
        clips = await self.twitch.clips(config["broadcaster_id"], start, now)
        clips.sort(key=lambda clip: clip.get("created_at", ""))
        guild = self.get_guild(int(config["guild_id"]))
        channel = guild.get_channel(int(config["channel_id"])) if guild else None

        for clip in clips:
            clip_id = clip.get("id")
            if not clip_id:
                continue
            exists = self.db.execute(
                "SELECT 1 FROM sent_clips WHERE guild_id = ? AND clip_id = ?",
                (config["guild_id"], clip_id),
            ).fetchone()
            if exists:
                continue
            if channel is None:
                LOG.warning("Zielkanal fehlt auf Discord-Server %s; Einrichtung nötig.", config["guild_id"])
                return
            title = str(clip.get("title") or "Clip")[:180]
            creator = str(clip.get("creator_name") or "Unbekannt")[:80]
            clip_url = clip.get("url") or f"https://clips.twitch.tv/{clip_id}"
            try:
                await channel.send(
                    f"🎬 **{discord.utils.escape_markdown(title)}** — Clip von **{discord.utils.escape_markdown(creator)}**\n{clip_url}",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except (discord.Forbidden, discord.HTTPException):
                LOG.exception("Clip konnte nicht in Server %s gesendet werden.", config["guild_id"])
                return
            self.db.execute(
                "INSERT OR IGNORE INTO sent_clips(guild_id, clip_id, sent_at) VALUES (?, ?, ?)",
                (config["guild_id"], clip_id, iso_utc(now)),
            )
            self.db.commit()

        self.db.execute(
            "UPDATE guild_config SET last_checked = ? WHERE guild_id = ?",
            (iso_utc(now), config["guild_id"]),
        )
        self.db.execute("DELETE FROM sent_clips WHERE sent_at < ?", (iso_utc(now - timedelta(days=90)),))
        self.db.commit()


bot = ClipBot()


@bot.tree.command(name="clip-setup", description="Neue Twitch-Clips in einen Kanal dieses Servers posten")
@app_commands.describe(
    twitch_channel="Twitch-Name oder Link zum Twitch-Kanal",
    zielkanal="Discord-Kanal, in den neue Clips gepostet werden",
)
@app_commands.checks.has_permissions(manage_guild=True)
async def clip_setup(interaction: discord.Interaction, twitch_channel: str,
                     zielkanal: discord.TextChannel) -> None:
    if interaction.guild_id is None or bot.db is None:
        await interaction.response.send_message("Dieser Befehl funktioniert nur auf einem Discord-Server.", ephemeral=True)
        return
    try:
        login = normalize_twitch_login(twitch_channel)
    except ValueError as error:
        await interaction.response.send_message(str(error), ephemeral=True)
        return
    bot_member = interaction.guild.me if interaction.guild else None
    if bot_member is None or not zielkanal.permissions_for(bot_member).send_messages:
        await interaction.response.send_message("Im gewählten Kanal darf ich keine Nachrichten senden.", ephemeral=True)
        return
    try:
        assert bot.twitch is not None
        broadcaster = await bot.twitch.broadcaster(login)
    except (HTTPError, URLError, TimeoutError):
        LOG.exception("Twitch-Kanal konnte nicht geprüft werden.")
        await interaction.response.send_message("Twitch ist gerade nicht erreichbar. Bitte versuche es gleich erneut.", ephemeral=True)
        return
    if broadcaster is None:
        await interaction.response.send_message("Diesen Twitch-Kanal habe ich nicht gefunden. Bitte prüfe den Namen.", ephemeral=True)
        return

    now = iso_utc(datetime.now(timezone.utc))
    bot.db.execute("""
        INSERT INTO guild_config(guild_id, channel_id, twitch_login, broadcaster_id, broadcaster_name, last_checked)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            channel_id=excluded.channel_id,
            twitch_login=excluded.twitch_login,
            broadcaster_id=excluded.broadcaster_id,
            broadcaster_name=excluded.broadcaster_name,
            last_checked=excluded.last_checked
    """, (str(interaction.guild_id), str(zielkanal.id), login,
          broadcaster["id"], broadcaster["display_name"], now))
    bot.db.commit()
    await interaction.response.send_message(
        f"Eingerichtet: Neue Clips von **{broadcaster['display_name']}** werden ab jetzt in {zielkanal.mention} gepostet. Ältere Clips werden übersprungen.",
        ephemeral=True,
    )


@bot.tree.command(name="clip-status", description="Zeigt die Clip-Einrichtung dieses Servers")
async def clip_status(interaction: discord.Interaction) -> None:
    config = bot.db.execute("SELECT * FROM guild_config WHERE guild_id = ?", (str(interaction.guild_id),)).fetchone() if bot.db and interaction.guild_id else None
    if config is None:
        await interaction.response.send_message("Noch nicht eingerichtet. Nutze `/clip-setup`.", ephemeral=True)
        return
    channel = f"<#{config['channel_id']}>"
    await interaction.response.send_message(
        f"Aktiv: **{config['broadcaster_name']}** → {channel}", ephemeral=True
    )


@bot.tree.command(name="clip-remove", description="Deaktiviert Clip-Meldungen für diesen Server")
@app_commands.checks.has_permissions(manage_guild=True)
async def clip_remove(interaction: discord.Interaction) -> None:
    if bot.db is not None and interaction.guild_id is not None:
        bot.db.execute("DELETE FROM guild_config WHERE guild_id = ?", (str(interaction.guild_id),))
        bot.db.execute("DELETE FROM sent_clips WHERE guild_id = ?", (str(interaction.guild_id),))
        bot.db.commit()
    await interaction.response.send_message("Clip-Meldungen wurden für diesen Server deaktiviert.", ephemeral=True)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    if isinstance(error, app_commands.MissingPermissions):
        message = "Diesen Befehl darf nur ein Server-Admin mit der Berechtigung **Server verwalten** nutzen."
    else:
        LOG.error("Slash-Befehl fehlgeschlagen: %s", error, exc_info=error)
        message = "Der Befehl ist fehlgeschlagen. Bitte versuche es erneut."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        bot.run(required_env("DISCORD_BOT_TOKEN"))
    except (RuntimeError, KeyError) as error:
        LOG.error("%s", error)
        sys.exit(1)
