import pathlib
import subprocess
import tempfile


root = pathlib.Path(__file__).resolve().parents[1]
excluded = {'private', '.local', '.git', '.idea', '__pycache__'}
blocked_suffixes = {'.bin', '.ext4', '.simg', '.qcow2', '.raw', '.nds', '.key', '.pem', '.p12', '.pfx', '.dlt'}
issues = []
files = []
repository = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
with tempfile.TemporaryDirectory(prefix='bmw-publish-check-') as temporary:
    if repository.returncode == 0 and pathlib.Path(repository.stdout.strip()).resolve() == root:
        command = ['git', '-C', str(root)]
    else:
        subprocess.run(['git', 'init', '-q', temporary], check=True)
        command = ['git', '-C', temporary, '--work-tree', str(root)]
    candidates = subprocess.check_output(command + ['ls-files', '--cached', '--others', '--exclude-standard', '-z'])
paths = sorted(set(entry for entry in candidates.decode().split('\0') if entry))
for name in paths:
    path = root / name
    relative = path.relative_to(root)
    if any(part in excluded for part in relative.parts):
        issues.append(f'Private or generated path included: {relative}')
        continue
    if relative.parts[0] == 'bmw-files' and str(relative) != 'bmw-files/README.md':
        issues.append(f'BMW input included: {relative}')
        continue
    if path.is_symlink():
        if str(relative) != 'runtime/logs':
            issues.append(f'Unexpected symlink: {relative}')
        continue
    if not path.is_file():
        continue
    files.append(path)
    if path.suffix.lower() in blocked_suffixes or path.name.startswith(('id_rsa', 'id_ed25519')):
        issues.append(f'Blocked artifact: {relative}')
    payload = path.read_bytes()
    if b''.join((b'PRIVATE', b' KEY-----')) in payload:
        issues.append(f'Possible private key: {relative}')
    if len(payload) > 10 * 1024 * 1024:
        issues.append(f'Unexpected large source file: {relative}')
if issues:
    raise SystemExit('\n'.join(issues))
print(f'Checked {len(files)} public candidate files, {sum(path.stat().st_size for path in files):,} bytes.')
print('Private payload excluded. This check is not a full secret, license or binary provenance audit.')
