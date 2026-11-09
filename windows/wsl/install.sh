#!/usr/bin/env bash
# Windows port installer, WSL side. Called by windows/install.ps1 after provision.sh.
#   bash windows/wsl/install.sh [/path/to/bmw-files-or-extracted]
# Mirrors install.sh + import.sh from the Mac flow, with the WSL distro as the "VM".
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
FILES="${1:-$ROOT/bmw-files}"
ensure_docker
ensure_arm64

say 'Getting the open-source graphics pieces'
python3 "$ROOT/tools/fetch_asset.py" driver.tar.gz \
    || fail 'Could not verify/download driver.tar.gz (ANGLE + Vulkan loader). Check the network and try again.'
ok 'ARM64 guest graphics libraries verified (the Mac-only host GPU driver is not needed)'

say 'Finding your BMW files'
installed=false
[[ -e "$BASE/state/rootfs" ]] && installed=true
plan="$WORK/import-plan.json"
extracted=''
if $installed; then
    ok "Already imported into $BASE/state; skipping (run uninstall-windows.cmd to start over)"
else
    [[ -d "$FILES" ]] || fail "Folder not found: $FILES"
    [[ ! -e "$BASE/state" ]] || fail "$BASE/state exists but is incomplete. Inspect or remove it before importing again."
    extracted="$(python3 "$ROOT/tools/prepare_extracted.py" "$FILES" --detect)"
    if [[ -n "$extracted" ]]; then
        python3 "$ROOT/tools/prepare_extracted.py" "$extracted" --check-only \
            || fail 'Extracted backup is incomplete; see docs/EXTRACTED_FILES.md.'
        ok "Extracted layout and Hmi8 match the supported release in $extracted"
    else
        python3 "$ROOT/tools/find_packages.py" "$FILES" --plan "$plan" >/dev/null 2>"$WORK/find-errors.txt" || {
            cat "$WORK/find-errors.txt" >&2
            fail "The BMW packages were not found or incomplete in $FILES. See bmw-files/README.md."; }
        ok "Found a complete, verified package release in $FILES"
    fi
fi

say 'Importing the firmware runtime (first time: 10-30 minutes)'
if $installed; then
    ok 'Already done'
else
    staging="$WORK/staging"
    rm -rf "$staging" "$WORK/extracted-import"
    mkdir -p "$staging/source"
    chmod 700 "$staging"
    if [[ -n "$extracted" ]]; then
        python3 "$ROOT/tools/prepare_extracted.py" "$extracted" --plan "$plan"
    fi
    python3 - "$plan" <<'PY' > "$WORK/import-items.tsv"
import json, sys
for item in json.load(open(sys.argv[1]))['items']:
    print('\t'.join([item['container'], item['kind'], item['sgbm'], item['version'], item['artifact'], str(item['size'])]))
PY
    while IFS=$'\t' read -r container kind sgbm version artifact size; do
        printf '  %s %s (%d MB)\n' "$(printf %s "$sgbm" | tr a-f A-F)" "$artifact" "$((size / 1000000))"
        if [[ "$kind" == extracted ]]; then
            cp "$artifact" "$staging/$sgbm.gz"
        else
            python3 "$ROOT/tools/stream_artifact.py" "$container" "$kind" "$sgbm" "$version" "$artifact" > "$staging/$sgbm.gz"
        fi
    done < "$WORK/import-items.tsv"
    copy_source "$staging/source"
    python3 "$staging/source/tools/build_runtime_guest.py" "$plan" "$staging" "$staging/source" --into "$BASE"
    mkdir -p "$BASE/source"
    cp -a "$staging/source/." "$BASE/source/"
    rm -rf "$staging" "$WORK/extracted-import"
    ok "Runtime built in $BASE/state"
fi

say 'Installing source, graphics libraries and the tools image'
copy_source "$BASE/source"
if [[ ! -f "$BASE/driver/venus.json" ]]; then
    tar -xzf "$ROOT/private/driver.tar.gz" -C "$BASE"
fi
ok 'Graphics libraries installed'
if image="$(tools_image)"; then
    ok "Tools image present ($image)"
elif [[ -f "$ROOT/private/tools-image-arm64.tar.gz" ]]; then
    docker load -i "$ROOT/private/tools-image-arm64.tar.gz" | tee "$WORK/tools-load.txt"
    sed -n 's/^Loaded image\( ID\)\?: //p' "$WORK/tools-load.txt" | tail -n 1 > "$WORK/tools-image-id"
    tools_image >/dev/null || fail 'Loading private/tools-image-arm64.tar.gz did not produce a usable image.'
else
    build_tools_image
fi

say 'Starting the HMI'
run_profile current

say "Waiting for the HMI to appear ($([[ "$HOST_ARCH" == x64 ]] && echo 'emulated ARM64: 5-20 minutes' || echo 'about 2-5 minutes'))"
deadline=$((SECONDS + ${BMW_START_TIMEOUT:-2400}))
boot_retries=0
stable_since=0
while true; do
    set +e
    python3 - "$VIEWER_PORT" <<'PY' 2>/dev/null
import json, sys, urllib.request
port = sys.argv[1]
status = json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/api/status', timeout=5))
exit_code = status.get('hmi_exit_code')
if exit_code is not None:
    sys.exit(75 if exit_code == 133 else 76)
frame = urllib.request.urlopen(f'http://127.0.0.1:{port}/frame.jpg', timeout=10).read()
sys.exit(0 if status.get('ready') and len(frame) > 30000 else 1)
PY
    status=$?
    set -e
    if [[ "$status" -eq 0 ]]; then
        if [[ "$stable_since" -eq 0 ]]; then stable_since=$SECONDS; fi
        if [[ $((SECONDS - stable_since)) -ge 10 ]]; then break; fi
    else
        stable_since=0
        if [[ "$status" -eq 75 && "$boot_retries" -lt 2 ]]; then
            boot_retries=$((boot_retries + 1))
            printf '  Startup trapped during shader initialization; saving logs and retrying (%s/2).\n' "$boot_retries"
            destination="$BASE/state/logs/installer-startup-retry-$boot_retries-$(date +%s)"
            mkdir -p "$destination"
            cp -a "$BASE"/state/logs/mesa-g26.* "$destination/" 2>/dev/null || true
            docker restart -t 15 bmw-idrive85 >/dev/null
        elif [[ "$status" -eq 75 || "$status" -eq 76 ]]; then
            fail "Hmi8 stopped during startup. Logs: $BASE/state/logs (open with: shell-windows.cmd)"
        fi
    fi
    [[ $SECONDS -lt $deadline ]] || fail "The HMI did not appear in time. Logs: $BASE/state/logs (see docs/WINDOWS.md, Troubleshooting)"
    if (( SECONDS / 10 % 3 == 0 )); then printf '  still starting (%s s)...\n' "$SECONDS"; fi
    sleep 10
done
ok "Running. Viewer: http://localhost:$VIEWER_PORT   Settings: http://localhost:$SETTINGS_PORT"
