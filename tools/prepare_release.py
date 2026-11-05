import argparse
import gzip
import hashlib
import io
import json
import pathlib
import tarfile


ROOT = pathlib.Path(__file__).resolve().parents[1]


def checked(payload, expected, name):
    if hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError(f'Unrecognized binary: {name}')
    return payload


def source_notices(source):
    notices = []
    for path in sorted(source.rglob('*')):
        if path.is_symlink() or not path.is_file() or path.suffix not in {'.c', '.h', '.cc', '.cpp', '.hpp', '.m', '.mm', '.rs'}:
            continue
        text = path.read_text(errors='replace')
        copyrights = [line for line in text.splitlines() if 'copyright' in line.lower()]
        if copyrights:
            leading = text.lstrip()
            header = ''
            if leading.startswith('/*') and '*/' in leading:
                header = leading[:leading.index('*/') + 2]
            elif leading.startswith('//'):
                header_lines = []
                for line in leading.splitlines():
                    if not line.startswith('//'):
                        break
                    header_lines.append(line)
                header = '\n'.join(header_lines)
            notices.append(str(path.relative_to(source)) + '\n' + header + '\n' + '\n'.join(copyrights))
    if not notices:
        raise ValueError(f'No copyright notices found in {source.name}')
    return ('\n\n'.join(notices) + '\n').encode()


def license_tree(source, prefix):
    result = {}
    for path in sorted(source.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'License input is a symlink: {path.name}')
        if path.is_file():
            result[prefix + '/' + path.relative_to(source).as_posix()] = path.read_bytes()
    if not result:
        raise ValueError(f'No licenses found in {source}')
    return result


def archive(path, files, links):
    with path.open('wb') as output:
        with gzip.GzipFile(fileobj=output, filename='', mode='wb', mtime=0, compresslevel=9) as compressed:
            with tarfile.open(fileobj=compressed, mode='w') as bundle:
                for name, payload in sorted(files.items()):
                    member = tarfile.TarInfo(name)
                    member.size = len(payload)
                    member.mode = 0o755 if name.endswith(('.so', '.dylib', '.so.1', '.so.0', '.so.3')) else 0o644
                    bundle.addfile(member, io.BytesIO(payload))
                for name, target in sorted(links.items()):
                    member = tarfile.TarInfo(name)
                    member.type, member.linkname, member.mode = tarfile.SYMTYPE, target, 0o777
                    bundle.addfile(member)
    payload = path.read_bytes()
    return {'sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload)}


def main():
    parser = argparse.ArgumentParser(description='Prepare allowlisted graphics releases without firmware or VM state.')
    parser.add_argument('--host', type=pathlib.Path, default=ROOT / 'private/host-runtime')
    parser.add_argument('--driver', type=pathlib.Path, default=ROOT / 'private/driver.tar.gz')
    parser.add_argument('--licenses', type=pathlib.Path, required=True)
    parser.add_argument('--mesa-source', type=pathlib.Path, required=True)
    parser.add_argument('--guest-mesa-source', type=pathlib.Path, required=True)
    parser.add_argument('--virgl-source', type=pathlib.Path, required=True)
    parser.add_argument('--output', type=pathlib.Path, default=ROOT / '.local/release')
    options = parser.parse_args()
    allowed_outputs = {'host-runtime.tar.gz', 'driver.tar.gz', 'assets.json', 'SHA256SUMS'}
    if options.output.exists():
        for path in options.output.iterdir():
            if path.name not in allowed_outputs or path.is_symlink() or not path.is_file():
                raise ValueError(f'Unexpected release output; review before continuing: {path.name}')
    provenance = json.loads((ROOT / 'docs/graphics-provenance.json').read_text())
    host = {}
    for name, expected in provenance['host'].items():
        host['host-runtime/' + name] = checked((options.host / name).read_bytes(), expected, name)
    host.update(license_tree(options.mesa_source / 'licenses', 'host-runtime/licenses/mesa'))
    host['host-runtime/licenses/mesa-copyrights.txt'] = source_notices(options.mesa_source)
    host['host-runtime/licenses/virglrenderer-COPYING'] = (options.virgl_source / 'COPYING').read_bytes()
    host['host-runtime/licenses/virglrenderer-copyrights.txt'] = source_notices(options.virgl_source)
    driver = {}
    with tarfile.open(options.driver) as original:
        for name, expected in provenance['driver'].items():
            member = original.getmember('driver/' + name)
            if not member.isfile():
                raise ValueError(f'Binary is not a regular file: {name}')
            driver['driver/' + name] = checked(original.extractfile(member).read(), expected, name)
    required = ('ANGLE-LICENSE', 'CHROMIUM-LICENSE', 'chromium-credits.html',
                'mesa-vulkan-drivers/LICENSE.dependencies', 'libwayland-client/COPYING',
                'libxcb/COPYING', 'libdisplay-info/LICENSE', 'vulkan-loader/LICENSE.txt')
    for name in required:
        if not (options.licenses / 'driver-licenses' / name).is_file():
            raise ValueError(f'Missing license input: {name}')
    credits = (options.licenses / 'driver-licenses/chromium-credits.html').read_bytes()
    checked(credits, provenance['sources']['chromium_credits_sha256'], 'Chromium bundled credits')
    driver.update(license_tree(options.licenses / 'driver-licenses', 'driver/licenses'))
    driver.update(license_tree(options.guest_mesa_source / 'licenses', 'driver/licenses/mesa'))
    driver['driver/licenses/mesa-copyrights.txt'] = source_notices(options.guest_mesa_source)
    driver['driver/licenses/egl_wayland_shim.c'] = (ROOT / 'runtime/egl_wayland_shim.c').read_bytes()
    for files, prefix in ((host, 'host-runtime'), (driver, 'driver')):
        files[prefix + '/licenses/PROJECT-LICENSE'] = (ROOT / 'LICENSE').read_bytes()
        files[prefix + '/licenses/PROJECT-NOTICE'] = (ROOT / 'NOTICE').read_bytes()
        files[prefix + '/licenses/provenance.json'] = (json.dumps(provenance, indent=2) + '\n').encode()
    options.output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / 'config/assets.json').read_text())
    host_links = {'host-runtime/libvirglrenderer.dylib': 'libvirglrenderer.1.dylib'}
    driver_links = {'driver/angle/libEGL.so.1': 'libEGL.so', 'driver/angle/libGLESv2.so.2': 'libGLESv2.so'}
    for name, files, links in (('host-runtime.tar.gz', host, host_links), ('driver.tar.gz', driver, driver_links)):
        result = archive(options.output / name, files, links)
        manifest['assets'][name].update(result)
        print(f'{name}: {result["bytes"]:,} bytes; SHA-256 {result["sha256"]}')
    (options.output / 'assets.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (options.output / 'SHA256SUMS').write_text(''.join(
        f'{record["sha256"]}  {name}\n' for name, record in manifest['assets'].items()))
    print('Prepared locally only. Review artifacts and copy assets.json into config before publishing.')


if __name__ == '__main__':
    main()
