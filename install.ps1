#requires -Version 5.1
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppDir = Join-Path $env:LOCALAPPDATA "OpenChamberTps"
$PluginDir = Join-Path $env:USERPROFILE ".config\opencode\plugins"

Write-Host "OpenCode / OpenChamber TPS installer" -ForegroundColor Cyan

$pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $pythonw) {
    $pythonw = Get-ChildItem (Join-Path $env:LOCALAPPDATA "Programs\Python\Python*\pythonw.exe") -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $pythonw) {
    Write-Host "Python 3.10+ (pythonw.exe) was not found. Install Python first, then run this again." -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
New-Item -ItemType Directory -Force -Path $PluginDir | Out-Null

Copy-Item (Join-Path $Root "app\*.py") $AppDir -Force
Copy-Item (Join-Path $Root "plugin\tps-live.js") $PluginDir -Force

Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*OpenChamberTps*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 400

$startup = [Environment]::GetFolderPath("Startup")
$oldLinkPath = Join-Path $startup "OpenChamber TPS.lnk"
Remove-Item $oldLinkPath -Force -ErrorAction SilentlyContinue
$linkPath = Join-Path $startup "OpenCode TPS.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($linkPath)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = '"' + (Join-Path $AppDir "watcher.py") + '"'
$shortcut.WorkingDirectory = $AppDir
$shortcut.WindowStyle = 7
$shortcut.Description = "OpenCode / OpenChamber live tokens/s overlay"
$shortcut.Save()

Start-Process -FilePath $pythonw -ArgumentList ('"' + (Join-Path $AppDir "watcher.py") + '"') -WorkingDirectory $AppDir -WindowStyle Hidden

Write-Host "Installed." -ForegroundColor Green
Write-Host "Restart OpenCode and/or OpenChamber once, then send a message."
Write-Host "The ball appears only while a response is running in either app."
Write-Host "Remove the startup shortcut to disable auto-start."
