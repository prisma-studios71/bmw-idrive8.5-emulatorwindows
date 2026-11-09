# Copy updated project sources into WSL (no firmware reimport), then restart the profile.
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-Installed
Invoke-WslScript 'sync_source.sh'
exit $WslExit
