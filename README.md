# Twitch Clip Discord Bot

Ein gemeinsam gehosteter Discord-Bot, den Freunde auf ihren eigenen Discord-Server einladen können. Jeder Server richtet selbst den Twitch-Kanal und den Discord-Zielkanal ein. Der Betreiber hostet den Bot dauerhaft und verwahrt dessen Zugangsdaten zentral.

## Was der Bot macht

- `/clip-setup twitch_channel zielkanal`: richtet den Server ein; nur Personen mit **Server verwalten** dürfen das.
- `/clip-status`: zeigt die Einrichtung.
- `/clip-remove`: schaltet Meldungen für den Server aus; ebenfalls nur für Server-Admins.
- Vorhandene Clips werden beim Einrichten übersprungen. Neue Links werden in den eingestellten Kanal gesendet.
- Die Einrichtung je Discord-Server und bereits veröffentlichte Clips bleiben in SQLite gespeichert.

Der Bot fragt Twitch im Abstand von standardmäßig 60 Sekunden ab und gleicht überlappende Zeitfenster ab. Twitch kann neue Clips mit einer Verzögerung auffindbar machen, daher ist die Zustellung nicht augenblicklich. Der Bot liest keine Chatnachrichten und braucht keinen Twitch-Chat-Zugriff. Er nutzt Twitchs [Get Clips API](https://dev.twitch.tv/docs/api/reference#get-clips).

## Discord-Bot einmalig anlegen

1. In [Discord Developer Portal](https://discord.com/developers/applications) eine Anwendung erstellen.
2. Unter **General Information** den Anwendungsnamen auf `Noxvyr` und das gewünschte App-Icon setzen. Discord verwendet Name und Icon als globale Marke der App und ihres Bot-Benutzers.
3. Unter **Bot** den Benutzernamen prüfen beziehungsweise auf `Noxvyr` setzen und das Bot-Token geheim auf dem eigenen Server speichern.
4. Den Bot als öffentlich einladbar konfigurieren, wenn Freunde ihn hinzufügen sollen.
5. Unter **OAuth2 → URL Generator** die Scopes `bot` und `applications.commands` wählen.
6. Nur die Berechtigungen **View Channels** und **Send Messages** setzen. Nachrichteninhalt-Intent, Adminrechte und Lesezugriff auf Nachrichten sind nicht nötig.
7. Den erzeugten Einladungslink an Freunde weitergeben. Beim Einladen braucht die Person auf ihrem Server die Berechtigung **Server verwalten**.

Die Slash-Befehle werden vom Bot beim Start registriert. Discord-Anwendungsbefehle benötigen den `applications.commands`-Scope und sind pro Server verfügbar, sobald die App eingeladen wurde. Mehr dazu in der [Discord-Dokumentation zu Anwendungsbefehlen](https://discord.com/developers/docs/interactions/slash-commands) und [OAuth2-Einladungen](https://discord.com/developers/docs/topics/oauth2).

## Windows-Anwendung installieren

1. `Noxvyr-Clip-Bot-Setup-Windows.zip` auf dem Server entpacken.
2. `Install-Noxvyr.cmd` starten. Das Setup richtet Python 3.12 ein (über den Python Install Manager oder winget, falls verfügbar), erstellt eine isolierte Bot-Umgebung und legt eine Startmenü-Verknüpfung an.
3. In der App Discord-Bot-Token, Twitch Client-ID und Twitch Client-Secret eintragen und speichern. Die Werte bleiben in `.env` im lokalen Installationsordner.
4. Mit „Bot starten“ starten. Die App zeigt Laufstatus und Meldungen an; „Bot stoppen“ beendet den Prozess.
5. „Beim Windows-Anmelden automatisch starten“ aktivieren, wenn die App nach der Anmeldung des Serverkontos automatisch starten und den Bot hochfahren soll. Nach einem Windows-Neustart muss sich das Serverkonto anmelden. Für Betrieb schon vor der Anmeldung wäre eine separat eingerichtete Windows-Aufgabe erforderlich.

Die App prüft alle fünf Minuten GitHub-Releases unter `NOXVYR-Dev/noxvyr-twitch-clip-bot`. Sobald eine neuere Version verfügbar ist, erscheint der Update-Knopf. Ein Klick lädt das Update herunter, hält den Bot kurz an, aktualisiert Dateien und Python-Abhängigkeiten und startet den Bot wieder, wenn er vorher lief. Zugangsdaten und Datenbank bleiben erhalten. GitHub Actions erstellt für jede neue Versionsnummer in `version.json` automatisch ein Release; für Bot-Updates muss diese Versionsnummer erhöht werden. Die Bot-Datenbank liegt unter `data/bot.sqlite3` im App-Installationsordner.

Die vorherige manuelle Installation mit `setup-windows.ps1` und `start-bot.cmd` ist weiterhin möglich.

## Betrieb mit Docker

1. Eine Twitch-Anwendung in der [Twitch Developer Console](https://dev.twitch.tv/console/apps) anlegen und Client-ID sowie Client-Secret bereithalten.
2. `.env.example` nach `.env` kopieren und `DISCORD_BOT_TOKEN`, `TWITCH_CLIENT_ID` sowie `TWITCH_CLIENT_SECRET` eintragen. Diese Datei niemals veröffentlichen oder in GitHub einchecken.
3. Mit installiertem Docker Compose im Projektordner starten:

   ```sh
   docker compose up -d --build
   ```

   Logs ansehen:

   ```sh
   docker compose logs -f
   ```

   Anhalten:

   ```sh
   docker compose down
   ```

Die Datenbank liegt im Ordner `data/` und bleibt bei Container-Neustarts erhalten. Die Discord- und Twitch-Schlüssel gehören nur auf den eigenen Host; Freunde benötigen keine Tokens.

## Vor öffentlicher Einladung

Die Discord- und Twitch-Anwendungen sind angelegt. Der Bot wurde noch nicht gestartet oder auf einem Discord-Server eingerichtet. Vor dem Verteilen des Einladungslinks muss der Bot auf dem Server laufen und der Einladungslink mit den Scopes `bot` und `applications.commands` sowie den Berechtigungen **View Channels** und **Send Messages** erstellt werden.
