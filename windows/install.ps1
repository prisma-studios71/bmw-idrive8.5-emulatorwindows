# BMW iDrive 8.5 emulator - Windows installer (WSL2 + Docker, software rendering).
#   install-windows.cmd [path\to\bmw-files-or-extracted]
# Safe to run again: finished steps are skipped. See docs/WINDOWS.md.
param(
    [Parameter(Position = 0)][string]$BmwFiles = '',
    [string]$RootfsTarball = '',
    [switch]$NoBrowser
)
. (Join-Path $PSScriptRoot 'common.ps1')

$UbuntuBase = 'https://cloud-images.ubuntu.com/wsl/releases/24.04/current'

Say 'Checking this PC'
$arch = Get-HostArch
$build = [int](Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion').CurrentBuildNumber
if ($build -lt 19041) { Fail "Windows 10 2004 (build 19041) or newer is required; this is build $build." }
$memory = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
$drive = Split-Path -Qualifier $env:LOCALAPPDATA
$free = [math]::Floor((Get-PSDrive ($drive.TrimEnd(':'))).Free / 1GB)
if ($free -lt 30) { Fail "At least 30 GiB of free space is needed on $drive (found $free GiB)." }
$sample = Get-Content (Join-Path $PSScriptRoot 'wsl\common.sh') -Raw
if ($sample.Contains("`r`n")) {
    Fail 'This checkout has Windows (CRLF) line endings. Re-clone with: git clone --config core.autocrlf=false <url>'
}
Ok "Windows build $build, $arch, $memory GiB RAM, $free GiB free on $drive"
if ($arch -eq 'x64') {
    Write-Host '  Note: x86-64 PC. The BMW firmware is ARM64 and will be emulated (qemu): it works, but slowly.' -ForegroundColor Yellow
}
if ($memory -lt 12) { Write-Host '  Note: 16 GiB RAM or more is recommended.' -ForegroundColor Yellow }

Say 'Checking WSL2'
if (-not (Test-WslInstalled)) {
    $admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $admin) {
        Fail 'WSL is not installed. Open PowerShell as Administrator, run "wsl --install --no-distribution", reboot, then run install-windows.cmd again.'
    }
    & wsl.exe --install --no-distribution
    Fail 'WSL was installed. Reboot Windows, then run install-windows.cmd again.'
}
& wsl.exe --version *> $null
if ($LASTEXITCODE -ne 0) {
    Fail 'This is the old inbox WSL. Run "wsl --update" (or install WSL from the Microsoft Store), then try again.'
}
Ok 'WSL is installed'

Say "Creating the '$Distro' WSL distro (Ubuntu 24.04)"
if (Test-Distro) {
    Ok 'Already exists'
} else {
    New-Item -ItemType Directory -Force -Path $DataRoot | Out-Null
    $tarball = $RootfsTarball
    if (-not $tarball) {
        $name = "ubuntu-noble-wsl-$($arch -replace 'x64','amd64')-24.04lts.rootfs.tar.gz"
        $tarball = Join-Path $DataRoot $name
        $sums = (Invoke-WebRequest -UseBasicParsing "$UbuntuBase/SHA256SUMS").Content
        if ($sums -is [byte[]]) { $sums = [System.Text.Encoding]::ASCII.GetString($sums) }
        $expected = ($sums -split "`n" | Where-Object { $_ -match "\s\*?$([regex]::Escape($name))$" } | Select-Object -First 1)
        if (-not $expected) { Fail "No checksum for $name at $UbuntuBase" }
        $expected = ($expected -split '\s+')[0].ToLower()
        $current = if (Test-Path $tarball) { (Get-FileHash -Algorithm SHA256 $tarball).Hash.ToLower() } else { '' }
        if ($current -ne $expected) {
            Write-Host "  Downloading $name (about 350 MB)"
            $ProgressPreference = 'SilentlyContinue'
            Invoke-WebRequest -UseBasicParsing "$UbuntuBase/$name" -OutFile "$tarball.part"
            if ((Get-FileHash -Algorithm SHA256 "$tarball.part").Hash.ToLower() -ne $expected) {
                Remove-Item "$tarball.part" -Force
                Fail 'The Ubuntu download failed its SHA-256 check.'
            }
            Move-Item -Force "$tarball.part" $tarball
        }
        Ok 'Ubuntu 24.04 image verified (SHA-256)'
    }
    $target = Join-Path $DataRoot 'wsl'
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    & wsl.exe --import $Distro $target $tarball --version 2
    if ($LASTEXITCODE -ne 0) { Fail 'wsl --import failed. Is virtualization enabled in the BIOS/UEFI?' }
    Ok "Created in $target"
}

Say 'Preparing Docker inside WSL'
Invoke-WslScript 'provision.sh'
if ($WslExit -eq 10) {
    & wsl.exe --terminate $Distro | Out-Null
    Invoke-WslScript 'provision.sh'
    if ($WslExit -eq 10) { Fail 'systemd could not be enabled in WSL. Run "wsl --update", then try again.' }
}
if ($WslExit -ne 0) { Fail "Preparing the WSL distro failed (exit code $WslExit)." }
Ok 'Docker ready'

Say 'Installing the emulator (downloads, import, image build, first start)'
if (-not $BmwFiles) { $BmwFiles = Join-Path $RepoRoot 'bmw-files' }
if (-not (Test-Path $BmwFiles)) { Fail "Folder not found: $BmwFiles (see bmw-files\README.md)" }
Start-KeepAlive
Invoke-WslScript 'install.sh' @(ConvertTo-WslPath $BmwFiles)
if ($WslExit -ne 0) { Fail "Installation failed (exit code $WslExit). See the messages above and docs/WINDOWS.md." }

Write-Host ''
Write-Host "Viewer:   http://localhost:$ViewerPort" -ForegroundColor Green
Write-Host "Settings: http://localhost:$($ViewerPort + 1)" -ForegroundColor Green
if (-not $NoBrowser -and $env:BMW_OPEN_BROWSER -ne '0') { Start-Process "http://localhost:$ViewerPort" }
Write-Host 'Next time just run start-windows.cmd   (stop with stop-windows.cmd)'
