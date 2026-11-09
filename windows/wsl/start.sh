#!/usr/bin/env bash
# Usage: bash windows/wsl/start.sh [current|g26|g80-m]
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
profile="${1:-current}"
case "$profile" in current|g26|g80-m) ;; *) echo 'Usage: start [g26|g80-m]' >&2; exit 2 ;; esac
[[ -f "$BASE/state/config/coding.json" ]] || fail 'Not installed yet. Run install-windows.cmd first.'
ensure_docker
ensure_arm64
run_profile "$profile"
printf 'Viewer: http://localhost:%s\nSettings and mocks: http://localhost:%s\n' "$VIEWER_PORT" "$SETTINGS_PORT"
if [[ "$HOST_ARCH" == x64 ]]; then
    printf 'ARM64 is emulated on this PC: allow several minutes for HMI initialization.\n'
else
    printf 'Allow a few minutes for HMI initialization (software rendering).\n'
fi
