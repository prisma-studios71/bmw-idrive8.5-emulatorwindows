# Emulator software updates

Open the settings page (normally `http://localhost:5012`) and use **Software
updates → Check for updates**. The page shows the installed source version,
branch, commit, and whether local changes were included when it was deployed.
It offers links to the project/branch, a comparison when an update is available,
and the release downloads page.

## What is checked

- Git installations compare the **installed commit** with the tracked remote
  branch, not an unrelated branch or merely the latest release number.
- A detached Git commit/tag can be compared with the latest published release.
- Local commits ahead of the remote, diverged histories, unavailable branches,
  unknown revisions, and network/API failures are reported separately. None
  of these is silently treated as “up to date.”
- Local modifications are shown separately: matching the remote commit does
  not imply that an installation containing local changes is identical.
- Folder/ZIP copies without revision metadata show an unknown version. They
  can still open the project/release website, but cannot reliably establish
  whether they contain the latest commit.

The check is manual, read-only, and cached in memory for five minutes. It uses
the public GitHub API without credentials. No firmware, coding values, file
contents, local paths, or Git credentials are sent. GitHub receives ordinary
connection metadata plus the repository, requested branch/tag and commit
identifiers. Private repositories are not authenticated by this feature.

## Install an update from a Git checkout

Save any unsaved coding editor text first, then open Terminal in the Mac's
emulator project folder:

```sh
bash update.sh
```

The script refuses to operate outside this Git checkout, on a detached tag,
with local changes, or without a tracking branch. It runs `git pull --ff-only`,
syncs the resulting source into Lima, and restarts the current profile. It
never resets, cleans, stashes, or switches branches for you. Review the changes
on GitHub before running it.

The existing VM firmware, resources, coding, custom presets, climate/music
mock values, and vehicle-specific saved state stay in the guest state folder;
they are not overwritten by source sync. The update is not transactional: if
Git succeeds but VM sync/start fails, fix that error and rerun
`bash scripts/sync_source.sh`, then `bash start.sh`.

This updates the emulator source/UI only. Releases that require new system
dependencies, a different tools image, or a graphics-driver migration need
their own release instructions; this script does not silently replace them.
It does not install BMW headunit software updates.

For an existing folder/ZIP installation, download the new project files and
run their `install.sh` with the same `BMW_VM` and port settings. An existing VM
skips the firmware import and syncs the new source before starting. Keep your
private BMW files and `.local` data backed up separately. Do not place a new
checkout inside the old checkout.

## Where the version comes from

The container intentionally has no `.git` mount and cannot see the Mac's
checkout. Before setup, import, or source sync copies files into the guest,
`container/updates.py` records a small `container/build-version.json` file.
The running server loads this metadata once at startup, so pulling a newer Mac
checkout without deploying it does **not** incorrectly change the installed
version shown in settings.

`build-version.json` is generated and Git-ignored. It contains no Git remote
credentials or local paths. The tracked GitHub upstream's URL determines the
repository for Git installations; a fork therefore checks its own upstream
remote. Non-GitHub remotes are reported as unsupported rather than contacted.
The default repository for folder copies is set in
`container/update-config.json`. Its optional `version` field can be set to a
real release tag when preparing a ZIP; it is currently unknown, not an invented
release number.

To prepare a standalone Docker source build with revision information, run
this on the Mac first:

```sh
python3 container/updates.py --write container/build-version.json
```

Then build normally. Without this file, the container reports unknown source
identity. Generated metadata describes the source at capture time; editing
files after capturing it requires regenerating it before deployment.
