$ErrorActionPreference = 'Stop'
$Source = $PSScriptRoot
$InstallDir = Join-Path $env:LOCALAPPDATA 'Programs\Noxvyr Clip Bot'

function Find-PythonLauncher {
    $cmd = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Test-Python312([string]$Launcher) {
    $previousNativePreference = $PSNativeCommandUseErrorActionPreference
    try {
        if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
            $PSNativeCommandUseErrorActionPreference = $false
        }
        if ($Launcher) {
            try {
                & $Launcher -3.12 --version *> $null
                if ($LASTEXITCODE -eq 0) { return $true }
            } catch { }
        }
        $Python = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($Python) {
            try {
                $VersionOutput = & $Python.Source --version 2>$null
                return ($LASTEXITCODE -eq 0 -and $VersionOutput -match '^Python 3\.12(\.|$)')
            } catch { return $false }
        }
        return $false
    } finally {
        if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
            $PSNativeCommandUseErrorActionPreference = $previousNativePreference
        }
    }
}

$Launcher = Find-PythonLauncher
if (-not (Test-Python312 $Launcher)) {
    $InstalledByPythonManager = $false
    if ($Launcher) {
        try {
            $previousNativePreference = $PSNativeCommandUseErrorActionPreference
            if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
                $PSNativeCommandUseErrorActionPreference = $false
            }
            & $Launcher install 3.12 *> $null
            $InstalledByPythonManager = ($LASTEXITCODE -eq 0) -and (Test-Python312 $Launcher)
        } catch {
            $InstalledByPythonManager = $false
        } finally {
            if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
                $PSNativeCommandUseErrorActionPreference = $previousNativePreference
            }
        }
    }

    if (-not $InstalledByPythonManager) {
        $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
        if (-not $winget) {
            Start-Process 'https://www.python.org/downloads/windows/'
            throw 'Python 3.12 fehlt und konnte nicht automatisch installiert werden. Installiere Python 3.12 von python.org und starte Install-Noxvyr.cmd erneut.'
        }
        & $winget.Source install --exact --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements --silent
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 konnte über winget nicht installiert werden.' }
        $UserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
        $MachinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
        $env:Path = "$UserPath;$MachinePath"
        $Launcher = Find-PythonLauncher
    }
}

if ($Launcher) {
    $LauncherHasPython312 = $false
    try {
        $previousNativePreference = $PSNativeCommandUseErrorActionPreference
        if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
            $PSNativeCommandUseErrorActionPreference = $false
        }
        & $Launcher -3.12 --version *> $null
        $LauncherHasPython312 = ($LASTEXITCODE -eq 0)
    } catch {
        $LauncherHasPython312 = $false
    } finally {
        if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
            $PSNativeCommandUseErrorActionPreference = $previousNativePreference
        }
    }
    if (-not $LauncherHasPython312) { $Launcher = $null }
}

if (-not (Test-Python312 $Launcher)) {
    throw 'Python 3.12 wurde nach der Installation nicht gefunden. Starte den Server neu und führe Install-Noxvyr.cmd erneut aus.'
}

if (-not (Test-Path -LiteralPath $InstallDir)) { New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null }
Get-ChildItem -LiteralPath $Source -Force | Where-Object { $_.Name -notin @('.env', '.venv', 'data', '__pycache__') } | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $InstallDir -Recurse -Force
}
$EnvFile = Join-Path $InstallDir '.env'
if (-not (Test-Path -LiteralPath $EnvFile)) {
    $SourceEnvFile = Join-Path $Source '.env'
    if (Test-Path -LiteralPath $SourceEnvFile) {
        Copy-Item -LiteralPath $SourceEnvFile -Destination $EnvFile
    } else {
        Copy-Item (Join-Path $InstallDir '.env.example') $EnvFile
    }
}
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
