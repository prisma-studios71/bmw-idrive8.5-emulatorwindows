import argparse
import hashlib
import json
import pathlib
import tempfile
import urllib.error
import urllib.request


def matches(path, expected):
    if not path.is_file() or path.is_symlink() or path.stat().st_size != expected['bytes']:
        return False
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest() == expected['sha256']


def fetch(root, name):
    if pathlib.PurePath(name).name != name:
        raise ValueError('Asset name must not contain a path.')
    manifest = json.loads((root / 'config/assets.json').read_text())
    expected = manifest['assets'][name]
    destination = root / 'private' / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if matches(destination, expected):
        print(f'Verified {name} (cached)', flush=True)
        return destination
    url = manifest['release_url'].rstrip('/') + '/' + name
    print(f'Downloading {name} ({expected["bytes"] / 1048576:.1f} MiB)', flush=True)
    temporary = None
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'bmw-idrive85-installer'})
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=name + '.', suffix='.part', delete=False) as output:
            temporary = pathlib.Path(output.name)
            with urllib.request.urlopen(request, timeout=60) as response:
                received = 0
                while chunk := response.read(1024 * 1024):
                    received += len(chunk)
                    if received > expected['bytes']:
                        raise ValueError(f'{name} exceeds its expected size.')
                    output.write(chunk)
        if not matches(temporary, expected):
            raise ValueError(f'{name} failed its SHA-256 or size check.')
        temporary.replace(destination)
        print(f'Verified {name}', flush=True)
        return destination
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description='Download a release asset and verify both cached and new copies.')
    parser.add_argument('name')
    options = parser.parse_args()
    try:
        fetch(pathlib.Path(__file__).resolve().parents[1], options.name)
    except (OSError, ValueError, KeyError, urllib.error.URLError) as error:
        raise SystemExit(f'Cannot prepare {options.name}: {error}')


if __name__ == '__main__':
    main()
