import argparse
import hashlib
import json
import pathlib
import tarfile


HMI_SHA256 = '9913ca569bfc78eb2b6174d0660855dc324a7b261667e0b9d20bc9352308062c'
VERSION = '007_023_004'
PARTITIONS = {'9ff7': 'ROOT_rootfs', '9fc6': 'ivi_fs', '9ff9': 'ext_fs'}
RESOURCES = {'a6b0': 'BMW shared', 'a6b1': 'BMW', 'aed4': 'G26 BEV',
             'a6b2': 'BMW M', 'a691': 'G80 LCI', 'a6aa': 'G82 LCI'}
EXCLUDED = ('root', 'home', 'dev', 'proc', 'sys', 'run', 'tmp', 'mnt', 'lost+found',
            'var/opt', 'var/log', 'var/ncd', 'etc/ssh', 'opt/ivi', 'opt/ext',
            'opt/lab-ubuntu', 'opt/lab-overrides', 'opt/venus')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def detect(source):
    for candidate in (source, source / 'extracted', source / 'mgu22filesystem/extracted'):
        if (candidate / 'ROOT_rootfs').is_dir() and (candidate / 'ivi_fs').is_dir():
            return candidate.resolve()
    return None


def partition(source, sgbm):
    path = source / PARTITIONS[sgbm]
    return path / 'rootfs' if sgbm != '9ff7' else path


def excluded(relative, root_partition):
    path = pathlib.PurePosixPath(relative)
    if path.name == '.DS_Store' or path.name in ('.bash_history', '.zsh_history'):
        return True
    if path.suffix.lower() in ('.key', '.p12', '.pfx') or path.name.startswith(
            ('ssh_host_', 'id_rsa', 'id_ed25519', 'id_ecdsa')):
        return True
    prefixes = EXCLUDED if root_partition else ('dev', 'proc', 'sys', 'run', 'tmp', 'home', 'etc/ssh')
    return any(relative == prefix or relative.startswith(prefix + '/') for prefix in prefixes)


def metadata_for(source):
    metadata = source / 'emulator-filesystem-metadata.json'
    if metadata.is_file():
        document = json.loads(metadata.read_text())
        if document.get('hmi_sha256') != HMI_SHA256:
            raise ValueError('Filesystem repair metadata belongs to a different Hmi8 build.')
        for records in document['partitions'].values():
            for name, record in records.items():
                path = pathlib.PurePosixPath(name)
                if not path.parts or path.is_absolute() or '..' in path.parts:
                    raise ValueError(f'Unsafe metadata path: {name}')
                if record.get('link') is not None and not isinstance(record['link'], str):
                    raise ValueError(f'Invalid symlink record: {name}')
        return document['partitions']
    for sgbm in PARTITIONS:
        base = partition(source, sgbm)
        for subfolder in ('lib', 'usr/lib'):
            if any(path.is_file() and not path.is_symlink() and path.stat().st_size == 0
                   for path in (base / subfolder).glob('*.so*')):
                raise ValueError('This Windows extraction has flattened Linux symlinks. Back up '
                                 'emulator-filesystem-metadata.json with it, or use a Linux extraction '
                                 'that preserves symlinks and permissions. See docs/EXTRACTED_FILES.md.')
    return {}


def archive_tree(source, target, records, root_partition):
    def member_filter(member):
        relative = member.name.removeprefix('payload/').removeprefix('./')
        if excluded(relative, root_partition):
            return None
        record = records.get(relative, {})
        if 'link' in record:
            empty_directory = member.isdir() and not any((source / relative).iterdir())
            if not member.issym() and not empty_directory and (not member.isfile() or member.size != 0):
                raise ValueError(f'Refusing to replace nonempty extracted file with a symlink: {relative}')
            member.type, member.linkname, member.size = tarfile.SYMTYPE, record['link'], 0
        elif 'mode' in record:
            member.mode = int(record['mode']) & 0o777
        if member.islnk():
            member.type, member.linkname = tarfile.REGTYPE, ''
            member.size = (source / relative).stat().st_size
        if not (member.isdir() or member.isfile() or member.issym()):
            return None
        member.uid = member.gid = 0
        member.uname = member.gname = ''
        return member

    with tarfile.open(target, 'w:gz', compresslevel=1, dereference=False) as archive:
        archive.add(source, arcname='payload', filter=member_filter)
        for relative, record in records.items():
            if 'link' not in record or excluded(relative, root_partition):
                continue
            path = source / relative
            if path.exists() or path.is_symlink():
                continue
            if any(parent.is_symlink() for parent in path.parents if parent != source.parent):
                raise ValueError(f'Extracted path beneath symlink: {relative}')
            member = tarfile.TarInfo('payload/' + relative)
            member.type, member.linkname, member.mode = tarfile.SYMTYPE, record['link'], 0o777
            archive.addfile(member)


