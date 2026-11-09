#!/usr/bin/env bash
set -euo pipefail
mkdir -p /srv/hmi8-lab/logs /srv/hmi8-lab/native-mock /srv/hmi8-lab/compat
gcc -std=c11 -shared -fPIC -O2 -Wall -Wextra -Werror \
    /mnt/hmi8-lab/hmi_bti_compat.c -o /srv/hmi8-lab/compat/libhmi-bti-compat.so -ldl
if [[ "${HMI_TOUCH_BACKEND:-uinput}" == shim ]]; then
    gcc -std=c11 -shared -fPIC -O2 -U_FORTIFY_SOURCE -Wall -Wextra -Werror \
        /mnt/hmi8-lab/evdev_touch_shim.c -o /srv/hmi8-lab/compat/libevdev-touch-shim.so -ldl -pthread
fi
if [[ "${HMI_GPU_BACKEND:-venus}" == software ]]; then
    # Mesa lavapipe (CPU Vulkan) for ANGLE; library path rewritten for the firmware chroot.
    python3 - <<'PY'
import glob, json, pathlib
manifest = sorted(glob.glob('/usr/share/vulkan/icd.d/lvp_icd.*.json'))
if not manifest:
    raise SystemExit('lavapipe (mesa-vulkan-drivers) is missing from the tools image')
document = json.loads(pathlib.Path(manifest[0]).read_text())
library = pathlib.Path(document['ICD']['library_path']).name
if not pathlib.Path('/usr/lib/aarch64-linux-gnu', library).is_file():
    raise SystemExit(f'lavapipe library {library} not found')
document['ICD']['library_path'] = '/opt/lab-ubuntu/lib/' + library
pathlib.Path('/srv/hmi8-lab/compat/lvp_icd.json').write_text(json.dumps(document, indent=2) + '\n')
print('Software rendering: Mesa lavapipe', document['ICD'].get('api_version', ''), flush=True)
PY
fi
python3 /opt/hmi8-container/mock_state.py native-source /mnt/hmi8-lab/native_mock.cpp \
    > /srv/hmi8-lab/native-mock/combined.cpp
g++ -std=c++17 -shared -fPIC -O2 -Wall -Wextra -Werror \
    /srv/hmi8-lab/native-mock/combined.cpp -o /srv/hmi8-lab/native-mock/libnative-mock.so -ldl -pthread
touch /srv/hmi8-lab/native-mock/enabled
python3 /mnt/hmi8-lab/build_controller_bridge.py
bash /mnt/hmi8-lab/build_stream_guest.sh
exec python3 /opt/hmi8-container/server.py
