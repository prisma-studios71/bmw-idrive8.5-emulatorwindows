import argparse
import json
import pathlib
import subprocess

from prepare_extracted import HMI_SHA256, PARTITIONS, detect, digest, excluded, partition


parser = argparse.ArgumentParser(description='Save Linux link/permission metadata beside a Windows-extracted backup.')
parser.add_argument('source', type=pathlib.Path)
parser.add_argument('--vm', default='bmw-idrive85')
options = parser.parse_args()
source = detect(options.source)
if source is None or digest(partition(source, '9fc6') / 'usr/bin/Hmi8') != HMI_SHA256:
    raise SystemExit('The extracted source must contain the tested Hmi8 binary.')
program = r'''
import hashlib, json, os, pathlib, stat
base = pathlib.Path('/srv/bmw-idrive85/state/rootfs')
with (base / 'opt/ivi/rootfs/usr/bin/Hmi8').open('rb') as stream:
    fingerprint = hashlib.file_digest(stream, 'sha256').hexdigest()
partitions = {}
for sgbm, relative in [('9ff7', ''), ('9fc6', 'opt/ivi/rootfs'), ('9ff9', 'opt/ext/rootfs')]:
    root = base / relative
    records = {}
    for directory, folders, files in os.walk(root, followlinks=False):
        if sgbm == '9ff7' and pathlib.Path(directory) == root / 'opt':
            folders[:] = [name for name in folders if name not in ('ivi', 'ext', 'lab-ubuntu', 'lab-overrides', 'venus')]
        for name in folders + files:
            path = pathlib.Path(directory) / name
            record = {'mode': stat.S_IMODE(path.lstat().st_mode)}
            if path.is_symlink():
                record['link'] = os.readlink(path)
            records[path.relative_to(root).as_posix()] = record
    partitions[sgbm] = records
print(json.dumps({'format': 1, 'hmi_sha256': fingerprint, 'partitions': partitions}))
'''
result = subprocess.run(['limactl', 'shell', '--workdir=/tmp', options.vm, '--',
                         'sudo', 'python3', '-c', program], check=True, capture_output=True, text=True)
document = json.loads(result.stdout)
if document['hmi_sha256'] != HMI_SHA256:
    raise SystemExit('Installed VM Hmi8 does not match the extracted backup.')
for sgbm in PARTITIONS:
    root = partition(source, sgbm)
    document['partitions'][sgbm] = {
        name: record for name, record in document['partitions'][sgbm].items()
        if not excluded(name, sgbm == '9ff7') and ((root / name).exists() or (root / name).is_symlink())
    }
target = source / 'emulator-filesystem-metadata.json'
if target.exists():
    raise SystemExit(f'{target} already exists; refusing to overwrite it.')
target.write_text(json.dumps(document, indent=2) + '\n')
print(f'Saved link/permission metadata (no file contents or keys): {target}')
