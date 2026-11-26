# Publishing Pandipak releases

The launcher EXE, installer bootstrap and player update have separate release tags. Mark only the player update as Latest. Keep historical release assets available for installed launchers and pinned recipes. The launcher checks the root `full-install.json` and applies incremental updates from the receipt left by the bootstrap.

## Publish a player update

Keep the last published full installer. Build and test the next full installer, then use Python 3.11 or later to prepare the release.

```powershell
python tools/publish.py "Previous player installer.zip" "New player installer.zip" v1.2.0 --out release-build
```

Review the changed files for public distribution and test the generated update. Run the command with `--publish` using the publisher's authenticated GitHub CLI to upload it. Players who miss a release can catch up on the next run.

### Rebuild the first-install volumes

Run the following in the repository with Python 3.11 or newer. The recipe maps player files to pinned author archives. The locations file maps archive names to local paths and stays on the build machine.

```powershell
python tools/build_bundle_cache.py server-bundles.json server-hashes.json archive-inputs.json bundle-cache.json --seven "C:/Program Files/7-Zip/7z.exe"
python tools/build_full.py "Player installer.zip" recipe.json locations.json staging INSTALLER_TAG --seven "C:/Program Files/7-Zip/7z.exe"
python tools/build_volumes.py "Player installer.zip" staging/Pandipak-full.zip staging/local-validation.json volumes INSTALLER_TAG --bundles bundle-cache.json
```

The default build uses pinned author downloads for third-party files. Add `--complete` to the second command to produce an offline kit containing the mod files. Both builds use the same file checksums. Keep the four ZIPs from each build together. Publish the matching `full-install.json` with its release, and keep the mod-update release marked latest so older updaters can still find their index.

Replace `INSTALLER_TAG` with the new installer release tag. Capture the live SPT bundle manifest from `/singleplayer/bundles`. Supply a JSON list of server file hashes with fields `mod`, `name` (relative to the mod's bundles folder), and `sha`. The private archive inputs are a JSON list with fields `mod`, `path`, `url`, and `sha256`. Only the resulting bundle recipe goes in the public bootstrap. The installer downloads pinned author archives and verifies each extracted bundle against the server hash before placing it in the launcher's cache.

When reusing an existing volume, keep its published URL and checksum. Upload and verify the new bootstrap before changing the root pointer. Check the newest public player receipt before generating an incremental release so players on that version have an upgrade path.
