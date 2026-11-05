#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/common.sh"
base=/srv/bmw-idrive85
driver="$ROOT/private/driver.tar.gz"
[[ -f "$driver" ]] || { printf 'Missing verified graphics archive: %s\n' "$driver" >&2; exit 1; }
limactl copy "$driver" "$VM:/tmp/bmw-driver-install.tar.gz"
limactl shell --workdir=/tmp "$VM" -- sudo sh -ec "tar -xzf /tmp/bmw-driver-install.tar.gz -C $base; rm /tmp/bmw-driver-install.tar.gz"
image_exists() {
    limactl shell --workdir=/tmp "$VM" -- sudo docker image inspect "$1" >/dev/null 2>&1
}
image="${BMW_TOOLS_IMAGE:-$(cat "$ROOT/.local/tools-image-id" 2>/dev/null || true)}"
if [[ -n "${BMW_TOOLS_IMAGE:-}" ]]; then
    image_exists "$image" || { printf 'Requested BMW_TOOLS_IMAGE is not installed in the VM: %s\n' "$image" >&2; exit 1; }
elif [[ -z "$image" ]] || ! image_exists "$image"; then
    if image_exists bmw-idrive85-tools:local; then
        image=bmw-idrive85-tools:local
    elif image_exists sha256:d7d89513b9fa8c2631b6ebfbdcf60fa3a38af605ab995440330f4820e10e58e1; then
        image=sha256:d7d89513b9fa8c2631b6ebfbdcf60fa3a38af605ab995440330f4820e10e58e1
    else
        printf 'Building the open-source tooling image inside the VM (resuming setup).\n'
        limactl shell --workdir=/tmp "$VM" -- sudo docker build -t bmw-idrive85-tools:local "$base/source"
        image=bmw-idrive85-tools:local
    fi
fi
limactl shell --workdir=/tmp "$VM" -- sudo docker image inspect --format '{{.Id}}' "$image" > "$ROOT/.local/tools-image-id.part"
mv "$ROOT/.local/tools-image-id.part" "$ROOT/.local/tools-image-id"
printf 'Graphics driver and tooling image verified in the VM.\n'
