# Usage: stop-windows.cmd [-Wsl]   (-Wsl also shuts down the WSL distro)
param([switch]$Wsl)
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-Installed
Invoke-WslScript 'stop.sh'
Stop-KeepAlive
if ($Wsl) { & wsl.exe --terminate $Distro | Out-Null; Write-Host "WSL distro '$Distro' stopped." }
exit $WslExit
