import json
import math
import os
import pathlib
import re
import tempfile


M_FIELDS = {
    'm_engine': ('Engine', ('Efficient', 'Sport', 'Sport Plus')),
    'm_damper': ('Chassis', ('Comfort', 'Sport', 'Sport Plus')),
    'm_steering': ('Steering', ('Comfort', 'Sport')),
    'm_brake': ('Brake', ('Comfort', 'Sport')),
    'm_xdrive': ('M xDrive', ('4WD', '4WD Sport', '2WD')),
}

DEFAULTS = {
    'title': 'Midnight Drive',
    'artist': 'HMI Lab Artist',
    'album': '',
    'source': 'Bluetooth (mock)',
    'left_temperature': 21.0,
    'right_temperature': 22.0,
    'climate_on': True,
    **{name: 1 for name in M_FIELDS},
}


def validate(document):
    if (not isinstance(document, dict) or set(document) - set(DEFAULTS)
            or set(DEFAULTS) - set(M_FIELDS) - set(document)):
        raise ValueError('Supply the supported climate/media fields and optional M selections')
    document = {**DEFAULTS, **document}
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
    for name, (label, choices) in M_FIELDS.items():
        if type(document[name]) is not int or not 1 <= document[name] <= len(choices):
            raise ValueError(f'{label}: select an option from 1 to {len(choices)}')
    return dict(document)


def m_values(directory):
    defaults = {name: DEFAULTS[name] for name in M_FIELDS}
    saved = directory / 'm-state.txt'
    if not saved.is_file():
        return defaults
    try:
        values = [int(value) for value in saved.read_text().split()]
    except ValueError:
        return defaults
    if len(values) != len(M_FIELDS):
        return defaults
    if any(not 1 <= value <= len(choices) for value, (_, choices) in zip(values, M_FIELDS.values())):
        return defaults
    return dict(zip(M_FIELDS, values))


def page(path):
    controls = ''.join(
        f'<label>{label}<select id="{name}" style="font:inherit;padding:10px">'
        + ''.join(f'<option value="{index}">{choice}</option>' for index, choice in enumerate(choices, 1))
        + '</select></label>' for name, (label, choices) in M_FIELDS.items())
    section = ('<section><h2>M Setup</h2>' + controls
               + '<p class="muted">G80 M Setup simulation. Touch selections and these values are saved per profile across HMI restarts. '
               'This does not control a vehicle or configure M1/M2.</p></section>')
    return (path.read_text().replace('<button id="apply"', section + '<button id="apply"', 1)
            .replace("'climate_on'];", "'climate_on'," + ','.join(json.dumps(name) for name in M_FIELDS) + '];', 1)
            .replace("input.type==='number'?Number(input.value)",
                     "(input.type==='number'||input.tagName==='SELECT')?Number(input.value)", 1)).encode()


def boot_console(root, vm, started_ns):
    home = pathlib.Path(os.environ.get('LIMA_HOME', str(pathlib.Path.home() / '.lima')))
    candidates = sorted((home / vm).glob('serial*.log'), key=lambda path: path.stat().st_mtime_ns, reverse=True)
    candidates.append(root / '.local/linux-dmesg.log')
    serial_text = ''
    for path in candidates:
        if not path.is_file() or path.stat().st_mtime_ns < started_ns:
            continue
        with path.open('rb') as stream:
            stream.seek(max(0, path.stat().st_size - 131072))
            text = stream.read(131072).decode('utf-8', errors='replace')
        text = re.sub(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)', '', text)
        text = re.sub(r'\x1bP.*?\x1b\\', '', text, flags=re.S)
        text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b.', '', text)
        text = re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', '', text)
        if text.strip():
            if path == root / '.local/linux-dmesg.log':
                return '\n'.join((text + '\n' + serial_text).splitlines()[-100:])
            if re.search(r'^\[\s*\d+\.\d+\]', text, re.M):
                return '\n'.join(text.splitlines()[-100:])
            if not serial_text:
                serial_text = text
    return '\n'.join(serial_text.splitlines()[-100:])


