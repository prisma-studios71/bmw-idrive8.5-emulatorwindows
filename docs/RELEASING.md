# Preparing a public release

Only project source goes into Git. Do not upload `private/`, `.local/`, BMW
firmware/extracted backups, maps, VM disks, saved coding state or credentials.
The main README remains owner-maintained.

## One-command installation

After the release is published, a user with an Apple Silicon Mac, macOS 26+,
Homebrew and their own supported BMW files runs:

```sh
bash install.sh /path/to/mgu22filesystem/extracted
```

The script installs its Homebrew dependencies, downloads and verifies the two
graphics archives, imports the supported firmware into a private Lima VM,
builds the open-source Docker tooling image inside that VM, starts the HMI
and opens the viewer. The BMW backup is an input, not a downloadable project
asset. The input requirements and optional G80 resources are described in
`EXTRACTED_FILES.md`. At least 25 GiB must be free before installation, with
additional space for the source backup and no navigation maps included.

First setup needs network access and can take substantially longer than five
minutes, especially when building tooling. The Mac GPU source-build fallback
can add another 15–30 minutes. Homebrew itself and Apple's command-line tools
are prerequisites; this is not an unattended operating-system bootstrapper.
If firmware import completed but driver/tooling setup was interrupted, rerun
the same command: it reinstalls the verified graphics archive and locates or
builds the missing tooling image without overwriting coding or mock state.
An interrupted, incomplete firmware import is still refused rather than
silently overwriting a partial runtime.

The known G26 cold-start SIGTRAP during shader initialization is retried at
most twice during installation, with each failed attempt's logs preserved.
Other HMI exit codes fail explicitly. Success requires ten seconds of
consecutive live, sufficiently sized frames, not just a running web server.
This is bounded recovery, not a fix to the proprietary renderer itself.

## Public assets

The initial version is `v0.1.0`. `config/assets.json` pins downloads to that
release instead of a mutable `latest` URL. Attach only:

- `host-runtime.tar.gz`: Mac KosmicKrisp/virglrenderer libraries and notices.
- `driver.tar.gz`: guest ANGLE/Venus/support libraries, shim source and notices.
- `SHA256SUMS`: the corresponding SHA-256 checksums.

Do not attach the old `runtime.tar.gz` or `tools-image.tar.gz`. The former
contains proprietary firmware. The latter is a research image; the public
installation builds tooling from the project's Dockerfile instead. Loading a
user's existing local image remains supported for private workflows.

`tools/prepare_release.py` accepts only the reviewed binary hashes recorded in
`docs/graphics-provenance.json`; it does not copy a whole driver folder or VM.
Each output includes original upstream license texts, copyright notices and
provenance. The guest archive includes the complete Chromium credits resource
from Playwright Chromium revision 1200, whose ANGLE library hashes match the
reviewed driver. It also carries the Fedora package license files. The guest
Mesa binary came from Fedora Copr `slp/mesa-libkrun-vulkan`.

Maintainer example, with local source/license inputs obtained from those
matching upstream distributions:

```sh
python3 tools/prepare_release.py \
  --licenses /path/to/release-inputs \
  --mesa-source /path/to/mesa-mirror-81d869ccd506ed4edf371bfaba700dc01e54723b \
  --guest-mesa-source /path/to/mesa-25.3.6 \
  --virgl-source /path/to/virglrenderer-0.10.4e-krunkit
```

The license input's `driver-licenses/` directory must contain the Chromium
and ANGLE LICENSE files, the matching complete `chromium-credits.html`, and
the `mesa-vulkan-drivers`, `libwayland-client`, `libxcb`, `libdisplay-info`, and
`vulkan-loader` license directories from the matching installed RPMs. The
preparer rejects absent notices, different binaries and different Chromium
credits. It writes deterministic archives, checksums and a candidate
`assets.json` into ignored `.local/release/`; review the candidate manifest
before updating `config/assets.json`. Never copy these archives into Git.

## Validation and publication order

1. Run `python3 tools/publish_check.py` and source syntax checks.
2. Check every release library against its reviewed hash and inspect archive
   member paths, links and license notices.
3. Test installation from a source-only copy with no `private/` cache or
   existing VM. Before publication a loopback HTTP server can stand in for
   GitHub downloads in the test copy's manifest; keep the public manifest
   unchanged. This tests the download/install flow, not GitHub availability.
4. Confirm viewer frames, touch and profile switching in the isolated VM.
   Preserve the user's existing VM, coding and mock state.
5. Resolve owner-maintained README mismatches before advertising a release.
6. Only after the owner approves publication, push the source and publish the
   pinned release with its verified assets. Smoke-test the real GitHub URLs.

A local test on one M1 Pro is not certification for every Apple Silicon model
or a clean Mac without the prerequisite development tools. Hashes validate
artifact integrity against the manifest, not independent publisher identity
or legal clearance for unrelated firmware.
