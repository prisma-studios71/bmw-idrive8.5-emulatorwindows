import hashlib
import json
import pathlib


root = pathlib.Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'private/manifest.json').read_text())
for relative, expected in manifest['files'].items():
    target = root / 'private' / relative
    if target.is_symlink() or not target.resolve().is_relative_to(root / 'private'):
        raise SystemExit(f'Unsafe manifest path: {relative}')
    digest = hashlib.file_digest(target.open('rb'), 'sha256').hexdigest()
    if digest != expected['sha256'] or target.stat().st_size != expected['bytes']:
        raise SystemExit(f'Integrity check failed: {relative}')
    print(f'OK {relative}')
print('Integrity verified against the local manifest; this is not publisher authentication.')
