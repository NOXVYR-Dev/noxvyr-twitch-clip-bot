from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
import urllib.error
import zipfile
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

APP_NAME = "Noxvyr Clip Bot"
APP_VERSION = "0.1.0"
GITHUB_REPO = "NOXVYR-Dev/noxvyr-twitch-clip-bot"
RELEASE_ASSET = "noxvyr-twitch-clip-bot-windows.zip"
ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
VERSION_FILE = ROOT / "version.json"
BOT_FILES = ("bot.py", "requirements.txt", "version.json")


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def safe_write_env(values: dict[str, str]) -> None:
    lines = [
        "# Noxvyr Clip Bot settings. Keep this file private.",
        f"DISCORD_BOT_TOKEN={values.get('DISCORD_BOT_TOKEN', '').strip()}",
        f"TWITCH_CLIENT_ID={values.get('TWITCH_CLIENT_ID', '').strip()}",
        f"TWITCH_CLIENT_SECRET={values.get('TWITCH_CLIENT_SECRET', '').strip()}",
        "POLL_SECONDS=60",
        "OVERLAP_SECONDS=900",
    ]
    tmp = ENV_FILE.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, ENV_FILE)
    try:
        os.chmod(ENV_FILE, 0o600)
    except OSError:
        pass


class Manager:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME}  ·  Verwaltung")
        self.root.geometry("850x720")
        self.root.minsize(760, 620)
        self.root.configure(bg="#15171c")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.proc: subprocess.Popen[str] | None = None
        self.stopping = False
        self.update_checking = False
        self.update_installing = False
        self.restart_after_update = False
        self.pending_update: dict[str, str] | None = None
        self.messages: queue.Queue[tuple[str, str]] = queue.Queue()
        self.reader: threading.Thread | None = None
        self.auto_start = tk.BooleanVar(value=self.startup_enabled())
        self.status = tk.StringVar(value="Bot gestoppt")
        self.update_status = tk.StringVar(value=f"Installierte Bot-Version: {self.bot_version()}")
        self.fields: dict[str, tk.Entry] = {}
        self._build_ui()
        self._load_fields()
        self.root.after(200, self._poll_messages)
        self.root.after(1200, self.check_updates)
        self.root.after(300000, self._check_updates_periodically)
        if "--autostart" in sys.argv:
            self.root.after(700, self.start_bot)
        if "--minimized" in sys.argv:
            self.root.after(100, self.root.iconify)

    def _build_ui(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#15171c")
        style.configure("Card.TFrame", background="#20232b")
        style.configure("TLabel", background="#20232b", foreground="#eceef4", font=("Segoe UI", 10))
        style.configure("Title.TLabel", background="#15171c", foreground="white", font=("Segoe UI Semibold", 20))
        style.configure("Sub.TLabel", background="#15171c", foreground="#aab0bf", font=("Segoe UI", 10))
        style.configure("Status.TLabel", background="#20232b", foreground="#8ce99a", font=("Segoe UI Semibold", 11))
        style.configure("TButton", font=("Segoe UI Semibold", 10), padding=(12, 8))
        style.configure("Accent.TButton", background="#7c5cff", foreground="white")
        style.map("Accent.TButton", background=[("active", "#927bff")])
        style.configure("TCheckbutton", background="#20232b", foreground="#eceef4", font=("Segoe UI", 10))
        style.map("TCheckbutton", background=[("active", "#20232b")])

        outer = ttk.Frame(self.root, padding=22)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Noxvyr Clip Bot", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="Einrichtung und Laufzeitstatus für deinen Windows-Server", style="Sub.TLabel").pack(anchor="w", pady=(3, 18))

        card = ttk.Frame(outer, style="Card.TFrame", padding=18)
        card.pack(fill="x")
        ttk.Label(card, text="Zugangsdaten", font=("Segoe UI Semibold", 12)).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        self._field(card, 1, "Discord-Bot-Token", "DISCORD_BOT_TOKEN", True)
        self._field(card, 2, "Twitch Client-ID", "TWITCH_CLIENT_ID", False)
        self._field(card, 3, "Twitch Client-Secret", "TWITCH_CLIENT_SECRET", True)
        ttk.Label(card, text="Die Zugangsdaten bleiben lokal auf diesem Server.", foreground="#aab0bf").grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 2))
        ttk.Button(card, text="Einstellungen speichern", command=self.save_config).grid(row=5, column=1, sticky="e", pady=(10, 0))
        card.columnconfigure(1, weight=1)

        run = ttk.Frame(outer, style="Card.TFrame", padding=18)
        run.pack(fill="x", pady=(14, 0))
        ttk.Label(run, text="Bot-Steuerung", font=("Segoe UI Semibold", 12)).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        ttk.Label(run, textvariable=self.status, style="Status.TLabel").grid(row=1, column=0, sticky="w")
        self.start_button = ttk.Button(run, text="Bot starten", style="Accent.TButton", command=self.start_bot)
        self.start_button.grid(row=1, column=1, padx=(10, 6))
        self.stop_button = ttk.Button(run, text="Bot stoppen", command=self.stop_bot, state="disabled")
        self.stop_button.grid(row=1, column=2)
        ttk.Checkbutton(run, text="Beim Windows-Anmelden automatisch starten", variable=self.auto_start, command=self.toggle_startup).grid(row=2, column=0, columnspan=3, sticky="w", pady=(13, 0))
        run.columnconfigure(0, weight=1)

        upd = ttk.Frame(outer, style="Card.TFrame", padding=18)
        upd.pack(fill="x", pady=(14, 0))
        ttk.Label(upd, text="Updates", font=("Segoe UI Semibold", 12)).grid(row=0, column=0, sticky="w")
        ttk.Label(upd, textvariable=self.update_status, foreground="#aab0bf").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.update_button = ttk.Button(upd, text="Update installieren", style="Accent.TButton", command=self.install_pending_update)
        self.update_button.grid(row=0, column=1, rowspan=2, padx=(12, 0))
        self.update_button.grid_remove()
        upd.columnconfigure(0, weight=1)

        log_frame = ttk.Frame(outer, style="Card.TFrame", padding=14)
        log_frame.pack(fill="both", expand=True, pady=(14, 0))
        ttk.Label(log_frame, text="Statusmeldungen", font=("Segoe UI Semibold", 12)).pack(anchor="w", pady=(0, 8))
        self.log = tk.Text(log_frame, height=10, wrap="word", bg="#111318", fg="#d5d8e0", insertbackground="white", relief="flat", font=("Consolas", 9), state="disabled")
        self.log.pack(fill="both", expand=True)
        self._log("Bereit. Trage die Discord- und Twitch-Zugangsdaten ein und starte den Bot.")

    def _field(self, parent: ttk.Frame, row: int, label: str, key: str, secret: bool) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 14), pady=5)
        entry = tk.Entry(parent, show="•" if secret else "", bg="#111318", fg="white", insertbackground="white", relief="flat", font=("Segoe UI", 10))
        entry.grid(row=row, column=1, sticky="ew", pady=5, ipady=7, padx=2)
        self.fields[key] = entry

    def _load_fields(self) -> None:
        for key, value in read_env().items():
            if key in self.fields and value:
                self.fields[key].insert(0, value)

    def _get_values(self) -> dict[str, str]:
        return {key: widget.get().strip() for key, widget in self.fields.items()}

    def save_config(self, quiet: bool = False) -> bool:
        values = self._get_values()
        missing = [key for key in ("DISCORD_BOT_TOKEN", "TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET") if not values.get(key)]
        if missing:
            if not quiet:
                messagebox.showwarning("Einstellungen fehlen", "Bitte alle drei Zugangsdaten ausfüllen.")
            return False
        safe_write_env(values)
        self._log("Einstellungen lokal gespeichert.")
        if not quiet:
            messagebox.showinfo("Gespeichert", "Die Einstellungen wurden lokal gespeichert.")
        return True

    def start_bot(self) -> None:
        if self.proc and self.proc.poll() is None:
            return
        if not self.save_config(quiet=True):
            messagebox.showwarning("Einstellungen fehlen", "Bitte fülle zuerst Discord-Token, Twitch Client-ID und Client-Secret aus und speichere sie.")
            return
        self.stopping = False
        python = ROOT / ".venv" / "Scripts" / "python.exe"
        if not python.exists():
            messagebox.showerror("Installation unvollständig", "Die Bot-Umgebung fehlt. Bitte starte Install-Noxvyr.cmd erneut.")
            return
        self.proc = subprocess.Popen([str(python), str(ROOT / "bot.py")], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.reader = threading.Thread(target=self._read_output, args=(self.proc,), daemon=True)
        self.reader.start()
        self.status.set("Bot startet …")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self._log("Bot-Prozess gestartet.")
        self.root.after(900, self._check_process)

    def _read_output(self, proc: subprocess.Popen[str]) -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            clean = line.rstrip()
            # Do not allow a misconfigured library to echo the saved credentials into the UI log.
            for secret in self._get_values().values():
                if secret:
                    clean = clean.replace(secret, "[ausgeblendet]")
            self.messages.put(("log", clean))
            low = clean.lower()
            if "logged in as" in low or "bot is ready" in low or "bot ist bereit" in low or "bot verbunden als" in low:
                self.messages.put(("status", "Bot verbunden"))
            elif "401 unauthorized" in low or "improper token" in low or "loginfailure" in low:
                self.messages.put(("status", "Discord-Anmeldung fehlgeschlagen – Token prüfen"))
        code = proc.wait()
        self.messages.put(("exit", str(code)))

    def _check_process(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.root.after(900, self._check_process)

    def stop_bot(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.stopping = True
            self.proc.terminate()
            self._log("Bot wird beendet …")

    def _poll_messages(self) -> None:
        while True:
            try:
                kind, value = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind.startswith("update"):
                self._handle_update_message(kind, value)
            elif kind == "log":
                self._log(value)
            elif kind == "status":
                self.status.set(value)
            elif kind == "exit":
                self.status.set("Bot gestoppt" if value == "0" else f"Bot beendet (Fehler {value})")
                self.start_button.configure(state="normal")
                self.stop_button.configure(state="disabled")
                self._log(f"Bot-Prozess beendet (Exit-Code {value}).")
                if value != "0" and not self.stopping:
                    self.status.set("Neustart in 15 Sekunden …")
                    self.start_button.configure(state="disabled")
                    self.root.after(15000, self.start_bot)
            elif kind == "restart-after-update-error":
                self.root.after(500, self.start_bot)
        self.root.after(200, self._poll_messages)

    def _log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def bot_version(self) -> str:
        try:
            return str(json.loads(VERSION_FILE.read_text(encoding="utf-8")).get("version", "unbekannt"))
        except Exception:
            return "0.1.0"

    def check_updates(self) -> None:
        if self.update_checking or self.update_installing:
            return
        self.update_checking = True
        self.update_button.configure(state="disabled")
        self.update_status.set("Suche nach einer neuen Version …")
        threading.Thread(target=self._check_updates_worker, daemon=True).start()

    def _check_updates_periodically(self) -> None:
        self.check_updates()
        self.root.after(300000, self._check_updates_periodically)

    def _check_updates_worker(self) -> None:
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "Noxvyr-Clip-Bot-Manager"})
            with urllib.request.urlopen(req, timeout=20) as response:
                release = json.loads(response.read().decode("utf-8"))
            asset = next((item for item in release.get("assets", []) if item.get("name") == RELEASE_ASSET), None)
            if not asset:
                raise RuntimeError("Im neuesten GitHub-Release fehlt das Windows-Updatepaket.")
            remote = release.get("tag_name", "unbekannt").lstrip("v")
            current = self.bot_version().lstrip("v")
            remote_key = tuple(int(part) for part in re.findall(r"\d+", remote))
            current_key = tuple(int(part) for part in re.findall(r"\d+", current))
            if remote_key <= current_key:
                self.messages.put(("update-current", f"Version {current} ist aktuell."))
                return
            self.messages.put(("update-ready", json.dumps({"url": asset["browser_download_url"], "version": remote})))
        except Exception as exc:
            if isinstance(exc, urllib.error.HTTPError) and exc.code == 404:
                self.messages.put(("release-missing", "Noch kein GitHub-Release veröffentlicht."))
            else:
                self.messages.put(("update-check-error", str(exc)))

    def _handle_update_message(self, kind: str, value: str) -> None:
        if kind == "update-current":
            self.update_checking = False
            self.update_button.configure(state="normal")
            self.update_button.grid_remove()
            self.update_status.set(value)
        elif kind == "update-progress":
            self.update_status.set(value)
        elif kind == "update-error":
            self.update_checking = False
            self.update_installing = False
            self.update_button.configure(state="normal")
            self.update_button.grid_remove()
            self.update_status.set("Update fehlgeschlagen")
            self._log(value)
            messagebox.showerror("Update-Prüfung", value)
        elif kind == "update-check-error":
            self.update_checking = False
            self.update_button.configure(state="normal")
            self.update_button.grid_remove()
            self.update_status.set("Update-Prüfung fehlgeschlagen; neuer Versuch in fünf Minuten.")
            self._log("Update-Prüfung: " + value)
        elif kind == "release-missing":
            self.update_checking = False
            self.update_button.configure(state="normal")
            self.update_button.grid_remove()
            self.update_status.set(value)
        elif kind == "update-ready":
            self.update_checking = False
            payload = json.loads(value)
            self.pending_update = payload
            self.update_button.configure(state="normal", text="Jetzt aktualisieren")
            self.update_button.grid()
            self.update_status.set(f"Neue Version verfügbar: {payload['version']}")
        elif kind == "update-done":
            self.update_installing = False
            self.pending_update = None
            self.update_button.configure(state="normal", text="Jetzt aktualisieren")
            self.update_button.grid_remove()
            self.update_status.set(value)
            if self.restart_after_update:
                self.root.after(500, self.start_bot)

    def install_pending_update(self) -> None:
        if not self.pending_update or self.update_installing:
            return
        payload = self.pending_update
        self.restart_after_update = bool(self.proc and self.proc.poll() is None)
        self.update_installing = True
        self.update_button.configure(state="disabled", text="Installiere …")
        self.update_status.set(f"Version {payload['version']} wird installiert …")
        threading.Thread(target=self._apply_update, args=(payload["url"], payload["version"], self.restart_after_update), daemon=True).start()

    def _apply_update(self, url: str, version: str, restart_after: bool) -> None:
        backup_dir = ROOT / ".update-backup"
        changed: list[str] = []
        try:
            if self.proc and self.proc.poll() is None:
                self.stopping = True
                self.proc.terminate()
                self.proc.wait(timeout=15)
            self.messages.put(("update-progress", "Update wird heruntergeladen und installiert …"))
            with tempfile.TemporaryDirectory(prefix="noxvyr-update-") as temp:
                archive = Path(temp) / "update.zip"
                req = urllib.request.Request(url, headers={"User-Agent": "Noxvyr-Clip-Bot-Manager"})
                with urllib.request.urlopen(req, timeout=60) as response, archive.open("wb") as out:
                    shutil.copyfileobj(response, out)
                extract = Path(temp) / "unpacked"
                extract.mkdir()
                with zipfile.ZipFile(archive) as zf:
                    for member in zf.infolist():
                        path = Path(member.filename)
                        if path.is_absolute() or ".." in path.parts:
                            raise RuntimeError("Das Updatepaket enthält einen ungültigen Dateipfad.")
                    zf.extractall(extract)
                candidates = [extract / name for name in BOT_FILES]
                if not all(candidate.is_file() for candidate in candidates):
                    nested = next((child for child in extract.iterdir() if child.is_dir() and all((child / name).is_file() for name in BOT_FILES)), None)
                    if nested:
                        extract = nested
                    else:
                        raise RuntimeError("Das Updatepaket ist unvollständig.")
                if backup_dir.exists():
                    shutil.rmtree(backup_dir)
                backup_dir.mkdir()
                for name in BOT_FILES:
                    src = extract / name
                    dst = ROOT / name
                    if dst.exists():
                        shutil.copy2(dst, backup_dir / name)
                    tmp = dst.with_suffix(dst.suffix + ".new")
                    shutil.copy2(src, tmp)
                    os.replace(tmp, dst)
                    changed.append(name)
            pip = ROOT / ".venv" / "Scripts" / "python.exe"
            subprocess.run([str(pip), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], cwd=ROOT, check=True, capture_output=True, text=True, timeout=300)
            shutil.rmtree(backup_dir, ignore_errors=True)
            new_version = self.bot_version()
            if restart_after:
                self.messages.put(("update-done", f"Update auf Version {new_version} abgeschlossen. Bot wird neu gestartet."))
            else:
                self.messages.put(("update-done", f"Update auf Version {new_version} abgeschlossen."))
        except Exception as exc:
            for name in reversed(changed):
                backup = backup_dir / name
                destination = ROOT / name
                if backup.exists():
                    shutil.copy2(backup, destination)
            shutil.rmtree(backup_dir, ignore_errors=True)
            self.messages.put(("update-error", f"Update fehlgeschlagen: {exc}"))
            if restart_after:
                self.messages.put(("restart-after-update-error", "Bot nach fehlgeschlagenem Update wieder starten."))

    def startup_path(self) -> Path:
        appdata = Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming")))
        return appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "Noxvyr Clip Bot.lnk"

    def startup_enabled(self) -> bool:
        return self.startup_path().exists()

    def toggle_startup(self) -> None:
        link = self.startup_path()
        if self.auto_start.get():
            try:
                link.parent.mkdir(parents=True, exist_ok=True)
                vbs = (ROOT / "create-shortcut.vbs").read_text(encoding="utf-8")
                vbs = vbs.replace("__TARGET__", str(ROOT / "Launch-Manager.vbs")).replace("__LINK__", str(link)).replace("__WORKING__", str(ROOT))
                temp_vbs = Path(tempfile.gettempdir()) / "noxvyr-startup-shortcut.vbs"
                temp_vbs.write_text(vbs, encoding="utf-8")
                subprocess.run(["wscript.exe", str(temp_vbs)], check=True, capture_output=True)
                self._log("Autostart bei der Windows-Anmeldung aktiviert.")
            except Exception as exc:
                self.auto_start.set(False)
                messagebox.showerror("Autostart", f"Autostart konnte nicht eingerichtet werden: {exc}")
        else:
            try:
                link.unlink(missing_ok=True)
                self._log("Autostart deaktiviert.")
            except OSError as exc:
                messagebox.showerror("Autostart", str(exc))

    def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno("Bot läuft", "Der Bot läuft noch. Beim Schließen wird er gestoppt. Fortfahren?"):
                return
            self.stop_bot()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    Manager().run()
