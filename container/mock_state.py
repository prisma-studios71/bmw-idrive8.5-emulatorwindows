import json
import math
import os
import pathlib
import re
import tempfile


DEFAULTS = {
    'title': 'Midnight Drive',
    'artist': 'HMI Lab Artist',
    'album': '',
    'source': 'Bluetooth (mock)',
    'left_temperature': 21.0,
    'right_temperature': 22.0,
    'climate_on': True,
}


def validate(document):
    if not isinstance(document, dict) or set(document) != set(DEFAULTS):
        raise ValueError('Supply exactly the supported climate/media fields')
    for name in ('title', 'artist', 'album', 'source'):
        value = document[name]
        if not isinstance(value, str) or len(value) > 128 or any(ord(character) < 32 or 127 <= ord(character) < 160 for character in value):
            raise ValueError(f'{name}: at most 128 characters, without control characters')
    for name in ('left_temperature', 'right_temperature'):
        value = document[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 16 <= value <= 28:
            raise ValueError(f'{name}: a finite number from 16 to 28 Celsius is required')
    if type(document['climate_on']) is not bool:
        raise ValueError('climate_on: a JSON boolean is required')
    return dict(document)


def active_directory(state):
    profile = (state / 'logs/active-profile.txt').read_text().strip()
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', profile):
        raise ValueError('Invalid active runtime profile')
    return profile, state / 'profiles' / profile / 'mock'


def status(state):
    profile, directory = active_directory(state)
    saved = directory / 'state.json'
    document = validate(json.loads(saved.read_text())) if saved.is_file() else dict(DEFAULTS)
    return {
        'profile': profile,
        'enabled': (state / 'native-mock/enabled').is_file(),
        'available': (state / 'native-mock/libnative-mock.so').is_file(),
        'configured': saved.is_file(),
        'state': document,
        'note': 'Experimental native display-state simulation; not Bluetooth pairing, audio playback, or a vehicle HVAC service.',
    }


def atomic_write(destination, content):
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=destination.parent, delete=False) as stream:
        temporary = pathlib.Path(stream.name)
        stream.write(content)
    try:
        temporary.chmod(0o644)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def save(state, document):
    document = validate(document)
    if not (state / 'native-mock/enabled').is_file() or not (state / 'native-mock/libnative-mock.so').is_file():
        raise ValueError('Native mock is not installed/enabled. Run hmi8_gpu_lab/install_native_mock.sh in the prepared GPU lab first.')
    profile, directory = active_directory(state)
    directory.mkdir(parents=True, exist_ok=True)
    secondary = ' · '.join(value for value in (document['artist'], document['album']) if value)
    transport = '\n'.join((document['title'], secondary, document['source'],
                           f"{document['left_temperature']} {document['right_temperature']} {int(document['climate_on'])}", ''))
    atomic_write(directory / 'state.txt', transport)
    atomic_write(directory / 'state.json', json.dumps(document, ensure_ascii=False, indent=2) + '\n')
    return {'ok': True, 'profile': profile, 'state': document,
            'note': 'Saved for the active profile. Allow about one minute after boot, then approximately one second for updates. No audio is played.'}
