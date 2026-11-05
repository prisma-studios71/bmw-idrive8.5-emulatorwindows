"""Find and verify the BMW packages the emulator needs.

Usage: python3 tools/find_packages.py SOURCE [--plan PLAN.json] [--version 007_023_004]

SOURCE can be a PSdZData folder (its swe/swfl and swe/swfk subfolders are
searched) or any folder holding the packages. Two layouts are recognised:

  swfl_00009fc6.bin.007_023_004              (tar container, PSdZData style)
  swfk_0000a6b1_007_023_004/full/...json+gz   (unpacked container folder)

Every selected artifact is checked against the SHA-256 and size listed in
BMW's own manifest inside the package. Nothing is extracted or modified here.
"""
import argparse
import hashlib
import json
import pathlib
import re
import sys
import tarfile

ROOT = pathlib.Path(__file__).resolve().parents[1]

# SGBM -> (role, artifact name pattern, destination inside the runtime)
REQUIRED = {
    '9ff7': ('Root filesystem', r'bmw-image-mgu22-sa8155\.ext4\.simg\.bin\.gz$', 'rootfs'),
    '9fc6': ('IVI filesystem (Hmi8)', r'-ivi-sa8155\.ext4\.simg\.bin\.gz$', 'rootfs/opt/ivi'),
    '9ff9': ('EXT filesystem', r'-ext-sa8155\.ext4\.simg\.bin\.gz$', 'rootfs/opt/ext'),
    'a6b0': ('Brand data BMW-shared', r'\.hmi-data\.bmw-shared\.ext4\.bin\.gz$', 'resource'),
    'a6b1': ('Brand data BMW', r'\.hmi-data\.bmw\.ext4\.bin\.gz$', 'resource'),
    'aed4': ('Car graphics G26 BEV', r'\.hmi-vehicles\.g26bev\.ext4\.bin\.gz$', 'resource'),
}
OPTIONAL = {
    'a6b2': ('Brand data BMW M (M interface)', r'\.hmi-data\.bmwm\.ext4\.bin\.gz$', 'resource'),
    'a691': ('Car graphics G80 LCI (M3)', r'\.hmi-vehicles\.g80lci\.ext4\.bin\.gz$', 'resource'),
    'a6aa': ('Car graphics G82 LCI (M4)', r'\.hmi-vehicles\.g82lci\.ext4\.bin\.gz$', 'resource'),
}
NAME = re.compile(r'^(swfl|swfk)_0000([0-9a-f]{4})(?:\.bin\.|_)(\d{3}_\d{3}_\d{3})$', re.I)


def names():
    table = {}
    path = ROOT / 'docs/swe_names.tsv'
    if path.is_file():
        for line in path.read_text(encoding='utf-8', errors='replace').splitlines()[1:]:
            parts = line.split('\t')
            if len(parts) >= 3:
                table[parts[0].lower()[-4:]] = parts[2].strip()
    return table


class Container:
    """A package as a tar file or as an unpacked folder."""

    def __init__(self, path, kind, sgbm, version):
        self.path, self.kind, self.sgbm, self.version = path, kind, sgbm, version
        manifest_name = f'{kind}_0000{sgbm}_{version}.json'
        if path.is_dir():
            found = [p for p in path.rglob('*.json') if p.name.lower() == manifest_name]
            if not found:
                raise ValueError(f'no {manifest_name} inside {path}')
            self.manifest = json.loads(found[0].read_text())
            self.files = {p.name: p for p in path.rglob('*') if p.is_file()}
        else:
            with tarfile.open(path) as archive:
                members = {pathlib.PurePosixPath(m.name).name: m for m in archive.getmembers() if m.isfile()}
                if manifest_name not in {n.lower() for n in members}:
                    raise ValueError(f'no {manifest_name} inside {path.name}')
                member = next(m for n, m in members.items() if n.lower() == manifest_name)
                self.manifest = json.loads(archive.extractfile(member).read())
                self.files = {n: m.name for n, m in members.items()}

    def artifact(self, pattern):
        matches = [a for a in self.manifest.get('artifacts', []) if re.search(pattern, a['name'], re.I)]
        if len(matches) != 1:
            raise ValueError(f'{self.kind} {self.sgbm}: expected one artifact matching {pattern}, found {len(matches)}')
        return matches[0]

    def open(self, name):
        if self.path.is_dir():
            return self.files[name].open('rb')
        archive = tarfile.open(self.path)
        return archive.extractfile(self.files[name])


