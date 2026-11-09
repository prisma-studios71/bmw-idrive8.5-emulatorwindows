# Open a root shell in the emulator's WSL distro (logs: /srv/bmw-idrive85/state/logs).
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-Installed
& wsl.exe -d $Distro -u root --cd /srv/bmw-idrive85
