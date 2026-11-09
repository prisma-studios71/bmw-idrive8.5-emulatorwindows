#!/usr/bin/env bash
set -euo pipefail
mode="${1:-baseline}"
case "$mode" in
    baseline|help|mesa|mesa-services|mesa-g26) ;;
    *) printf 'Unknown launch mode: %s\n' "$mode" >&2; exit 2 ;;
esac
# venus: host GPU through virtio-gpu (Mac/krunkit). software: Mesa lavapipe on the CPU (Windows/WSL2).
export HMI_GPU_BACKEND="${HMI_GPU_BACKEND:-venus}"
# uinput: kernel virtual touchscreen. shim: userspace evdev emulation (no evdev or qemu-user).
export HMI_TOUCH_BACKEND="${HMI_TOUCH_BACKEND:-uinput}"
case "$HMI_GPU_BACKEND" in venus|software) ;; *) printf 'Unknown HMI_GPU_BACKEND: %s\n' "$HMI_GPU_BACKEND" >&2; exit 2 ;; esac
case "$HMI_TOUCH_BACKEND" in uinput|shim) ;; *) printf 'Unknown HMI_TOUCH_BACKEND: %s\n' "$HMI_TOUCH_BACKEND" >&2; exit 2 ;; esac
root=/srv/hmi8-lab/rootfs
logs=/mnt/hmi8-lab/logs
width=1920
height=720
coding_flags=''
profile=g26
if [[ "$mode" == mesa-g26 ]]; then
    coding_config="${HMI_CODING_CONFIG:-/mnt/hmi8-lab/coding.json}"
    coding_flags="$(python3 /mnt/hmi8-lab/cafd.py flags --config "$coding_config")"
    read -r width height < <(python3 /mnt/hmi8-lab/cafd.py geometry --config "$coding_config")
    profile="$(python3 /mnt/hmi8-lab/cafd.py profile --config "$coding_config")"
fi
exec 9>/srv/hmi8-lab/launch.lock
if ! flock -n 9; then
    printf 'Another Hmi8 launch is active. Stop it before starting another.\n' >&2
    exit 2
fi
mkdir -p "$logs"
if [[ "$mode" == mesa-g26 ]]; then
    cp "$coding_config" "$logs/$mode.coding-overrides.json"
    printf '%s\n' "$profile" > "$logs/active-profile.txt"
fi
ulimit -c 0
duration=90s
trace=(strace -f -tt -s 200 -o "$logs/$mode.strace")
if [[ "$mode" == mesa-g26 ]]; then
    duration=180s
    trace=()
fi
set +e
timeout --signal=TERM --kill-after=3s "${HMI_TIMEOUT:-$duration}" \
    "${trace[@]}" \
    unshare --mount --pid --fork --net bash -s -- "$root" "$mode" "$logs" "$width" "$height" "$coding_flags" "$profile" \
    > "$logs/$mode.stdout.txt" 2> "$logs/$mode.stderr.txt" <<'GUEST'
set -euo pipefail
root="$1"
mode="$2"
logs="$3"
width="$4"
height="$5"
coding_flags="$6"
profile="$7"
printf 'Lab display: %sx%s\nFLAGS_CONFIG=%s\n' "$width" "$height" "$coding_flags"
mount --make-rprivate /
if [[ "$mode" == mesa-g26 ]]; then
    profile_state="/srv/hmi8-lab/profiles/$profile"
    for area in public personal; do
        if [[ ! -d "$profile_state/$area" ]]; then
            mkdir -p "$profile_state"
            cp -a "$root/var/opt/$area" "$profile_state/$area" 2>/dev/null || mkdir -p "$profile_state/$area"
            printf 'Created saved state for new profile %s (%s)\n' "$profile" "$area"
        fi
    done
    mkdir -p "$root/var/opt/public" "$root/var/opt/personal"
    mount --bind "$profile_state/public" "$root/var/opt/public"
    mount --bind "$profile_state/personal" "$root/var/opt/personal"
    mkdir -p "$root/etc/persod"
    mount --bind "$root/opt/ivi/rootfs/etc/persod" "$root/etc/persod"
    mount -o remount,bind,ro "$root/etc/persod"
