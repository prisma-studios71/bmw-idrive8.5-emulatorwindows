import pathlib
import subprocess
import sys
import time


root = pathlib.Path(sys.argv[1])
vm = sys.argv[2]
viewer = int(sys.argv[3])
command = [
    'ssh', '-F', str(pathlib.Path.home() / '.lima' / vm / 'ssh.config'), '-nN',
    '-o', 'ControlMaster=no', '-o', 'ControlPath=none', '-o', 'ExitOnForwardFailure=yes',
    '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
    '-L', f'127.0.0.1:{viewer}:127.0.0.1:5011',
    '-L', f'127.0.0.1:{viewer + 1}:127.0.0.1:5012', f'lima-{vm}',
]
with (root / '.local/tunnel.log').open('wb') as log:
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log,
                               stderr=subprocess.STDOUT, start_new_session=True)
(root / '.local/tunnel.pid').write_text(str(process.pid) + '\n')
time.sleep(0.5)
if process.poll() is not None:
    raise SystemExit('SSH forwarding failed; see .local/tunnel.log')
