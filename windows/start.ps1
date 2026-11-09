# Usage: start-windows.cmd [g26|g80-m]   (no argument: resume the current profile)
param([Parameter(Position = 0)][ValidateSet('current', 'g26', 'g80-m')][string]$VehicleProfile = 'current', [switch]$NoBrowser)
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-Installed
Start-KeepAlive
Invoke-WslScript 'start.sh' @($VehicleProfile)
if ($WslExit -ne 0) { Fail "Start failed (exit code $WslExit). See docs/WINDOWS.md, Troubleshooting." }
if (-not $NoBrowser -and $env:BMW_OPEN_BROWSER -ne '0') { Start-Process "http://localhost:$ViewerPort" }
