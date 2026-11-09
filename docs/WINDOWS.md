# Windows port (WSL2)

Experimental. The emulator runs on Windows 10 (2004+) and Windows 11 using WSL2 and
Docker, with the same firmware runtime, coding page and mocks as the Mac version.

> **Status:** the guest-side pieces (software rendering path, touch shim, ARM64
> emulation under qemu-user) were validated in Linux test environments. The full
> flow has not yet been confirmed on real Windows hardware. Please report results
> (CPU, Windows build, x64/ARM64, how long boot took) in an Issue.

## How it works

```
Mac:      macOS → Lima/krunkit VM (ARM64) → privileged Docker container → firmware chroot
                   GPU: Venus/virtio-gpu → KosmicKrisp (Metal)
Windows:  Windows → WSL2 distro "bmw-idrive85" (Ubuntu 24.04) → privileged Docker container → firmware chroot
                   GPU: none passed through → Mesa lavapipe (Vulkan on the CPU) under ANGLE
```

The WSL2 distro plays the role of the Lima VM: Docker runs inside it and the
runtime lives at `/srv/bmw-idrive85` exactly as in the Mac guest, so the same
`scripts/run_guest.sh`, `runtime/launch_guest.sh` and container code are used.
Only two backends differ, selected by environment variables:

| Setting | Mac (default) | Windows |
|---|---|---|
| `HMI_GPU_BACKEND` | `venus` – host GPU through virtio-gpu | `software` – Mesa lavapipe on the CPU |
| `HMI_TOUCH_BACKEND` | `uinput` – kernel virtual touchscreen | `shim` – userspace evdev emulation |

Why the touch shim: the Microsoft WSL2 kernel for ARM64 is built without
`CONFIG_INPUT_EVDEV`, and on x86-64 the ARM64 container runs under qemu-user,
which does not translate evdev/uinput ioctls. `runtime/evdev_touch_shim.c` is
preloaded into Hmi8 only: when Hmi8 opens its touchscreen device it receives a
Unix socket fed by `runtime/touch_guest.py`, and the shim answers the `EVIOC*`
ioctls itself. Firmware files are not modified.

### x64 vs ARM64 Windows

The BMW firmware is ARM64 code.

- **Windows on ARM (Snapdragon X etc.)**: runs natively in WSL2. Recommended.
- **x86-64 PCs (Intel/AMD)**: runs through qemu-user emulation. It works, but
  expect a slow boot (5–20 minutes) and a low frame rate. The default stream
  rate is 10 fps on x64 and 30 fps on ARM64 (`BMW_STREAM_FPS`).

Neither variant uses the Windows GPU. Rendering happens on the CPU, so more cores help.

## Requirements

- Windows 10 version 2004 (build 19041) or newer, or Windows 11; x64 or ARM64
- Virtualization enabled in BIOS/UEFI, WSL2 installed (`wsl --install --no-distribution`
  in an Administrator PowerShell, then reboot). The Microsoft Store WSL is required
  (`wsl --version` must work; run `wsl --update` if it does not).
- 16 GiB RAM recommended, 30 GiB free disk space on the system drive
- Network access during installation
- Your BMW files, prepared as described in [`bmw-files/README.md`](../bmw-files/README.md)

Docker Desktop is **not** needed. The installer sets up its own Docker engine
inside a dedicated distro, so it does not touch your other WSL distros. If you
use Docker Desktop, leave its WSL integration off for `bmw-idrive85`.

## Install

1. Clone or download this repository. If you use Git, line endings are kept
   correct by `.gitattributes`; if the installer complains about CRLF, re-clone with
   `git clone --config core.autocrlf=false <url>`.
