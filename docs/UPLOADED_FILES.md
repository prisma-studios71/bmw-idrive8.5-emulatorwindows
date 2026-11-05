# What the supplied BMW files are used for

This inventory describes the files currently supplied in
`mgu22filesystem/originalfiles` and `mgu22filesystem/extracted`, not every
package in PSdZData. Roles are based on the supplied package manifests,
extracted inventories, the local SGBM-name catalog, and the actual importer.
An identifiable package is not automatically compatible or needed.

## Core software used by this emulator

- **SWFL `00009FF7`, `007_023_004` — ROOT.** The package contains the main Linux
  root filesystem and additional headunit boot/SoC firmware. The emulator
  imports `extracted/ROOT_rootfs/`; it does not boot the Snapdragon boot chain.
- **SWFL `00009FC6`, `007_023_004` — IVI application filesystem.** Extracted as
  `ivi_fs/rootfs/`. Contains `usr/bin/Hmi8`, HMI libraries, applet definitions,
  supporting services and shared data. This is where the actual HMI program is.
- **SWFL `00009FF9`, `007_023_004` — EXT filesystem.** Extracted as
  `ext_fs/rootfs/`. Provides additional software/libraries alongside ROOT and
  IVI. The importer places it under the firmware's `/opt/ext/rootfs` path.

These three form the firmware environment. They are not coding presets or
separate vehicle models. The VM's own Fedora kernel is separate from them.

## HMI appearance and vehicle graphics

These are SWFK resource packages, not replacement HMI executables. The following
packages use release `007_023_004` in the working setup:

- **`0000A6B0` — `hmi-data.bmw-shared`.** Common/shared HMI resources used by
  the supported brand configurations.
- **`0000A6B1` — `hmi-data.bmw`.** Ordinary BMW-brand resources. Used for G26;
  the G80 setup also retains the shared/BMW resource foundation.
- **`0000A6B2` — `hmi-data.bmwm`.** BMW M-brand HMI resources. This is the
  additional package needed for the M-specific interface; G80 car graphics
  alone do not supply it.
- **`0000AED4` — `hmi-vehicles.g26bev`.** Vehicle graphics for the G26 BEV/i4.
  Used by the working G26 profile.
- **`0000A691` — `hmi-vehicles.g80lci`.** G80 LCI/M3 vehicle graphics. The
  `007_023_004` copy is used by the working G80 M profile. The supplied
  `007_022_012` copy is an older alternative, not the selected package.
- **`0000A6AA` — `hmi-vehicles.g82lci`.** G82 LCI/M4 graphics. Optional input
  supported by the importer, but not selected by the current G26/G80 profiles.
- **`0000987F`, `036_010_004` — original G80 M-GmbH vehicle graphics.** This
  was the earlier non-LCI G80 candidate. Its extracted layout/resource version
  differs from the current working set. The working G80 profile uses A691 LCI
  plus A6B2, not this older package. It is not the entire BMW M interface.

Do not substitute a package just because its vehicle name looks similar. The
installer currently supports the matched `007_023_004` resource set.

## Other uploaded packages not imported for the current HMI

- **SWFL `00009FC4`, `007_023_004` — `mgu22-node1-sa8155` filesystem.**
  Extracted as `node1_fs/`. A separate headunit filesystem; its precise full
  service role is not established by this inventory. The emulator does not
  import it.
- **SWFL `00009FC5`, `007_023_004` — RSU filesystem.** Extracted as `rsu_fs/`;
  associated with the headunit's remote-software-update subsystem. It is not
  the emulator's GitHub update feature and is not imported.
- **SWFL `00009FC7`, `007_023_004` — OAP filesystem.** Extracted as `oap_fs/`.
  The manifest identifies its partition name, not a complete explanation of
  its services. It is not imported.
- **SWFL `00009FC8`, `038_022_000` — M4 firmware archive.** Extracted under
  `fc8_m4/`; its manifest names `bmw_mgu_m4_2m_38.22.0_for_pdx.tar.bin`.
  This is not the G82 BMW M4 vehicle-graphics package. It is not imported.
- **SWFL `00009FC9`, `004_002_019` — Marvell PHY firmware archives.**
  Extracted under `fc9_phy/`; includes signed/unsigned 88Q5050 PHY variants.
  Not needed for the virtual graphics/runtime setup and not imported.
- **SWFK `00009FD1`, `007_020_007` — BMW IBA animations/videos.**
- **SWFK `0000A7E4`, `007_020_007` — IBA texts/graphics for the 3/4-series
  family.**
- **SWFK `0000A7E6`, `007_020_007` — common IBA animations/videos.**
  These last three are integrated-owner's-manual content. They are not the M
  theme or navigation maps and are not imported by the current installer.

`ff7_boot/` holds other extracted ROOT-package artifacts such as boot images
and SoC firmware. Those are preserved research inputs, not files the current
Lima VM boots.

## Backup, metadata and extraction helper files

- **`emulator-filesystem-metadata.json`** records Linux permissions and symlink
  targets for repairing the supplied flattened extraction. Keep it with the
  backup. It contains neither the HMI program nor a coding preset.
- **`ROOT_rootfs.zip`, `ivi_fs.zip`, `ext_fs.zip`** are backup archives of the
  filesystem folders. The current extracted-folder installer expects the
  unpacked directory layout; these ZIPs are not additional runtime components.
- **`_swfl_manifests/`** contains the original package artifact manifests used
  to identify and check the supplied payloads; it is not a runnable partition.
- **`root_bmw_filelist.txt`, `ivi_filelist.txt`** are inventories, not software.
- **`resource_profiles.json`** records earlier research resource mappings; the
  current installer uses its own verified import plan.
- **`README.md`, `RESOURCE_EXTRACTION.md`** explain earlier extraction work.
  Their historical G80 findings predate the working A691/A6B2 combination.
- A resource folder's **`.ext4`** file is its filesystem image; its **`rootfs/`**
  is an exported copy. The extracted installer accepts the supported image or
  exported-rootfs layout. Manifest/signature/extraction inventory files are
  supporting records, not additional themes.
- **`.DS_Store`** is Finder metadata and has no emulator function.

## Project JSON versus BMW packages

- `config/barestock.json`, `config/full-g26.json`, `config/full-g80.json` are
  emulator coding templates. They select options but do not contain firmware,
  graphics, navigation databases or complete vehicle services.
- `config/assets.json` is the installer's open-source download/checksum
  manifest. It must remain in the project, but is not listed as a coding preset.
- The former `gpu-g26` and `gpu-g80-m` entries were generated coding snapshots,
  not graphics drivers. Identical copies are hidden and no longer generated.
  Actual per-vehicle saved coding/state is kept separately and remains intact.

For the minimum extracted backup layout, see `EXTRACTED_FILES.md`. Nothing
in this inventory authorizes distributing proprietary BMW firmware; keep it
and private headunit data out of the public project repository.
