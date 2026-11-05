# Validation status

Prepared November 4, 2026 from the existing M1 Pro/macOS 26.7.1 GPU lab.

The package separates the exact tooling image, current wrapper source and
selected extracted runtime from the original research directory. Original
SWFL/SWFK containers, maps, guest SSH host keys, runtime logs and donor
personalization are excluded. The base runtime is retained conservatively,
not minimized solely to files observed in one short process trace.

The original session already demonstrated both native G26 and G80 M interfaces,
Home tiles, touch, custom media text and climate-bar values. That does not,
by itself, validate this new installer or a different Mac.

Package-specific validation results are recorded here after testing. Do not
claim clean-machine or all-M-series validation from source/syntax checks.

Known limitations: no navigation map/backend, AR camera, real Bluetooth/audio,
full climate application or full vehicle emulation; stream rate can be lower
than renderer/capture rate. A previous first G26 launch trapped in shader
upload and succeeded on restart; cold-start reliability is not guaranteed.

## Results — November 4, 2026 (M1 Pro, macOS 26.7.1)

Tested with a fresh Lima/Krunkit VM `bmw-idrive85` created by `setup.sh`,
separate from the original lab VMs:

- First install: G80 M booted; Home, Apps and touch verified
  (`.local/g80-validation.jpg`, `.local/g80-touch-validation.jpg`).
- Repeat install (state moved aside, `setup.sh` run again): G26 booted with
  Home tiles, climate and media mocks (`.local/g26-validation.jpg`).
- Profile switch on the repeat install: `start.sh g80-m` booted the ID8.5
  M Home screen with the Bluetooth mock text (`.local/g80-switch-validation.jpg`),
  tested on alternate ports via `BMW_VIEWER_PORT=5021`.
- `tools/publish_check.py`: 48 public files (~200 KB), no blocked artifacts.

Not validated: a different Mac model, a Mac without the Homebrew build
dependencies, or other M series than G80 LCI.

## Release preparation — November 5, 2026

Validated on the same M1 Pro/macOS 26.7.1, without publishing a repository or
release and without changing either README during this release-preparation
pass:

- Prepared deterministic graphics archives with upstream license texts,
  copyright notices, complete matching Chromium credits and binary provenance.
  Rebuilding produced the same SHA-256 hashes as `config/assets.json`.
- Fourteen focused tests passed for downloads, cache reuse/repair, corrupted
  or missing downloads, archive contents, README preservation and bounded
  installer retry behavior. These temporary tests are retained privately in
  `.local/publication-audit/`, not added as a new public test framework.
- A source-only copy downloaded the graphics through a loopback HTTP server
  standing in for the unpublished GitHub release. A new disposable Lima VM
  imported the extracted BMW backup and built its Docker tooling image from
  the Dockerfile, without an existing runtime or tooling-image archive.
- The first cold trial reproduced the previously documented SIGTRAP during
  G26 shader initialization. A second new-VM installation completed and
  displayed the G26 Home screen. The installer now retries that exit code
  at most twice and preserves failure logs; this mitigates, rather than fixes,
  the proprietary renderer's cold-start problem. Retry bounds were tested
  with simulated statuses; recovery from a naturally occurring trap under
  the revised installer has not yet been observed.
- G26 touch opened the native Apps menu; setting mock state changed the native
  climate bar to 21/22 Celsius. The settings API exposed only `barestock`,
  `full-g26` and `full-g80` presets.
- Repeated installation with the final installer preserved coding and mock
  JSON files byte-for-byte. Removing the host image-ID cache was recovered
  automatically from the image already installed in the VM.
- Switching the disposable VM to G80 M displayed the M3 welcome animation and
  native M Home screen, with effective `HMI_BRAND=bmw_m` and `SERIES=G080LCI`.
  Evidence includes `fresh-g26.jpg`, `fresh-g26-apps.jpg`, `fresh-g80.jpg`,
  `fresh-g80-home.jpg`, API status files and install logs under the private
  audit directory.

This is a new-VM/source-only test, not a test on a clean Mac: Homebrew and
development tools were already installed, and Lima reused its verified Fedora
base-image download cache. Actual GitHub download URLs cannot be smoke-tested
until the owner approves creating the repository and publishing its release.
Neither all Apple Silicon models nor sustained 60 FPS is certified by these
checks. Firmware, maps, VM images and the old research Docker archive are not
public release assets.