2. Put the BMW files into `bmw-files\` (for example `bmw-files\extracted\...`).
   Extractions made on Windows are fine: keep `emulator-filesystem-metadata.json`
   with them, it restores Linux symlinks and permissions during import.
3. Double-click **`install-windows.cmd`**, or run it from a terminal:

   ```bat
   install-windows.cmd
   install-windows.cmd D:\path\to\extracted
   ```

The installer:

1. checks Windows, WSL2, architecture and free space;
2. downloads Ubuntu 24.04 for WSL from `cloud-images.ubuntu.com`, verifies its
   SHA-256 and imports it as the distro `bmw-idrive85`
   (stored in `%LOCALAPPDATA%\bmw-idrive85\wsl`);
3. enables systemd, installs Docker (and `qemu-user-static` on x64);
4. downloads and verifies `driver.tar.gz` (ANGLE and the Vulkan loader; the Mac
   host GPU driver is not needed);
5. verifies and imports your BMW files, builds the ARM64 tools image
   (10–30 minutes on x64 because it is emulated), starts the HMI and opens
   http://localhost:5011.

Running it again skips finished steps.

## Everyday use

| Command | What it does |
|---|---|
| `start-windows.cmd` | Start/resume the current profile |
| `start-windows.cmd g26` / `start-windows.cmd g80-m` | Switch profile (coding is preserved per profile) |
| `stop-windows.cmd` | Stop the HMI container |
| `stop-windows.cmd -Wsl` | Also shut down the WSL distro |
| `sync-windows.cmd` | Copy updated project sources into WSL (after `git pull`), then restart with `start-windows.cmd` |
| `shell-windows.cmd` | Root shell in the distro (logs in `/srv/bmw-idrive85/state/logs`) |
| `uninstall-windows.cmd` | Delete the distro, including firmware import, coding and saved state |

Viewer: http://localhost:5011, coding/settings: http://localhost:5012,
mocks: http://localhost:5012/mocks. WSL2 forwards these ports to Windows
`localhost` automatically.

`start-windows.cmd` also keeps a hidden `wsl.exe` process running so that
WSL does not stop the idle distro (and the emulator with it). `stop-windows.cmd`
ends it.

### Options (environment variables, set before running a `.cmd`)

| Variable | Default | Meaning |
|---|---|---|
| `BMW_VIEWER_PORT` | `5011` | Viewer port; settings use the next port |
| `BMW_STREAM_FPS` | `10` (x64) / `30` (ARM64) | Browser stream frame rate |
| `BMW_RENDER_THREADS` | all CPUs | lavapipe rendering threads |
| `BMW_TOUCH_BACKEND` | `shim` | `uinput` only with a custom WSL kernel that has evdev |
| `BMW_START_TIMEOUT` | `2400` | Seconds the installer waits for the first frame |
| `BMW_OPEN_BROWSER` | `1` | `0` to not open the browser |
| `BMW_WSL_DISTRO` | `bmw-idrive85` | Distro name |

Changing port, frame rate or backends recreates the container automatically;
state and coding live in bind mounts and are kept.

To give WSL more resources, edit `%UserProfile%\.wslconfig`, for example:

```ini
[wsl2]
memory=8GB
processors=8
```

then run `wsl --shutdown` and start again.

## Known limitations

- No GPU acceleration: rendering is CPU-only (lavapipe). Animations are slower
  than on a Mac, especially on x64.
- x64: the "display on/off" mock may not work under qemu-user (it patches the
  running Hmi8 process memory through `/proc`, whose layout depends on how qemu
  maps the guest). The failure is logged in `display-mock.txt`; nothing else is affected.
- First boot of each profile builds shader caches and takes longer.
- Same scope as the Mac version: no navigation maps, no ConnectedDrive, mocks
  are display simulations.

## Troubleshooting

- **"WSL is not installed" / import fails with a virtualization error**:
  enable virtualization (Intel VT-x / AMD-V / SVM) in firmware settings and
  the "Virtual Machine Platform" Windows feature, then reboot.
- **Port 5011 in use**: `set BMW_VIEWER_PORT=5021` then `start-windows.cmd`.
- **The viewer stays black or the installer times out**: open
  `shell-windows.cmd` and check
  `tail -n 80 /srv/bmw-idrive85/state/logs/mesa-g26.stderr.txt` and
  `docker logs bmw-idrive85`. On x64 it may simply need more time:
  `set BMW_START_TIMEOUT=4800`.
- **Touch does nothing**: check `/srv/bmw-idrive85/state/logs/mesa-g26.touch.txt`
  (should say `Touch shim client connected`) and look for `evdev-touch-shim:` in
  `mesa-g26.stderr.txt`.
- **x64: `exec format error`**: ARM64 emulation is not registered. `start-windows.cmd`
  re-registers it; if it persists, re-run `install-windows.cmd`.
