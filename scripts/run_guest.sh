#!/usr/bin/env bash
set -euo pipefail
base=/srv/bmw-idrive85
image="${BMW_TOOLS_IMAGE:-sha256:d7d89513b9fa8c2631b6ebfbdcf60fa3a38af605ab995440330f4820e10e58e1}"
# Mac defaults: host GPU (Venus) and a kernel uinput touchscreen. The Windows/WSL2 port
# passes software rendering and the userspace touch shim (see docs/WINDOWS.md).
gpu_backend="${BMW_GPU_BACKEND:-venus}"
touch_backend="${BMW_TOUCH_BACKEND:-uinput}"
viewer_port="${BMW_PUBLISH_PORT:-5011}"
stream_fps="${BMW_STREAM_FPS:-60}"
platform=()
if [[ -n "${BMW_DOCKER_PLATFORM:-}" ]]; then platform=(--platform "$BMW_DOCKER_PLATFORM"); fi
test -f "$base/state/config/coding.json"
case "$gpu_backend" in
    venus) test -c /dev/dri/renderD128
           gpu_environment=(-e VK_DRIVER_FILES=/opt/venus/venus.json -e MESA_LOADER_DRIVER_OVERRIDE=zink -e GALLIUM_DRIVER=zink) ;;
    software) gpu_environment=(-e LP_NUM_THREADS="${BMW_RENDER_THREADS:-$(nproc)}") ;;
    *) printf 'Unknown BMW_GPU_BACKEND: %s\n' "$gpu_backend" >&2; exit 2 ;;
esac
case "$touch_backend" in
    uinput) modprobe uinput 2>/dev/null || true; test -c /dev/uinput ;;
    shim) ;;
    *) printf 'Unknown BMW_TOUCH_BACKEND: %s\n' "$touch_backend" >&2; exit 2 ;;
esac
signature="$gpu_backend/$touch_backend/$viewer_port/$stream_fps"
if docker inspect bmw-idrive85 >/dev/null 2>&1; then
    existing="$(docker inspect --format '{{index .Config.Labels "bmw.runtime"}}' bmw-idrive85)"
    # Containers from earlier releases carry no label: they are the Mac defaults.
    if [[ "${existing:-venus/uinput/5011/60}" != "$signature" ]]; then
        printf 'Recreating the HMI container for %s (state and coding are bind-mounted and kept).\n' "$signature"
        docker rm -f bmw-idrive85 >/dev/null
    fi
fi
if ! docker inspect bmw-idrive85 >/dev/null 2>&1; then
    docker create --name bmw-idrive85 "${platform[@]}" --privileged --security-opt label=disable \
        --restart unless-stopped --shm-size 64m --label "bmw.runtime=$signature" \
        -p "127.0.0.1:$viewer_port:5001" -p "127.0.0.1:$((viewer_port + 1)):5002" \
        --mount "type=bind,src=$base/state,dst=/srv/hmi8-lab" \
        --mount "type=bind,src=$base/driver,dst=/opt/venus,readonly" \
        --mount "type=bind,src=$base/source/runtime,dst=/mnt/hmi8-lab,readonly" \
        --mount "type=bind,src=$base/source/container,dst=/opt/hmi8-container,readonly" \
        --mount "type=bind,src=$base/source/web,dst=/opt/hmi8-container/web,readonly" \
        --mount "type=bind,src=$base/source/config,dst=/opt/hmi8-container/presets,readonly" \
        -e HMI_CODING_CONFIG=/srv/hmi8-lab/config/coding.json \
        -e HMI_EMBEDDED_COMPOSITOR=1 -e HMI_TIMEOUT=0 \
        -e HMI_PREVIEW_SCALE=2 -e "HMI_STREAM_FPS=$stream_fps" \
        -e "HMI_GPU_BACKEND=$gpu_backend" -e "HMI_TOUCH_BACKEND=$touch_backend" \
        -e LD_LIBRARY_PATH=/opt/venus -e EGL_PLATFORM=surfaceless "${gpu_environment[@]}" \
        --entrypoint bash "$image" /opt/hmi8-container/entrypoint.sh
fi
export BMW_STATE="$base/state" BMW_RUNTIME="$base/source/runtime" BMW_CONTAINER=bmw-idrive85
python3 "$base/source/tools/select_profile_guest.py" "${1:-current}"
