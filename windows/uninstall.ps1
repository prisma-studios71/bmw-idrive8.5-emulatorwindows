# Removes the emulator's WSL distro, including imported firmware, coding and saved HMI state.
param([switch]$Force)
. (Join-Path $PSScriptRoot 'common.ps1')
if (-not (Test-Distro)) { Write-Host "Nothing to remove: no WSL distro named '$Distro'."; exit 0 }
Write-Host "This permanently deletes the WSL distro '$Distro': imported firmware, coding, mocks and saved state." -ForegroundColor Yellow
Write-Host "Back it up first if needed:  wsl --export $Distro bmw-idrive85-backup.tar"
if (-not $Force) {
    $answer = Read-Host "Type the distro name ($Distro) to confirm"
    if ($answer -ne $Distro) { Write-Host 'Cancelled.'; exit 1 }
}
Stop-KeepAlive
& wsl.exe --unregister $Distro
exit $LASTEXITCODE
