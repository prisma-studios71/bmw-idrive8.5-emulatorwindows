#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VM="${BMW_VM:-bmw-idrive85}"
VIEWER_PORT="${BMW_VIEWER_PORT:-5011}"
SETTINGS_PORT="$((VIEWER_PORT + 1))"
export DYLD_LIBRARY_PATH="$ROOT/private/host-runtime"
export VK_DRIVER_FILES="$ROOT/.local/kosmickrisp_icd.json"
export PYTHONDONTWRITEBYTECODE=1
mkdir -p "$ROOT/.local"
lima_start() {
    python3 - "$@" <<'PY'
import subprocess
import sys
sys.exit(subprocess.run(['limactl', 'start', *sys.argv[1:]], start_new_session=True).returncode)
PY
}
python3 - "$ROOT" <<'PY'
import json
import pathlib
import sys
root = pathlib.Path(sys.argv[1])
driver = root / 'private/host-runtime/libvulkan_kosmickrisp.dylib'
(root / '.local/kosmickrisp_icd.json').write_text(json.dumps({
    'file_format_version': '1.0.1',
    'ICD': {'api_version': '1.4.367', 'library_path': str(driver)},
}, indent=2) + '\n')
PY
