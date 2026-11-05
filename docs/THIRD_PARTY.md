# Third-party material and redistribution

The only vendored upstream protocol is
`runtime/ivi-controller-legacy/protocol/ivi-controller.xml`, from COVESA
wayland-ivi-extension tag `1.11.0`, commit
`c9001582b10ce209c37b42dd560947c5aa8928b3`. Its MIT-style permission notice and
DENSO / BMW Car IT copyright notices remain in the XML, unmodified.

Ubuntu, Weston, Mesa, Python, evdev and the other Linux packages are installed
from Ubuntu repositories when building the tooling image. Their package
licenses and notices remain in the image under `/usr/share/doc`.
The public installer builds this image locally; the old research tooling-image
archive is not a public release asset. A user's own local tooling-image cache
can still be loaded by the private-bundle/import paths.

The two graphics release archives contain a `licenses/` directory alongside
their libraries, including upstream license texts, copyright notices and
`provenance.json`. The guest archive also includes Chromium's complete bundled
credits from the same Playwright Chromium build as its ANGLE libraries, plus
the project's EGL/Wayland shim source. Exact reviewed binary hashes and package
versions are recorded in `docs/graphics-provenance.json`. The guest Mesa
library is from Fedora Copr `slp/mesa-libkrun-vulkan`, not stock Fedora Mesa.

BMW/Harman/Qualcomm firmware executables, proprietary shared libraries, CAFD
metadata binaries, map databases, donor NCD dumps, credentials, and activation
tokens must not be committed or copied into the public tooling image.
User-supplied firmware is imported into private guest storage and bind-mounted
into the runtime container. Do not export that storage or commit containers
derived from a running lab. The source documentation contains screenshots of
BMW UI and package-name catalogs; these are not relicensed under MIT, and
their presence does not establish redistribution permission.

This is an unofficial research wrapper, not an official BMW emulator or
vehicle software distribution. Users must supply files they are entitled to
use. Possession of a firmware dump does not itself establish redistribution
rights. Original wrapper code and original project documentation are licensed
under MIT in `LICENSE`, subject to the third-party scope described in `NOTICE`.
Before publishing prebuilt graphics or tooling archives, inventory their
contents and include the applicable upstream licenses, copyright notices,
and any required source or source offers. The wrapper's MIT license alone
does not cover those archives.
