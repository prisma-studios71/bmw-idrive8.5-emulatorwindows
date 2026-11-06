#!/usr/bin/env bash
set -euo pipefail
mkdir -p /srv/hmi8-lab/logs /srv/hmi8-lab/native-mock /srv/hmi8-lab/compat
gcc -std=c11 -shared -fPIC -O2 -Wall -Wextra -Werror \
    /mnt/hmi8-lab/hmi_bti_compat.c -o /srv/hmi8-lab/compat/libhmi-bti-compat.so -ldl
python3 /opt/hmi8-container/mock_state.py native-source /mnt/hmi8-lab/native_mock.cpp \
    > /srv/hmi8-lab/native-mock/combined.cpp
g++ -std=c++17 -shared -fPIC -O2 -Wall -Wextra -Werror \
    /srv/hmi8-lab/native-mock/combined.cpp -o /srv/hmi8-lab/native-mock/libnative-mock.so -ldl -pthread
touch /srv/hmi8-lab/native-mock/enabled
python3 /mnt/hmi8-lab/build_controller_bridge.py
bash /mnt/hmi8-lab/build_stream_guest.sh
exec python3 /opt/hmi8-container/server.py
