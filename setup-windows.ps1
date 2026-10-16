$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

$PythonLauncher = Get-Command 'py.exe' -ErrorAction SilentlyContinue
if (-not $PythonLauncher) {
    throw 'Python 3.12 fehlt. Installiere Python 3.12 von python.org und aktiviere beim Setup „Python Launcher“, danach starte dieses Skript erneut.'
}

& $PythonLauncher.Source -3.12 --version
if ($LASTEXITCODE -ne 0) {
    throw 'Python 3.12 wurde nicht gefunden. Installiere Python 3.12 von python.org und starte dieses Skript erneut.'
}

$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $VenvPython)) {
    & $PythonLauncher.Source -3.12 -m venv (Join-Path $ProjectRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Die Python-Umgebung konnte nicht angelegt werden.' }
}

& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip konnte nicht aktualisiert werden.' }
& $VenvPython -m pip install -r (Join-Path $ProjectRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Die Bot-Abhängigkeiten konnten nicht installiert werden.' }

$DataPath = Join-Path $ProjectRoot 'data'
New-Item -ItemType Directory -Path $DataPath -Force | Out-Null

$EnvPath = Join-Path $ProjectRoot '.env'
if (-not (Test-Path -LiteralPath $EnvPath)) {
    Copy-Item -LiteralPath (Join-Path $ProjectRoot '.env.example') -Destination $EnvPath
    Write-Host 'Die lokale .env-Datei wurde angelegt.'
}

Write-Host ''
Write-Host 'Einrichtung abgeschlossen.'
Write-Host 'Trage DISCORD_BOT_TOKEN, TWITCH_CLIENT_ID und TWITCH_CLIENT_SECRET in die .env-Datei ein.'
Write-Host 'Danach kannst du start-bot.cmd ausführen. Die Schlüssel nicht in GitHub veröffentlichen oder im Chat senden.'
