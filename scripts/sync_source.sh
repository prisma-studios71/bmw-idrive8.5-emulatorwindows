#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/common.sh"
python3 "$ROOT/container/updates.py" --write "$ROOT/container/build-version.json"
COPYFILE_DISABLE=1 tar --no-xattrs --exclude='__pycache__' --exclude='*.pyc' -czf "$ROOT/.local/source.tar.gz" \
    -C "$ROOT" Dockerfile .dockerignore LICENSE NOTICE runtime container web config scripts tools
limactl copy "$ROOT/.local/source.tar.gz" "$VM:/tmp/bmw-source.tar.gz"
limactl shell --workdir=/tmp "$VM" -- sudo tar -xzf /tmp/bmw-source.tar.gz -C /srv/bmw-idrive85/source
limactl shell --workdir=/tmp "$VM" -- sudo sync
printf 'Source updated; restart the selected profile to apply changes.\n'