fi
mkdir -p "$root/proc" "$root/dev" "$root/run" "$root/tmp"
mount -t proc proc "$root/proc"
mount -t tmpfs -o mode=755,nosuid tmpfs "$root/dev"
for device in null zero random urandom; do
    touch "$root/dev/$device"
    mount --bind "/dev/$device" "$root/dev/$device"
done
mkdir -p "$root/sys" "$root/opt/venus"
if [[ "$HMI_GPU_BACKEND" == venus ]]; then
    test -c /dev/dri/renderD128
    gpu_group="$(stat -c %g /dev/dri/renderD128)"
    mkdir -p "$root/dev/dri"
    mount --bind /dev/dri "$root/dev/dri"
    vulkan_icd=/opt/venus/venus.json
    weston_vulkan_icd=/opt/venus/venus.json
    vulkan_preload=/opt/venus/libvulkan_virtio.so:
else
    gpu_group=4010200
    # Written by entrypoint.sh: the Ubuntu lavapipe ICD, with its library path as seen inside the chroot.
    test -s /srv/hmi8-lab/compat/lvp_icd.json
    vulkan_icd=/opt/lab-compat/lvp_icd.json
    weston_vulkan_icd="$(ls /usr/share/vulkan/icd.d/lvp_icd.*.json | head -n 1)"
    vulkan_preload=
