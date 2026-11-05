import json
import os
import pathlib
import socket
import subprocess
import sys

from evdev import AbsInfo, ecodes
from input_device import ContainerUInput


root = pathlib.Path(sys.argv[1])
width, height = map(int, sys.argv[2:4])
if width < 2 or height < 2:
    raise ValueError('Touch geometry must be at least 2×2')
capabilities = {
    ecodes.EV_KEY: [ecodes.BTN_TOUCH, ecodes.BTN_TOOL_FINGER],
    ecodes.EV_ABS: [
        (ecodes.ABS_X, AbsInfo(0, 0, width - 1, 0, 0, 0)),
        (ecodes.ABS_Y, AbsInfo(0, 0, height - 1, 0, 0, 0)),
        (ecodes.ABS_MT_SLOT, AbsInfo(0, 0, 9, 0, 0, 0)),
        (ecodes.ABS_MT_TRACKING_ID, AbsInfo(0, 0, 65535, 0, 0, 0)),
        (ecodes.ABS_MT_POSITION_X, AbsInfo(0, 0, width - 1, 0, 0, 0)),
        (ecodes.ABS_MT_POSITION_Y, AbsInfo(0, 0, height - 1, 0, 0, 0)),
        (ecodes.ABS_MT_TOUCH_MAJOR, AbsInfo(0, 0, 255, 0, 0, 0)),
        (ecodes.ABS_MT_PRESSURE, AbsInfo(0, 0, 255, 0, 0, 0)),
    ],
}
with ContainerUInput(capabilities, name='Hmi8 laboratory touchscreen',
            input_props=[ecodes.INPUT_PROP_DIRECT]) as device:
    os.chmod(device.device.path, 0o644)
    (root / 'run/lab-touch-device').write_text(device.device.path)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(root / 'run/lab-touch.sock'))
    server.listen(1)
    active = False
    tracking = 1
    mock_process = None

    def release():
        global active
        if active:
            device.write(ecodes.EV_ABS, ecodes.ABS_MT_SLOT, 0)
            device.write(ecodes.EV_ABS, ecodes.ABS_MT_TRACKING_ID, -1)
            device.write(ecodes.EV_KEY, ecodes.BTN_TOUCH, 0)
            device.write(ecodes.EV_KEY, ecodes.BTN_TOOL_FINGER, 0)
            device.syn()
            active = False

    print(f'Touch device: {device.device.path}, range {width}×{height}', flush=True)
    while True:
        connection, _ = server.accept()
        try:
            with connection.makefile('r') as commands:
                for line in commands:
                    try:
                        command = json.loads(line)
                        action = command['action']
                        if action in ('display-on', 'display-off'):
                            release()
                            if mock_process is not None and mock_process.poll() is None:
                                continue
                            with pathlib.Path('/mnt/hmi8-lab/logs/display-mock.txt').open('a') as log:
                                mock_process = subprocess.Popen(
                                    ['/usr/bin/python3', '/mnt/hmi8-lab/display_state_guest.py',
                                     '--state', action.removeprefix('display-')],
                                    stdout=log, stderr=subprocess.STDOUT,
                                )
                            continue
                        if action == 'up':
                            release()
                            continue
                        if action not in ('down', 'move'):
                            continue
                        if action == 'move' and not active:
                            continue
                        horizontal = max(0, min(width - 1, int(command['x'])))
                        vertical = max(0, min(height - 1, int(command['y'])))
                        device.write(ecodes.EV_ABS, ecodes.ABS_MT_SLOT, 0)
                        if not active:
                            tracking = tracking % 65535 + 1
                            device.write(ecodes.EV_ABS, ecodes.ABS_MT_TRACKING_ID, tracking)
                            device.write(ecodes.EV_KEY, ecodes.BTN_TOUCH, 1)
                            device.write(ecodes.EV_KEY, ecodes.BTN_TOOL_FINGER, 1)
                        device.write(ecodes.EV_ABS, ecodes.ABS_X, horizontal)
                        device.write(ecodes.EV_ABS, ecodes.ABS_Y, vertical)
                        device.write(ecodes.EV_ABS, ecodes.ABS_MT_POSITION_X, horizontal)
                        device.write(ecodes.EV_ABS, ecodes.ABS_MT_POSITION_Y, vertical)
                        device.write(ecodes.EV_ABS, ecodes.ABS_MT_TOUCH_MAJOR, 20)
                        device.write(ecodes.EV_ABS, ecodes.ABS_MT_PRESSURE, 100)
                        device.syn()
                        active = True
                    except (ValueError, KeyError, TypeError):
                        continue
        finally:
            release()
            connection.close()
