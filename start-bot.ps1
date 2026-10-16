$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

$EnvPath = Join-Path $ProjectRoot '.env'
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $EnvPath)) {
    throw 'Die .env-Datei fehlt. Führe zuerst setup-windows.ps1 aus.'
}
if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw 'Python-Abhängigkeiten fehlen. Führe zuerst setup-windows.ps1 aus.'
}

$Configured = @{}
foreach ($Line in Get-Content -LiteralPath $EnvPath) {
    if ($Line -match '^\s*(DISCORD_BOT_TOKEN|TWITCH_CLIENT_ID|TWITCH_CLIENT_SECRET)\s*=(.*)$') {
        $Configured[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
    }
}
$Missing = @('DISCORD_BOT_TOKEN', 'TWITCH_CLIENT_ID', 'TWITCH_CLIENT_SECRET') |
    Where-Object { -not $Configured.ContainsKey($_) -or [string]::IsNullOrWhiteSpace($Configured[$_]) }
if ($Missing.Count -gt 0) {
    throw ('Fülle zuerst diese Werte in .env aus: ' + ($Missing -join ', '))
}

while ($true) {
    & $VenvPython (Join-Path $ProjectRoot 'bot.py')
    $ExitCode = $LASTEXITCODE
    if ($ExitCode -eq 0) { break }
    Write-Warning "Der Bot wurde mit Fehlercode $ExitCode beendet. Neuer Startversuch in 15 Sekunden."
    Start-Sleep -Seconds 15
}
