import argparse
import hashlib
import os
import pathlib
import re
import struct
import sys
import time


parser = argparse.ArgumentParser(description='Build-gated VM-only display-input state simulation')
parser.add_argument('--state', choices=['on', 'off'], default='on')
options = parser.parse_args()
state = bytes([options.state == 'on'])
root = pathlib.Path('/srv/hmi8-lab/rootfs')
binary = root / 'opt/ivi/rootfs/usr/bin/Hmi8'
expected = '9913ca569bfc78eb2b6174d0660855dc324a7b261667e0b9d20bc9352308062c'
with binary.open('rb') as stream:
    if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
        sys.exit('Refusing display-state override for an unknown Hmi8 build')

for attempt in range(60):
    for process in pathlib.Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            command = (process / 'cmdline').read_bytes().split(b'\0')
            if b'/opt/ivi/rootfs/usr/bin/Hmi8' not in command:
                continue
            mappings = []
            base = None
            for line in (process / 'maps').read_text().splitlines():
                fields = line.split()
                start, end = [int(value, 16) for value in fields[0].split('-')]
                if fields[2] == '00000000' and fields[-1].endswith('/usr/bin/Hmi8'):
                    base = start
                if fields[1] == 'rw-p' and (len(fields) == 5 or fields[-1] == '[heap]'):
                    mappings.append((start, end))
            if base is None:
                continue
            descriptor = os.open(process / 'mem', os.O_RDWR)
            try:
                setter = os.pread(descriptor, 12, base + 0x5DAA0C0)
                if setter != bytes.fromhex('5f2403d501680039c0035fd6'):
                    sys.exit('Refusing display-state override: setter signature changed')
                needle = struct.pack('<Q', base + 0xFDBDA90)
                matches = []
                for start, end in mappings:
                    position = start
                    while position < end:
                        size = min(1024 * 1024, end - position)
                        chunk = os.pread(descriptor, size, position)
                        offset = chunk.find(needle)
                        while offset != -1:
                            candidate = position + offset - 32
                            body = os.pread(descriptor, 200, candidate)
                            if (len(body) == 200 and
                                struct.unpack_from('<Q', body, 88)[0] == base + 0xFB9D768 and
                                struct.unpack_from('<Q', body, 144)[0] == base + 0xFB393C0 and
                                body[26] in (0, 1)):
                                matches.append(candidate)
                            offset = chunk.find(needle, offset + 8)
                        position += max(8, size - 8)
                log = pathlib.Path('/mnt/hmi8-lab/logs/mesa-g26.hmi-dlt.txt').read_text(errors='replace')
                parents = re.findall(r'Added target 21CHmiTouchEventHandler \((0x[0-9a-f]+)\)', log)
                if not parents:
                    continue
                parent = int(parents[-1], 16)
                child = struct.unpack('<Q', os.pread(descriptor, 8, parent + 144))[0]
                matches = [candidate for candidate in matches if candidate == child]
                if len(matches) == 1:
                    address = matches[0] + 26
                    before = os.pread(descriptor, 1, address)
                    os.pwrite(descriptor, state, address)
                    after = os.pread(descriptor, 1, address)
                    if after != state:
                        sys.exit('Display-input state readback failed')
                    print(f'VM-only display-input state: state={options.state} pid={process.name} address={address:#x} previous={before.hex()} readback={after.hex()}', flush=True)
                    sys.exit(0)
                if len(matches) > 1:
                    sys.exit(f'Refusing ambiguous display-state override: {len(matches)} objects')
            finally:
                os.close(descriptor)
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    time.sleep(1)
sys.exit('Display-state object was not found')