def verify(container, artifact):
    digest = hashlib.sha256()
    size = 0
    with container.open(artifact['name']) as stream:
        while chunk := stream.read(8 << 20):
            digest.update(chunk)
            size += len(chunk)
    if size != artifact['size'] or digest.hexdigest() != artifact['hash'].lower():
        raise ValueError(f'{artifact["name"]}: size/SHA-256 does not match the BMW manifest')
    return digest.hexdigest()


def scan(source):
    roots = [source / 'swe/swfl', source / 'swe/swfk'] if (source / 'swe').is_dir() else [source]
    found = {}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob('*'):
            match = NAME.match(path.name)
            if not match:
                continue
            kind, sgbm, version = match.group(1).lower(), match.group(2).lower(), match.group(3)
            if sgbm in REQUIRED or sgbm in OPTIONAL:
                found.setdefault((sgbm, version), path)
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('source', type=pathlib.Path)
    parser.add_argument('--plan', type=pathlib.Path)
    parser.add_argument('--version', help='force a release, e.g. 007_023_004')
    options = parser.parse_args()
    titles = names()
    found = scan(options.source.expanduser().resolve())
    versions = sorted({v for (_, v) in found}, reverse=True)
    complete = [v for v in versions if all((s, v) in found for s in REQUIRED)]
    if options.version:
        complete = [v for v in complete if v == options.version]
    if not complete:
        print('No complete release found. Required packages (all the same version):', file=sys.stderr)
        for sgbm, (role, _, _) in REQUIRED.items():
            have = sorted(v for (s, v) in found if s == sgbm)
            print(f'  {sgbm.upper()}  {role:28} {titles.get(sgbm, ""):40} found: {", ".join(have) or "MISSING"}', file=sys.stderr)
        return 1
    version = complete[0]
    print(f'Release {version}')
    plan = {'version': version, 'items': []}
    for table, required in ((REQUIRED, True), (OPTIONAL, False)):
        for sgbm, (role, pattern, destination) in table.items():
            path = found.get((sgbm, version))
            if path is None:
                print(f'  -    {sgbm.upper()}  {role} not found; that profile will be unavailable')
                continue
            kind = 'swfl' if path.name.lower().startswith('swfl') else 'swfk'
            container = Container(path, kind, sgbm, version)
            artifact = container.artifact(pattern)
            print(f'  ...  {sgbm.upper()}  {role}: verifying {artifact["name"]} ({artifact["size"] / 1e6:.0f} MB)', flush=True)
            sha256 = verify(container, artifact)
            print(f'  OK   {sgbm.upper()}  {titles.get(sgbm, role)}')
            plan['items'].append({
                'sgbm': sgbm, 'kind': kind, 'version': version, 'role': role, 'required': required,
                'container': str(path), 'artifact': artifact['name'], 'size': artifact['size'], 'sha256': sha256,
                'destination': destination if destination != 'resource' else f'resources/swfk_0000{sgbm}_{version}/rootfs',
                'sparse': '.simg.' in artifact['name'],
            })
    if options.plan:
        options.plan.write_text(json.dumps(plan, indent=2) + '\n')
    total = sum(item['size'] for item in plan['items'])
    print(f'All {len(plan["items"])} packages match their BMW manifests ({total / 1e9:.2f} GB to import).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
