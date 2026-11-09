#!/usr/bin/env bash
# Copy updated project sources into the distro without reimporting firmware.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
[[ -d "$BASE/source" ]] || fail 'Not installed yet. Run install-windows.cmd first.'
copy_source "$BASE/source"
sync
printf 'Source updated; restart the selected profile to apply changes.\n'