fi
mount --bind /sys "$root/sys"
mount -o remount,bind,ro "$root/sys"
mount --bind /opt/venus "$root/opt/venus"
mount -o remount,bind,ro "$root/opt/venus"
mkdir -p "$root/dev/shm"
mount -t tmpfs -o mode=1777,nosuid,nodev tmpfs "$root/dev/shm"
ln -s /proc/self/fd "$root/dev/fd"
ln -s /proc/self/fd/0 "$root/dev/stdin"
ln -s /proc/self/fd/1 "$root/dev/stdout"
ln -s /proc/self/fd/2 "$root/dev/stderr"
mount -t tmpfs -o mode=755,nosuid,nodev tmpfs "$root/run"
mount -t tmpfs -o mode=1777,nosuid,nodev tmpfs "$root/tmp"
mkdir -p "$root/run/wayland" "$root/var/opt/public/hmi" "$root/var/opt/personal" "$root/var/begu/IBA" "$root/var/data/rsu-shared/rsureleasenotes"
chown 4010200:4010200 "$root/run/wayland" "$root/var/opt/public/hmi"
chmod 700 "$root/run/wayland" "$root/var/opt/public/hmi"
ip link set lo up
if [[ "$mode" == mesa-g26 ]]; then
    python3 /mnt/hmi8-lab/touch_guest.py "$root" "$width" "$height" "$HMI_TOUCH_BACKEND" > "$logs/$mode.touch.txt" 2>&1 &
    touch_pid=$!
    for attempt in $(seq 1 50); do
        if [[ -f "$root/run/lab-touch-device" ]]; then break; fi
        if ! kill -0 "$touch_pid" 2>/dev/null; then exit 5; fi
        sleep 0.1
    done
    [[ -f "$root/run/lab-touch-device" ]]
    mkdir -p "$root/dev/input"
    touch "$root/dev/input/cid-touchscreen"
    if [[ "$HMI_TOUCH_BACKEND" == uinput ]]; then
        touch_device="$(cat "$root/run/lab-touch-device")"
        udevadm settle --timeout=5 || true
        chown 4010200:4010200 "$touch_device"
        chmod 660 "$touch_device"
        mount --bind "$touch_device" "$root/dev/input/cid-touchscreen"
    fi
    # Packages are found by SGBM ID, whatever release version was imported.
    resource_dir() { ls -d /srv/hmi8-lab/resources/swfk_0000"$1"_* 2>/dev/null | sort -V | tail -n 1; }
    for resource in a6b1:hmi-data/bmw a6b0:hmi-data/bmw-shared aed4:hmi-vehicles/G26BEV; do
        package="$(resource_dir "${resource%%:*}")"
        destination="$root/var/begu/${resource#*:}"
        prepared="$package/rootfs"
        [[ -d "$prepared" ]]
        mkdir -p "$destination"
        mount --bind "$prepared" "$destination"
        mount -o remount,bind,ro,nosuid,nodev,noexec "$destination"
    done
    case "$profile" in
        g80lci-*) lci_package="$(resource_dir a691)"; lci_dir=G80LCI ;;
        g82lci-*) lci_package="$(resource_dir a6aa)"; lci_dir=G82LCI ;;
        *) lci_package= ;;
    esac
    if [[ -n "$lci_package" ]]; then
        prepared=$lci_package/rootfs
        if [[ ! -f "$prepared/hmi_version" ]]; then
            printf '%s car graphics package is not imported; run import.sh with it.\n' "$lci_dir" >&2
            exit 6
        fi
        mkdir -p "$root/var/begu/hmi-vehicles/$lci_dir"
        mount --bind "$prepared" "$root/var/begu/hmi-vehicles/$lci_dir"
        mount -o remount,bind,ro,nosuid,nodev,noexec "$root/var/begu/hmi-vehicles/$lci_dir"
        printf '%s vehicle package (%s) mounted read-only.\n' "$lci_dir" "$lci_package"
    fi
    if [[ "$profile" == *-m ]]; then
        prepared="$(resource_dir a6b2)/rootfs"
        if [[ ! -s "$prepared/hmi_version" ]]; then
            printf 'M mode requires SWFK 0000A6B2 (Data HMI ID8 BMW M); run import.sh with it. No substitute brand assets are used.\n' >&2
            exit 6
        fi
        mkdir -p "$root/var/begu/hmi-data/bmwm"
        mount --bind "$prepared" "$root/var/begu/hmi-data/bmwm"
        mount -o remount,bind,ro,nosuid,nodev,noexec "$root/var/begu/hmi-data/bmwm"
        printf 'BMW M brand package (%s) mounted read-only.\n' "$(basename "$(dirname "$prepared")")"
    fi
    if [[ "$profile" == g80-* ]]; then
        g80=/srv/hmi8-lab/resources/swfk_0000987f_036_010_004/rootfs/mnt/dataro/data/hmi8/vehicles/widgetasset/vehicles/G80
        [[ -f "$g80/TRIMA/vehicle/widget.pbw" || -f "$g80/TRIMA/vehicle/vehicle.pbw" || -f "$g80/TRIMA/vehicle/meshes.res" ]]
        for destination in /var/begu/hmi-vehicles/G80 /mnt/dataro/data/hmi8/vehicles/widgetasset/vehicles/G80; do
            mkdir -p "$root$destination"
            mount --bind "$g80" "$root$destination"
            mount -o remount,bind,ro,nosuid,nodev,noexec "$root$destination"
        done
        printf 'Experimental G80 vehicle package mounted read-only; no G80LCI alias and no substitute bmwm brand assets.\n'
    fi
fi
if [[ "$mode" == mesa-g26 ]]; then
    brand=bmw
    if [[ "$profile" == *-m ]]; then
        brand=bmwm
        if [[ ! -f "$root/var/begu/hmi-data/bmwm/hmi_version" ]]; then
            printf 'G80 M mode requires compatible bmwm brand resources; the G80 vehicle graphics package alone is insufficient. No BMW-to-M asset alias was made.\n' >&2
            exit 6
        fi
    fi
    section="config.${brand}_id8_display14_9_2880x960"
    [[ -s "$root/opt/ivi/rootfs/usr/share/hmi/data/ro/$section.pbr" ]]
    cached="$root/var/opt/public/hmi/fallback_config_section"
    if [[ ! -f "$cached" || "$(cat "$cached")" != "$section" ]]; then
        if [[ -f "$cached" ]]; then
            backup="$(mktemp "$cached.previous.XXXXXX")"
            cp -p "$cached" "$backup"
            printf 'Preserved stale cached HMI section in %s\n' "$backup"
        fi
        printf '%s\n' "$section" > "$cached"
        chown 4010200:4010200 "$cached"
        printf 'Initialized lab fallback section for %s: %s\n' "$profile" "$section"
    fi
