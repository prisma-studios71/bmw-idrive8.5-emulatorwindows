#!/usr/bin/env bash
# Shared settings for the Windows port. These scripts run as root *inside* the dedicated
# WSL2 distro, which plays the role the Lima VM plays on a Mac: Docker runs here and the
# firmware runtime lives in /srv/bmw-idrive85, exactly as in the Mac guest.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BASE=/srv/bmw-idrive85
WORK=/var/lib/bmw-idrive85
VIEWER_PORT="${BMW_VIEWER_PORT:-5011}"
SETTINGS_PORT="$((VIEWER_PORT + 1))"
export PYTHONDONTWRITEBYTECODE=1
step=0
say()  { step=$((step + 1)); printf '\n\033[1;34m[%s] %s\033[0m\n' "$step" "$1"; }
ok()   { printf '  \033[32mOK\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
fail() { printf '\n\033[1;31mERROR: %s\033[0m\n' "$1" >&2; exit 1; }

[[ "$(id -u)" -eq 0 ]] || fail 'Run inside the bmw-idrive85 WSL distro as root (the Windows scripts do this).'
grep -qi microsoft /proc/version || fail 'These scripts are for the Windows port and must run inside WSL2.'
mkdir -p "$WORK"

# The firmware is ARM64. On ARM64 Windows it runs natively; on x86-64 Windows the
# container runs through qemu-user (binfmt_misc), which is functional but far slower.
case "$(uname -m)" in
    aarch64) HOST_ARCH=arm64; DOCKER_PLATFORM=; DEFAULT_FPS=30 ;;
    x86_64)  HOST_ARCH=x64;   DOCKER_PLATFORM=linux/arm64; DEFAULT_FPS=10 ;;
    *) fail "Unsupported WSL architecture: $(uname -m)" ;;
esac
# No host GPU bridge exists for WSL2 (no Venus/virtio-gpu): render with Mesa lavapipe.
# The WSL2 ARM64 kernel has no evdev, and qemu-user cannot translate evdev/uinput
# ioctls, so touch uses the userspace shim (runtime/evdev_touch_shim.c).
GPU_BACKEND="${BMW_GPU_BACKEND:-software}"
TOUCH_BACKEND="${BMW_TOUCH_BACKEND:-shim}"
STREAM_FPS="${BMW_STREAM_FPS:-$DEFAULT_FPS}"

ensure_docker() {
    if docker info >/dev/null 2>&1; then return; fi
    systemctl start docker 2>/dev/null || service docker start >/dev/null 2>&1 || true
    for attempt in $(seq 1 30); do
        docker info >/dev/null 2>&1 && return
        sleep 1
    done
    fail 'Docker is not running in the WSL distro. Re-run install-windows.cmd to repair it.'
}

ensure_arm64() {
    [[ "$HOST_ARCH" == x64 ]] || return 0
    local entry=/proc/sys/fs/binfmt_misc/qemu-aarch64
    [[ -e /proc/sys/fs/binfmt_misc/register ]] || mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc
    if [[ ! -e "$entry" ]] || ! grep -qx enabled "$entry"; then
        [[ -f /usr/lib/binfmt.d/qemu-aarch64.conf ]] || fail 'qemu-user-static is missing; re-run install-windows.cmd.'
        [[ ! -e "$entry" ]] || echo -1 > "$entry"
        cat /usr/lib/binfmt.d/qemu-aarch64.conf > /proc/sys/fs/binfmt_misc/register
    fi
    # The F (fix-binary) flag lets ARM64 programs inside containers and chroots find qemu.
    grep -q '^flags:.*F' "$entry" || fail 'ARM64 emulation is registered without the F flag; cannot run the firmware chroot.'
}

tools_image() {
    local image
    image="${BMW_TOOLS_IMAGE:-$(cat "$WORK/tools-image-id" 2>/dev/null || true)}"
    [[ -n "$image" ]] && docker image inspect "$image" >/dev/null 2>&1 || return 1
    printf '%s\n' "$image"
}

build_tools_image() {
    printf '  Building the open-source tools image (ARM64). On x86-64 this is emulated: 10-30 minutes.\n'
    docker build --platform linux/arm64 -t bmw-idrive85-tools:local "$BASE/source"
    docker image inspect --format '{{.Id}}' bmw-idrive85-tools:local > "$WORK/tools-image-id"
}

copy_source() {
    # Project sources only; never BMW files, private assets or local state.
    local destination="$1"
    python3 "$ROOT/container/updates.py" --write "$ROOT/container/build-version.json" >/dev/null || true
    mkdir -p "$destination"
    tar --exclude='__pycache__' --exclude='*.pyc' -C "$ROOT" -cf - \
        Dockerfile .dockerignore LICENSE NOTICE runtime container web config scripts tools docs/swe_names.tsv windows \
        | tar -xf - -C "$destination"
    if grep -rlI $'\r$' "$destination" --include='*.sh' --include='*.py' --include='*.c' --include='*.cpp' >/dev/null; then
        fail 'The project files have Windows (CRLF) line endings. Re-clone with: git clone --config core.autocrlf=false ...'
    fi
}

run_profile() {
    local image
    image="$(tools_image)" || fail 'The tools image is missing; re-run install-windows.cmd.'
    env "BMW_TOOLS_IMAGE=$image" "BMW_GPU_BACKEND=$GPU_BACKEND" "BMW_TOUCH_BACKEND=$TOUCH_BACKEND" \
        "BMW_PUBLISH_PORT=$VIEWER_PORT" "BMW_DOCKER_PLATFORM=$DOCKER_PLATFORM" "BMW_STREAM_FPS=$STREAM_FPS" \
        bash "$BASE/source/scripts/run_guest.sh" "$1"
}