def main():
    parser = argparse.ArgumentParser(description='Import only the used partitions/resources from an extracted backup.')
    parser.add_argument('source', type=pathlib.Path)
    parser.add_argument('--detect', action='store_true')
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--plan', type=pathlib.Path)
    parser.add_argument('--version', default=VERSION)
    options = parser.parse_args()
    source = detect(options.source.expanduser())
    if options.detect:
        print(source or '')
        return
    if source is None:
        raise ValueError('No ROOT_rootfs and ivi_fs directories found in the supplied extracted folder.')
    if options.version != VERSION:
        raise ValueError(f'Extracted-folder support is verified only for {VERSION}.')
    for sgbm in PARTITIONS:
        if not partition(source, sgbm).is_dir():
            raise ValueError(f'Missing extracted partition: {PARTITIONS[sgbm]}')
    if digest(partition(source, '9fc6') / 'usr/bin/Hmi8') != HMI_SHA256:
        raise ValueError('Hmi8 does not match the tested release; refusing a mixed or unsupported extraction.')
    metadata = metadata_for(source)
    items = []
    for sgbm, role in RESOURCES.items():
        package = source / f'swfk_0000{sgbm}_{VERSION}'
        images = list(package.glob('*.ext4'))
        if len(images) == 1:
            artifact, format_name = images[0], 'ext4'
        elif (package / 'rootfs/hmi_version').is_file():
            artifact, format_name = package / 'rootfs', 'tree'
        elif sgbm in ('a6b0', 'a6b1', 'aed4'):
            raise ValueError(f'Missing resource {package.name}: needs its extracted .ext4 image or rootfs/.')
        else:
            print(f'Optional {role} not found (that profile may be unavailable).')
            continue
        items.append({'sgbm': sgbm, 'role': role, 'artifact': str(artifact), 'format': format_name,
                      'destination': f'resources/{package.name}/rootfs'})
    print(f'Extracted input: {source}; tested Hmi8 hash matches. No BMW package containers required.', flush=True)
    if options.check_only:
        return
    if options.plan is None:
        parser.error('--plan is required unless --check-only or --detect is used')
    cache = options.plan.parent / 'extracted-import'
    cache.mkdir(parents=True, exist_ok=True)
    partitions = []
    for sgbm, folder in PARTITIONS.items():
        destination = 'rootfs' if sgbm == '9ff7' else 'rootfs/opt/' + ('ivi' if sgbm == '9fc6' else 'ext') + '/rootfs'
        partitions.append({'sgbm': sgbm, 'role': folder, 'artifact': str(partition(source, sgbm)),
                           'format': 'tree', 'destination': destination})
    items = partitions + items
    for item in items:
        print(f'Preparing {item["sgbm"].upper()}: {item["role"]}', flush=True)
        artifact = pathlib.Path(item['artifact'])
        if item['format'] == 'tree':
            target = cache / f'{item["sgbm"]}.tar.gz'
            archive_tree(artifact, target, metadata.get(item['sgbm'], {}), item['sgbm'] == '9ff7')
            artifact, item['format'] = target, 'tar'
        item.update(artifact=str(artifact.resolve()), sha256=digest(artifact), size=artifact.stat().st_size,
                    version=VERSION, container=str(source), kind='extracted', sparse=False)
    options.plan.write_text(json.dumps({'version': VERSION, 'source_kind': 'extracted', 'items': items}, indent=2) + '\n')
    print('Only ROOT, IVI, EXT and supported BMW/M/vehicle resources will be imported; no maps or boot-chain images.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError) as error:
        raise SystemExit(str(error))