fi
library_path=/opt/ivi/rootfs/usr/lib/hmi:/opt/ivi/rootfs/usr/lib:/opt/ext/rootfs/usr/lib:/usr/lib:/lib
launcher=(/opt/ivi/rootfs/usr/bin/Hmi8)
activation=()
extra_environment=()
if [[ "$mode" == mesa* ]]; then
    mkdir -p "$root/opt/lab-compat"
    mount --bind /srv/hmi8-lab/compat "$root/opt/lab-compat"
    mount -o remount,bind,ro "$root/opt/lab-compat"
    mkdir -p "$root/opt/lab-ubuntu/lib" "$root/opt/lab-ubuntu/glvnd" "$root/opt/lab-overrides"
    mount --bind /usr/lib/aarch64-linux-gnu "$root/opt/lab-ubuntu/lib"
    mount --bind /usr/share/glvnd "$root/opt/lab-ubuntu/glvnd"
    ln -sfn /opt/lab-ubuntu/lib/libgbm.so.1 "$root/opt/lab-overrides/libgbm.so"
    library_path="/opt/venus/angle:/opt/venus:/opt/lab-overrides:/opt/lab-ubuntu/lib:$library_path"
    launcher=(/opt/lab-ubuntu/lib/ld-linux-aarch64.so.1 --library-path "$library_path" /opt/ivi/rootfs/usr/bin/Hmi8)
    extra_environment=(XDG_SESSION_TYPE=wayland ANGLE_DEFAULT_PLATFORM=vulkan ANGLE_FEATURE_OVERRIDES_DISABLED=supportsIncrementalPresent "VK_DRIVER_FILES=$vulkan_icd" LIBGL_DRIVERS_PATH=/opt/lab-ubuntu/lib/dri __EGL_VENDOR_LIBRARY_FILENAMES=/opt/lab-ubuntu/glvnd/egl_vendor.d/50_mesa.json GCONV_PATH=/opt/lab-ubuntu/lib/gconv)
    extra_environment+=(LD_PRELOAD=/opt/lab-compat/libhmi-bti-compat.so)
    if [[ "$mode" == mesa-g26 ]]; then
        touch_preload=
        if [[ "$HMI_TOUCH_BACKEND" == shim ]]; then
            touch_preload=:/opt/lab-compat/libevdev-touch-shim.so
            extra_environment+=(LAB_EVDEV_DEVICE=/dev/input/cid-touchscreen LAB_EVDEV_SOCKET=/run/lab-evdev.sock "LAB_EVDEV_SIZE=${width}x${height}")
        fi
        extra_environment+=(ECU=mgu_02_a "LD_PRELOAD=/opt/lab-compat/libhmi-bti-compat.so:/usr/lib/libfakecod.so.0:${vulkan_preload}/opt/venus/angle/libegl-wayland-shim.so$touch_preload" LOAD_DEFAULTS=1 "FLAGS_CONFIG=$coding_flags")
        if [[ -f /srv/hmi8-lab/native-mock/enabled ]]; then
            [[ -s /srv/hmi8-lab/native-mock/libnative-mock.so ]]
            expected_hmi=9913ca569bfc78eb2b6174d0660855dc324a7b261667e0b9d20bc9352308062c
            [[ "$(sha256sum "$root/opt/ivi/rootfs/usr/bin/Hmi8" | cut -d' ' -f1)" == "$expected_hmi" ]]
            mkdir -p "$root/opt/lab-mock"
            mount --bind /srv/hmi8-lab/native-mock "$root/opt/lab-mock"
            mount -o remount,bind,ro "$root/opt/lab-mock"
            mkdir -p "$profile_state/mock" "$root/run/lab-mock"
            chown 4010200:4010200 "$profile_state/mock"
            mount --bind "$profile_state/mock" "$root/run/lab-mock"
            extra_environment+=("LD_PRELOAD=/opt/lab-compat/libhmi-bti-compat.so:/usr/lib/libfakecod.so.0:${vulkan_preload}/opt/venus/angle/libegl-wayland-shim.so$touch_preload:/opt/lab-mock/libnative-mock.so")
        fi
    fi
    weston_options=(--renderer=pixman)
    if [[ "$mode" == mesa-g26 && -f /srv/hmi8-lab/controller-bridge/lab-ivi-controller.so ]]; then
        weston_options=(--renderer=pixman --debug --modules=/srv/hmi8-lab/controller-bridge/lab-ivi-controller.so)
    fi
    setpriv --reuid=4010200 --regid=4010200 --groups="$gpu_group" \
        env XDG_RUNTIME_DIR="$root/run/wayland" LIBGL_ALWAYS_SOFTWARE=0 GALLIUM_DRIVER=zink MESA_LOADER_DRIVER_OVERRIDE=zink VK_DRIVER_FILES="$weston_vulkan_icd" LD_LIBRARY_PATH=/opt/venus \
        weston --backend=headless "${weston_options[@]}" --shell=ivi-shell.so \
        --socket=wayland-0 --width="$width" --height="$height" --idle-time=0 --no-config \
        > "$logs/$mode.weston.txt" 2>&1 &
    weston_pid=$!
    for attempt in $(seq 1 50); do
        if [[ -S "$root/run/wayland/wayland-0" ]]; then break; fi
        if ! kill -0 "$weston_pid" 2>/dev/null; then exit 3; fi
        sleep 0.1
    done
    if [[ ! -S "$root/run/wayland/wayland-0" ]]; then exit 4; fi
    if [[ "$mode" == mesa-g26 && "${HMI_SNAPSHOTS:-0}" == 1 ]]; then
        mkdir -p /srv/hmi8-lab/captures
        (
            capture_directory="$(mktemp -d /srv/hmi8-lab/captures/session.XXXXXX)"
            cd "$capture_directory"
            while kill -0 "$weston_pid" 2>/dev/null; do
                sleep 3
                env XDG_RUNTIME_DIR="$root/run/wayland" WAYLAND_DISPLAY=wayland-0 \
                    timeout 10s weston-screenshooter > "$logs/$mode.capture.txt" 2>&1 || true
                for image in *.png; do
                    if [[ -f "$image" ]]; then
                        cp "$image" "$logs/live-frame.next.png"
                        mv "$logs/live-frame.next.png" "$logs/live-frame.png"
                        rm -- "$image"
                    fi
                done
            done
        ) &
    fi
