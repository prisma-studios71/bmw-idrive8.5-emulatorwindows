#!/usr/bin/env bash
# Prepare the dedicated WSL distro: systemd, Docker, and ARM64 emulation on x86-64.
# Exit code 10 means /etc/wsl.conf changed: the caller restarts the distro and runs this again.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
changed="$(python3 - <<'PY'
import configparser, pathlib
path = pathlib.Path('/etc/wsl.conf')
config = configparser.ConfigParser()
config.optionxform = str
if path.exists():
    config.read(path)
before = {section: dict(config[section]) for section in config.sections()}
for section, key, value in (('boot', 'systemd', 'true'), ('user', 'default', 'root'),
                            ('interop', 'appendWindowsPath', 'false')):
    if not config.has_section(section):
        config.add_section(section)
    config[section][key] = value
after = {section: dict(config[section]) for section in config.sections()}
if before != after:
    with path.open('w') as stream:
        config.write(stream)
    print('changed')
PY
)"
if [[ "$changed" == changed ]] || [[ "$(ps -p 1 -o comm=)" != systemd ]]; then
    printf 'WSL settings updated; the distro must restart once.\n'
    exit 10
fi
packages=(docker.io python3 ca-certificates curl e2fsprogs util-linux kmod)
[[ "$HOST_ARCH" == x64 ]] && packages+=(qemu-user-static)
missing=()
for package in "${packages[@]}"; do
    dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed' || missing+=("$package")
done
if (( ${#missing[@]} )); then
    printf 'Installing: %s\n' "${missing[*]}"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -q
    apt-get install -y -q --no-install-recommends "${missing[@]}"
fi
# BuildKit plugin: optional, docker build falls back to the classic builder without it.
dpkg-query -W -f='${Status}' docker-buildx 2>/dev/null | grep -q 'install ok installed' \
    || DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends docker-buildx \
    || warn 'docker-buildx is unavailable; using the classic Docker builder.'

python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' || fail 'Python 3.11 or newer is required in the WSL distro.'
systemctl enable --now docker >/dev/null 2>&1 || true
ensure_docker
ensure_arm64
losetup -f >/dev/null 2>&1 || modprobe loop 2>/dev/null || true
losetup -f >/dev/null 2>&1 || warn 'No loop devices: importing original .bin packages may fail (the extracted-folder import does not need them).'
printf 'WSL distro ready: %s, Docker %s, ARM64 %s.\n' "$(uname -m)" "$(docker version --format '{{.Server.Version}}')" \
    "$([[ "$HOST_ARCH" == x64 ]] && echo 'emulated by qemu-user' || echo native)"
