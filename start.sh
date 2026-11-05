#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
bash "$here/doctor.sh"
source "$here/scripts/common.sh"
profile="${1:-current}"
case "$profile" in current|g26|g80-m) ;; *) echo 'Usage: bash start.sh [g26|g80-m]' >&2; exit 2 ;; esac
python3 "$ROOT/tools/boot_splash.py" stop "$ROOT" "$VIEWER_PORT"
if [[ -f "$ROOT/.local/tunnel.pid" ]]; then
    previous="$(cat "$ROOT/.local/tunnel.pid")"
    if [[ "$previous" =~ ^[0-9]+$ ]] && ps -p "$previous" -o args= | grep -Fq "lima-$VM"; then kill "$previous"; fi
fi
for port in "$VIEWER_PORT" "$SETTINGS_PORT"; do
    if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
        printf 'Port %s is in use. Stop the other viewer or set BMW_VIEWER_PORT to a free port pair.\n' "$port" >&2
        exit 1
    fi
done
python3 "$ROOT/tools/boot_splash.py" start "$ROOT" "$VIEWER_PORT" --vm "$VM"
trap 'python3 "$ROOT/tools/boot_splash.py" status "$ROOT" "$VIEWER_PORT" "Startup failed. Check the terminal output and .local/tunnel.log."' ERR
if [[ "${BMW_OPEN_BROWSER:-1}" != 0 ]]; then open "http://localhost:$VIEWER_PORT" 2>/dev/null || true; fi
if [[ "$(limactl list --format '{{.Status}}' "$VM")" != Running ]]; then lima_start "$VM" --tty=false; fi
limactl shell --workdir=/tmp "$VM" -- true
if ! limactl shell --workdir=/tmp "$VM" -- grep -qw console=hvc0 /proc/cmdline; then
    python3 "$ROOT/tools/boot_splash.py" status "$ROOT" "$VIEWER_PORT" 'Enabling the Linux serial boot console (one-time VM restart)…'
    limactl shell --workdir=/tmp "$VM" -- sudo grubby --update-kernel=ALL --args='console=hvc0 loglevel=6'
    limactl stop "$VM"
    lima_start "$VM" --tty=false
fi
python3 "$ROOT/tools/boot_splash.py" status "$ROOT" "$VIEWER_PORT" 'Fedora is ready. Preparing BMW HMI…'
limactl shell --workdir=/tmp "$VM" -- sudo env "BMW_TOOLS_IMAGE=${BMW_TOOLS_IMAGE:-$(cat "$ROOT/.local/tools-image-id" 2>/dev/null || echo sha256:d7d89513b9fa8c2631b6ebfbdcf60fa3a38af605ab995440330f4820e10e58e1)}" \
    bash /srv/bmw-idrive85/source/scripts/run_guest.sh "$profile"
python3 "$ROOT/tools/boot_splash.py" stop "$ROOT" "$VIEWER_PORT"
python3 "$ROOT/tools/open_tunnel.py" "$ROOT" "$VM" "$VIEWER_PORT"
trap - ERR
printf 'Viewer: http://localhost:%s\nSettings and mocks: http://localhost:%s\nAllow about one minute for HMI initialization.\n' "$VIEWER_PORT" "$SETTINGS_PORT"