fi
if [[ "$mode" == mesa-g26 && "${HMI_EMBEDDED_COMPOSITOR:-0}" == 1 ]]; then
    activation=(python3 /mnt/hmi8-lab/socket_activation_guest.py "$root/run/wayland/wayland-1")
    extra_environment+=("LISTEN_PID=$$" LISTEN_FDS=1 LISTEN_FDNAMES=hmiec.socket)
fi
if [[ "$mode" == mesa-services || "$mode" == mesa-g26 ]]; then
    mkdir -p "$root/run/dlt-files" "$root/run/someip"
    chmod 777 "$root/run/dlt-files" "$root/run/someip"
    chroot "$root" /usr/bin/env DLT_USER_IPC_PATH=/run/dlt-files \
        /usr/bin/dlt-daemon -c /etc/dlt_MGU22.conf -t /run/dlt-files \
        > "$logs/$mode.dlt.txt" 2>&1 &
    chroot "$root" /usr/bin/env DLT_USER_IPC_PATH=/run/dlt-files \
        /usr/bin/vsomeipd > "$logs/$mode.vsomeip.txt" 2>&1 &
    sleep 1
    chroot "$root" /usr/bin/dlt-receive -a -o "/var/opt/public/hmi/$mode.dlt" 127.0.0.1 \
        > "$logs/$mode.hmi-dlt.txt" 2>&1 &
    if [[ "$mode" == mesa-g26 ]]; then
        chroot "$root" /usr/bin/env \
            LD_LIBRARY_PATH=/opt/ivi/rootfs/usr/lib:/opt/ext/rootfs/usr/lib:/usr/lib:/lib \
            LD_PRELOAD=/usr/lib/libfakecod.so.0 LOAD_DEFAULTS=1 ECU=mgu_02_a \
            "FLAGS_CONFIG=$coding_flags" DLT_USER_IPC_PATH=/run/dlt-files \
            /opt/ivi/rootfs/usr/bin/persod --ecu="${HMI_PERSONALIZATION_ECU:-rse}" \
            > "$logs/$mode.persod.txt" 2>&1 &
    fi
    sleep 1
