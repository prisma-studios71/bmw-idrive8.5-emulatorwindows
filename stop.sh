#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
source "$here/scripts/common.sh"
python3 "$ROOT/tools/boot_splash.py" stop "$ROOT" "$VIEWER_PORT"
limactl shell --workdir=/tmp "$VM" -- sudo docker stop -t 15 bmw-idrive85
if [[ -f "$ROOT/.local/tunnel.pid" ]]; then
    previous="$(cat "$ROOT/.local/tunnel.pid")"
    if [[ "$previous" =~ ^[0-9]+$ ]] && ps -p "$previous" -o args= | grep -Fq "lima-$VM"; then kill "$previous"; fi
fi
if [[ "${1:-}" == --vm ]]; then limactl stop "$VM"; fi
