# Using an extracted filesystem backup

The main README is maintained by the project owner; this document describes the
extracted-folder installer and startup monitor without changing that README.

Keep your extracted folder intact, then run:

```sh
bash install.sh /path/to/mgu22filesystem/extracted
```

Or copy that folder to `bmw-files/extracted/` and run `bash install.sh`.
Passing a folder explicitly takes precedence over `private/runtime.tar.gz`.
An installed VM is never overwritten; use another `BMW_VM` name to test a fresh
installation. No folder is mounted from the Mac at runtime.

Before installation, check the backup locally without creating a VM or
installing dependencies:

```sh
python3 tools/prepare_extracted.py "/path/to/mgu22filesystem/extracted" --check-only
```

This checks the supported executable hash, partition/resource presence and
metadata format. Full archive repair, resource build-marker checks and transfer
integrity checks occur during import; this command is not a complete runtime test.

## What to back up and how assets are loaded

Back up the entire existing `mgu22filesystem/extracted/` directory, including
`emulator-filesystem-metadata.json`. You can leave it on an external drive and
pass its path to `install.sh`; copying it into the emulator project is optional.
The current local backup is approximately 7.3 GiB; this is not the VM size or
the amount copied into the runtime. Maps are not required.

The importer rebuilds the needed Linux filesystem layout inside the VM:

- `ROOT_rootfs/` becomes `/srv/bmw-idrive85/state/rootfs/`.
- `ivi_fs/rootfs/` becomes `state/rootfs/opt/ivi/rootfs/`.
- `ext_fs/rootfs/` becomes `state/rootfs/opt/ext/rootfs/`.
- Selected shared, brand and vehicle resources become `state/resources/`.

Inside the firmware chroot, the launcher mounts the selected resources at
`/var/begu/hmi-data/bmw-shared`, `/var/begu/hmi-data/bmw`, and, for M mode,
`/var/begu/hmi-data/bmwm`, plus the selected vehicle graphics. Hmi8 reads those
normal firmware paths; it does not read files from the browser or Mac backup.
After import you can disconnect the backup drive. Your new coding/mock settings
and saved HMI state live separately in the VM, not in the original extracted files.
Backing up the extracted input does not back up later settings you change in the VM.

Only the open-source project/tooling belongs in a public GitHub repository.
An ignored folder or an external/shared drive does not grant redistribution
rights to the proprietary firmware. Never include private keys or donor state.

The importer uses only:

- `ROOT_rootfs/`, `ivi_fs/rootfs/`, `ext_fs/rootfs/`.
- `swfk_0000a6b0_007_023_004/`, `swfk_0000a6b1_007_023_004/`,
  `swfk_0000aed4_007_023_004/` (shared/BMW/G26 resources).
- Optional `swfk_0000a6b2_007_023_004/` and
  `swfk_0000a691_007_023_004/` for the full G80 M interface.
- Optional `swfk_0000a6aa_007_023_004/` (G82 resources).

Resource folders can contain their extracted `.ext4` image or an already
exported `rootfs/`. Images are mounted read-only inside Linux and copied out.
The tested Hmi8 executable hash is checked and resource build markers must agree.
For extracted files, transfer hashes verify copy integrity, **not BMW signature
authentication or full firmware provenance**. Only release `007_023_004` is supported.
No original SWFL containers, maps, modem/boot-chain images or headunit access are needed.

## Important: Windows extractions

The existing 7-Zip/Windows extraction replaced many Linux symlinks with empty
files and lost permissions. Those files alone are not a faithful Linux backup.
Keep `emulator-filesystem-metadata.json` beside `ROOT_rootfs/`: it records link
targets and permissions recovered from the matching installed VM, without any
file contents. The importer applies these records to a temporary archive; it
does not alter your extracted files. Keep this metadata in your backup too.

To capture metadata from an already-working, matching local VM, once:

```sh
python3 tools/capture_extracted_metadata.py /path/to/extracted --vm bmw-idrive85
```

This is not a solution for an arbitrary unsupported extraction: metadata must
come from the same firmware. Native Linux extractions preserving symlinks and
permissions do not need this repair metadata.

Donor saved state, SSH material, known private-key filenames and special nodes
are excluded. Fresh coding profiles come from the project config. This is not
a comprehensive privacy audit; extracted BMW firmware remains proprietary.

## Boot splash

`start.sh` opens the existing viewer immediately, showing live Linux serial
console output inside its display area. There is no replacement page or spinner.
The HMI initializes behind the console. Once capture contains a non-black frame,
the viewer paints that already-decoded image immediately and continues the normal
HMI stream in the same page, enabling touch controls. There is no deliberate black
pause, page reload, or second first-frame download during handover. The console
remains visible while initial capture frames are black.
The probe checks decoded pixels, not JPEG size, so small boot logos are not
discarded just because they compress well. `/api/status.ready` means the HMI process
is alive and capture has a recent frame; that frame can still be black. The pixel
probe is a display heuristic, not a native BMW boot-logo-ready notification. Native
execution is not paused or replayed, so a brief logo before capture starts cannot
be recovered by this handover.

Expected capture/network errors are not printed during the initial 90-second
wait. If no visible output arrives within that grace period, the viewer shows
a delayed-start warning and available diagnostics rather than hiding a failure
forever. Reboot behavior is unchanged: only `start.sh` runs the host-side
serial-console handover; the settings restart button still restarts the HMI
container, not the Linux VM.

The text is read from the VM's actual `serial.log`, not simulated messages.
On first use, `start.sh` enables `console=hvc0 loglevel=6` in Fedora's kernel
arguments and restarts the VM once. Subsequent boots show kernel and systemd
output directly. Restarting only Hmi8 does not generate another Linux boot log.
This is not a guest framebuffer capture: the current headless Krunkit configuration
has no connected scanout, so framebuffer penguin logos are not captured.
It does not enable a graphical Linux desktop or change the GPU rendering path.
Set `BMW_OPEN_BROWSER=0` to suppress automatic browser opening. The splash
uses the viewer port only until the normal SSH tunnel takes over.
