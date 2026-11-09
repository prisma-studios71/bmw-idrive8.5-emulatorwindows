# Shared helpers for the Windows port (PowerShell 5.1+). Keep this file ASCII-only:
# Windows PowerShell 5.1 reads BOM-less scripts in the legacy code page.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 3
$env:WSL_UTF8 = '1'   # wsl.exe prints UTF-16 otherwise
# Decode wsl.exe output as UTF-8, so paths like C:\Users\<non-ASCII name> survive.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$OutputEncoding = [System.Text.Encoding]::UTF8
$script:Distro = if ($env:BMW_WSL_DISTRO) { $env:BMW_WSL_DISTRO } else { 'bmw-idrive85' }
$script:RepoRoot = Split-Path -Parent $PSScriptRoot
$script:DataRoot = Join-Path $env:LOCALAPPDATA 'bmw-idrive85'
$script:ViewerPort = if ($env:BMW_VIEWER_PORT) { [int]$env:BMW_VIEWER_PORT } else { 5011 }
$script:Step = 0
$script:WslExit = 0
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

function Say([string]$Message) {
    $script:Step++
    Write-Host ''
    Write-Host ("[{0}] {1}" -f $script:Step, $Message) -ForegroundColor Cyan
}
function Ok([string]$Message) { Write-Host "  OK $Message" -ForegroundColor Green }
function Fail([string]$Message) {
    Write-Host ''
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

function Get-HostArch {
    try {
        $arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
    } catch {
        $arch = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
    }
    switch -Regex ($arch) {
        '^(Arm64|ARM64)$' { return 'arm64' }
        '^(X64|AMD64)$' { return 'x64' }
        default { Fail "Unsupported Windows architecture: $arch (x64 or ARM64 required)." }
    }
}

function Test-WslInstalled {
    if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) { return $false }
    & wsl.exe --status *> $null
    return ($LASTEXITCODE -eq 0)
}

function Test-Distro {
    $names = & wsl.exe --list --quiet 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $names) { return $false }
    foreach ($name in $names) {
        if ($name.Trim([char]0, ' ', "`t") -eq $script:Distro) { return $true }
    }
    return $false
}

function ConvertTo-WslPath([string]$WindowsPath) {
    $full = [System.IO.Path]::GetFullPath($WindowsPath)
    $result = & wsl.exe -d $script:Distro -u root --exec wslpath -a -u $full
    if ($LASTEXITCODE -ne 0 -or -not $result) { Fail "Cannot translate path for WSL: $full" }
    return ($result | Select-Object -First 1).Trim()
}

# Run a project script inside the distro as root. Arguments are passed without a shell.
# Output streams straight to the console; the exit code is left in $script:WslExit.
function Invoke-WslScript([string]$Script, [string[]]$Arguments = @()) {
    $repo = ConvertTo-WslPath $script:RepoRoot
    $environment = @("BMW_VIEWER_PORT=$($script:ViewerPort)")
    foreach ($name in 'BMW_STREAM_FPS', 'BMW_TOUCH_BACKEND', 'BMW_RENDER_THREADS', 'BMW_START_TIMEOUT', 'BMW_TOOLS_IMAGE') {
        $value = [Environment]::GetEnvironmentVariable($name)
        if ($value) { $environment += "$name=$value" }
    }
    & wsl.exe -d $script:Distro -u root --exec /usr/bin/env @environment bash "$repo/windows/wsl/$Script" @Arguments
    $script:WslExit = $LASTEXITCODE
}

# WSL stops an idle distro (and Docker with it) when no Windows process uses it.
function Start-KeepAlive {
    New-Item -ItemType Directory -Force -Path $script:DataRoot | Out-Null
    $pidFile = Join-Path $script:DataRoot 'keepalive.pid'
    if (Test-Path $pidFile) {
        $existing = Get-Process -Id ([int](Get-Content $pidFile -Raw).Trim()) -ErrorAction SilentlyContinue
        if ($existing -and $existing.ProcessName -eq 'wsl') { return }
    }
    $process = Start-Process -FilePath wsl.exe -WindowStyle Hidden -PassThru `
        -ArgumentList @('-d', $script:Distro, '-u', 'root', '--exec', 'sleep', 'infinity')
    Set-Content -Path $pidFile -Value $process.Id -Encoding ascii
}

function Stop-KeepAlive {
    $pidFile = Join-Path $script:DataRoot 'keepalive.pid'
    if (-not (Test-Path $pidFile)) { return }
    $existing = Get-Process -Id ([int](Get-Content $pidFile -Raw).Trim()) -ErrorAction SilentlyContinue
    if ($existing -and $existing.ProcessName -eq 'wsl') { Stop-Process -Id $existing.Id -Force }
    Remove-Item $pidFile -Force
}

function Assert-Installed {
    if (-not (Test-WslInstalled)) { Fail 'WSL is not installed. Run install-windows.cmd first.' }
    if (-not (Test-Distro)) { Fail "The WSL distro '$($script:Distro)' does not exist. Run install-windows.cmd first." }
}
