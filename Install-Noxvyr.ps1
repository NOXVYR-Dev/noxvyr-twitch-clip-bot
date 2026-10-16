$ErrorActionPreference = 'Stop'
$Source = $PSScriptRoot
$InstallDir = Join-Path $env:LOCALAPPDATA 'Programs\Noxvyr Clip Bot'

function Find-PythonLauncher {
    $cmd = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

$Launcher = Find-PythonLauncher
if ($Launcher) {
    & $Launcher -3.12 --version *> $null
    if ($LASTEXITCODE -ne 0) {
        & $Launcher install 3.12
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 konnte nicht installiert werden. Installiere Python 3.12 von python.org und starte das Setup erneut.' }
    }
} else {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) {
        Start-Process 'https://www.python.org/downloads/windows/'
        throw 'Python bzw. der Python-Installationsmanager fehlt. Die offizielle Python-Downloadseite wurde geöffnet. Installiere Python 3.12 und starte Install-Noxvyr.cmd erneut.'
    }
    & $winget.Source install --exact --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements --silent
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 konnte über winget nicht installiert werden.' }
    $UserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $MachinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $env:Path = "$UserPath;$MachinePath"
    $Launcher = Find-PythonLauncher
}

if (-not (Test-Path -LiteralPath $InstallDir)) { New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null }
Get-ChildItem -LiteralPath $Source -Force | Where-Object { $_.Name -notin @('.env', '.venv', 'data', '__pycache__') } | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $InstallDir -Recurse -Force
}
$EnvFile = Join-Path $InstallDir '.env'
if (-not (Test-Path -LiteralPath $EnvFile)) { Copy-Item (Join-Path $InstallDir '.env.example') $EnvFile }
$DbDir = Join-Path $InstallDir 'data'
New-Item -ItemType Directory -Path $DbDir -Force | Out-Null

$Py = Get-Command python.exe -ErrorAction SilentlyContinue
if ($Launcher) {
    & $Launcher -3.12 -m venv (Join-Path $InstallDir '.venv')
} elseif ($Py) {
    & $Py.Source -m venv (Join-Path $InstallDir '.venv')
} else {
    throw 'Python wurde installiert, ist aber noch nicht auffindbar. Bitte melde dich einmal ab und wieder an und starte das Setup erneut.'
}
$VenvPython = Join-Path $InstallDir '.venv\Scripts\python.exe'
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $InstallDir 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Bot-Abhängigkeiten konnten nicht installiert werden.' }

$ShortcutPath = Join-Path ([Environment]::GetFolderPath('Programs')) 'Noxvyr Clip Bot.lnk'
$Wsh = New-Object -ComObject WScript.Shell
$Shortcut = $Wsh.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = 'wscript.exe'
$Shortcut.Arguments = '"' + (Join-Path $InstallDir 'Launch-Manager.vbs') + '"'
$Shortcut.WorkingDirectory = $InstallDir
$Shortcut.Description = 'Noxvyr Clip Bot verwalten'
$Shortcut.Save()

Write-Host 'Noxvyr Clip Bot wurde installiert.' -ForegroundColor Green
Write-Host 'Starte die App über das Startmenü: Noxvyr Clip Bot.'
Start-Process $ShortcutPath