def configure_boot(root=pathlib.Path('/')):
    def arguments(text):
        values = [value for value in text.split() if value not in ('quiet', 'rhgb', 'console=hvc0')
                  and not value.startswith(('loglevel=', 'systemd.show_status='))]
        return ' '.join(values + ['console=hvc0', 'loglevel=7', 'systemd.show_status=1'])

    entries = sorted((root / 'boot/loader/entries').glob('*.conf'))
    if not entries:
        raise ValueError('No Fedora boot-loader entries found; refusing to guess the boot configuration')
    configured = 0
    for entry in entries:
        text = entry.read_text()
        if not re.search(r'^options\s+', text, re.M):
            continue
        updated = re.sub(r'^options[^\n]*', lambda match: 'options ' + arguments(match[0][7:]), text, flags=re.M)
        if updated != text:
            atomic_write(entry, updated)
        configured += 1
    if not configured:
        raise ValueError('Fedora boot-loader entries have no kernel options')
    command_line = root / 'etc/kernel/cmdline'
    if command_line.is_file():
        atomic_write(command_line, arguments(command_line.read_text()) + '\n')
    return configured


def active_directory(state):
    profile = (state / 'logs/active-profile.txt').read_text().strip()
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', profile):
        raise ValueError('Invalid active runtime profile')
    return profile, state / 'profiles' / profile / 'mock'


def status(state):
    profile, directory = active_directory(state)
    saved = directory / 'state.json'
    document = validate(json.loads(saved.read_text())) if saved.is_file() else dict(DEFAULTS)
    document.update(m_values(directory))
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
    supplied_m = {name: document[name] for name in M_FIELDS if isinstance(document, dict) and name in document}
    document = validate(document)
    if not (state / 'native-mock/enabled').is_file() or not (state / 'native-mock/libnative-mock.so').is_file():
        raise ValueError('Native mock is not installed/enabled. Run hmi8_gpu_lab/install_native_mock.sh in the prepared GPU lab first.')
    profile, directory = active_directory(state)
    directory.mkdir(parents=True, exist_ok=True)
    document.update({**m_values(directory), **supplied_m})
    secondary = ' · '.join(value for value in (document['artist'], document['album']) if value)
    transport = '\n'.join((document['title'], secondary, document['source'],
                           f"{document['left_temperature']} {document['right_temperature']} {int(document['climate_on'])}", ''))
    atomic_write(directory / 'state.txt', transport)
    if supplied_m:
        atomic_write(directory / 'm-state.txt', ' '.join(str(document[name]) for name in M_FIELDS) + '\n')
    atomic_write(directory / 'state.json', json.dumps(document, ensure_ascii=False, indent=2) + '\n')
    return {'ok': True, 'profile': profile, 'state': document,
            'note': 'Saved for the active profile. Allow about one minute after boot, then approximately one second for updates. No audio is played.'}