fi
if [[ "$mode" == help ]]; then
    arguments=(--help)
else
    arguments=(-ap=/opt/ivi/rootfs/usr/lib/hmi/applet -ro=/opt/ivi/rootfs/usr/share/hmi/data/ro/ -rw=/var/opt/public/hmi/ -ibaroot=/var/begu/IBA -rsurn=/var/data/rsu-shared/rsureleasenotes -lm=ramses_thread)
    if [[ "$mode" == mesa-g26 ]]; then
        if [[ "$profile" == g80lci-* || "$profile" == g82lci-* ]]; then
            brand=bmw
            if [[ "$profile" == *-m ]]; then brand=bmwm; fi
            lci_dir=G80LCI; [[ "$profile" == g82lci-* ]] && lci_dir=G82LCI
            arguments+=("-brand=$brand" -vp=/var/begu/hmi-vehicles/$lci_dir)
        elif [[ "$profile" == g80-* ]]; then
            brand=bmw
            if [[ "$profile" == g80-m ]]; then brand=bmwm; fi
            arguments+=("-brand=$brand" -vp=/var/begu/hmi-vehicles/G80)
        else
            brand=bmw
            if [[ "$profile" == *-m ]]; then brand=bmwm; fi
            arguments+=("-brand=$brand" -vp=/opt/ivi/rootfs/usr/share/hmi/data/ro/vehicles/widgetasset/vehicles/G26BEV)
        fi
        python3 /mnt/hmi8-lab/display_state_guest.py > "$logs/$mode.display-state.txt" 2>&1 &
    fi
fi
exec "${activation[@]}" chroot --groups="$gpu_group" --userspec=hmi_id8main:hmi_id8main "$root" /usr/bin/env -i \
    PATH=/usr/bin:/bin LC_ALL=C HOME=/tmp \
    DISABLE_UPDATER_THREAD=1 XDG_RUNTIME_DIR=/run/wayland \
    LD_LIBRARY_PATH="$library_path" DLT_USER_IPC_PATH=/run/dlt-files \
    HMI_TOUCH_INPUT_DEVICE=/dev/input/cid-touchscreen \
    "${extra_environment[@]}" "${launcher[@]}" "${arguments[@]}"
GUEST
result=$?
set -e
printf '%s\n' "$result" > "$logs/$mode.exit-code.txt"
dlt_source="$root/var/opt/public/hmi/$mode.dlt"
if [[ "$mode" == mesa-g26 ]]; then
    dlt_source="/srv/hmi8-lab/profiles/$profile/public/hmi/$mode.dlt"
fi
if [[ -f "$dlt_source" ]]; then
    cp "$dlt_source" "$logs/$mode.dlt"
fi
printf 'HMI %s exit code: %s\n' "$mode" "$result"
tail -n 60 "$logs/$mode.stdout.txt" "$logs/$mode.stderr.txt"
exit "$result"
