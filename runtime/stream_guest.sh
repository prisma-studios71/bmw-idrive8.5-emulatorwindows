#!/usr/bin/env bash
set -euo pipefail
process="$(pgrep -f '^(\S*qemu\S* (\S+ )?)?/opt/lab-ubuntu/lib/ld-linux-aarch64.so.1.* /opt/ivi/rootfs/usr/bin/Hmi8' | head -n 1)"
if [[ -z "$process" ]]; then
    printf 'Hmi8 is not running. Start the window session first.\n' >&2
    exit 1
fi
if [[ "${HMI_INPUT_ONLY:-0}" == 1 ]]; then
    exec nsenter --target "$process" --mount --net python3 -u -c '
import socket, sys
with socket.socket(socket.AF_UNIX) as connection:
    connection.connect("/srv/hmi8-lab/rootfs/run/lab-touch.sock")
    for line in sys.stdin.buffer:
        connection.sendall(line)
'
fi
exec nsenter --target "$process" --mount --net \
    env XDG_RUNTIME_DIR=/srv/hmi8-lab/rootfs/run/wayland WAYLAND_DISPLAY=wayland-0 \
    /srv/hmi8-lab/bin/hmi-stream - "${1:-60}" "${2:-85}" "${3:-1}"