M_NATIVE = r'''
#include <sys/mman.h>
#include <cstdlib>

namespace m_mock {
static constexpr std::array<unsigned, 5> limits = {3, 3, 2, 2, 3};
static std::atomic<void *> service(nullptr);
using Values = std::array<unsigned, 5>;

static Values read_values() {
    Values values = {1, 1, 1, 1, 1};
    std::ifstream input("/run/lab-mock/m-state.txt");
    Values saved;
    for (size_t index = 0; index < saved.size(); ++index) {
        if (!(input >> saved[index]) || saved[index] < 1 || saved[index] > limits[index]) return values;
    }
    std::string extra;
    if (input >> extra) return values;
    return saved;
}

static bool write_values(const Values &values) {
    char path[] = "/run/lab-mock/m-state.XXXXXX";
    int descriptor = mkstemp(path);
    if (descriptor < 0) return false;
    std::ostringstream output;
    for (unsigned value : values) output << value << ' ';
    output << '\n';
    std::string text = output.str();
    bool saved = write(descriptor, text.data(), text.size()) == static_cast<ssize_t>(text.size());
    if (fsync(descriptor) != 0) saved = false;
    if (close(descriptor) != 0) saved = false;
    if (saved) saved = std::rename(path, "/run/lab-mock/m-state.txt") == 0;
    if (!saved) unlink(path);
    return saved;
}

struct Description {
    virtual ~Description() = default;
    unsigned selection;
};
static_assert(sizeof(Description) == 16);

static void refresh(void *instance) {
    if (instance && *static_cast<uintptr_t *>(instance) == image_base + 0x104314c0)
        native<void (*)(void *)>(0x9303fcc)(instance);
}

template <size_t Index> static std::unique_ptr<Description> get(void *instance) {
    service = instance;
    auto description = std::make_unique<Description>();
    native<void (*)(void *, unsigned)>(0x9339fe0)(description.get(), read_values()[Index] + 1);
    return description;
}

template <size_t Index> static void set(void *instance, unsigned value) {
    if (value < 1 || value > limits[Index]) return;
    Values values = read_values();
    values[Index] = value;
    if (!write_values(values)) {
        std::fprintf(stderr, "lab-mock: unable to persist M Setup selection\n");
        return;
    }
    service = instance;
    refresh(instance);
}

static void *watch(void *) {
    Values previous = read_values();
    Snapshot snapshot;
    std::atomic<bool> queued(false);
    for (;;) {
        std::this_thread::sleep_for(std::chrono::seconds(1));
        Values current = read_values();
        if (current == previous || !service.load() || queued.exchange(true)) continue;
        if (!object(snapshot, 0)) snapshot = find_objects();
        if (void *application = object(snapshot, 0)) {
            auto dispatch = native<void (*)(void *, std::function<void ()>, std::shared_ptr<void>)>(0x510c568);
            dispatch(application, [&queued] { refresh(service.load()); queued = false; }, {});
            previous = current;
        } else {
            queued = false;
        }
    }
    return nullptr;
}

__attribute__((constructor)) static void install() {
    if (!image_base) return;
    struct Hook { uintptr_t slot; uintptr_t original; uintptr_t replacement; };
    const std::array<Hook, 10> hooks = {{
        {0x104314c0, 0x9300c40, reinterpret_cast<uintptr_t>(&get<0>)},
        {0x104314d8, 0x9300a00, reinterpret_cast<uintptr_t>(&get<1>)},
        {0x104314d0, 0x9300e80, reinterpret_cast<uintptr_t>(&get<2>)},
        {0x104314f0, 0x9301300, reinterpret_cast<uintptr_t>(&get<3>)},
        {0x104314f8, 0x9301540, reinterpret_cast<uintptr_t>(&get<4>)},
        {0x10431530, 0x9301d8c, reinterpret_cast<uintptr_t>(&set<0>)},
        {0x10431550, 0x93029e0, reinterpret_cast<uintptr_t>(&set<1>)},
        {0x10431558, 0x9302e00, reinterpret_cast<uintptr_t>(&set<2>)},
        {0x10431560, 0x9303220, reinterpret_cast<uintptr_t>(&set<3>)},
        {0x10431568, 0x9303640, reinterpret_cast<uintptr_t>(&set<4>)}
    }};
    for (const auto &hook : hooks) {
        if (*reinterpret_cast<uintptr_t *>(image_base + hook.slot) != image_base + hook.original) {
            std::fprintf(stderr, "lab-mock: M Setup signature mismatch; disabled\n");
            return;
        }
    }
    uintptr_t page_size = static_cast<uintptr_t>(sysconf(_SC_PAGESIZE));
    uintptr_t page = (image_base + hooks.front().slot) & ~(page_size - 1);
    if (mprotect(reinterpret_cast<void *>(page), page_size, PROT_READ | PROT_WRITE) != 0) return;
    for (const auto &hook : hooks) *reinterpret_cast<uintptr_t *>(image_base + hook.slot) = hook.replacement;
    if (mprotect(reinterpret_cast<void *>(page), page_size, PROT_READ) != 0)
        std::fprintf(stderr, "lab-mock: unable to restore M Setup table protection\n");
    pthread_t thread;
    if (!pthread_create(&thread, nullptr, watch, nullptr)) pthread_detach(thread);
    std::fprintf(stderr, "lab-mock: persistent M Setup feedback enabled\n");
}
}
'''


if __name__ == '__main__':
    import sys
    if len(sys.argv) == 2 and sys.argv[1] == 'configure-boot':
        print(f'Enabled Linux boot messages in {configure_boot()} boot entries')
    elif len(sys.argv) == 3 and sys.argv[1] == 'native-source':
        print(pathlib.Path(sys.argv[2]).read_text() + M_NATIVE)
    else:
        raise SystemExit('Usage: mock_state.py configure-boot | native-source /path/to/native_mock.cpp')
