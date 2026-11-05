#!/usr/bin/env bash
set -euo pipefail
base=/srv/bmw-idrive85
image="${BMW_TOOLS_IMAGE:-sha256:d7d89513b9fa8c2631b6ebfbdcf60fa3a38af605ab995440330f4820e10e58e1}"
test -f "$base/state/config/coding.json"
test -c /dev/dri/renderD128
modprobe uinput
if ! docker inspect bmw-idrive85 >/dev/null 2>&1; then
    docker create --name bmw-idrive85 --privileged --security-opt label=disable \
        --restart unless-stopped --shm-size 64m \
        -p 127.0.0.1:5011:5001 -p 127.0.0.1:5012:5002 \
        --mount "type=bind,src=$base/state,dst=/srv/hmi8-lab" \
        --mount "type=bind,src=$base/driver,dst=/opt/venus,readonly" \
        --mount "type=bind,src=$base/source/runtime,dst=/mnt/hmi8-lab,readonly" \
        --mount "type=bind,src=$base/source/container,dst=/opt/hmi8-container,readonly" \
        --mount "type=bind,src=$base/source/web,dst=/opt/hmi8-container/web,readonly" \
        --mount "type=bind,src=$base/source/config,dst=/opt/hmi8-container/presets,readonly" \
        -e HMI_CODING_CONFIG=/srv/hmi8-lab/config/coding.json \
        -e HMI_EMBEDDED_COMPOSITOR=1 -e HMI_TIMEOUT=0 \
        -e HMI_PREVIEW_SCALE=2 -e HMI_STREAM_FPS=60 \
        -e LD_LIBRARY_PATH=/opt/venus -e VK_DRIVER_FILES=/opt/venus/venus.json \
        -e EGL_PLATFORM=surfaceless -e MESA_LOADER_DRIVER_OVERRIDE=zink -e GALLIUM_DRIVER=zink \
        --entrypoint bash "$image" /opt/hmi8-container/entrypoint.sh
fi
export BMW_STATE="$base/state" BMW_RUNTIME="$base/source/runtime" BMW_CONTAINER=bmw-idrive85
python3 "$base/source/tools/select_profile_guest.py" "${1:-current}"
