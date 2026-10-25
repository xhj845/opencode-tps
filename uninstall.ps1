$ErrorActionPreference = "SilentlyContinue"

$AppDir = Join-Path $env:LOCALAPPDATA "OpenChamberTps"
$PluginDir = Join-Path $env:USERPROFILE ".config\opencode\plugins"

Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -like "*OpenChamberTps*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Remove-Item (Join-Path ([Environment]::GetFolderPath("Startup")) "OpenCode TPS.lnk") -Force
Remove-Item (Join-Path ([Environment]::GetFolderPath("Startup")) "OpenChamber TPS.lnk") -Force
Remove-Item (Join-Path $PluginDir "tps-live.js") -Force
Remove-Item $AppDir -Recurse -Force

Write-Host "OpenCode TPS removed." -ForegroundColor Green
Write-Host "Restart OpenCode and/or OpenChamber to unload the plugin."
