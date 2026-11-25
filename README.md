# Pandipak player updates

Install the group's full SPT 4.1.6 player pack once. Keep the `.msi-player-pack` folder inside your game directory. It records your installed version and backups.

## One-time setup

The current full installer includes **Update Pandipak.cmd**. If you used an older installer, download [Pandipak-Updater.zip](https://github.com/PandizeLive/spt-pandipak/releases/latest/download/Pandipak-Updater.zip) once. Open the downloaded ZIP's Properties, select **Unblock** if Windows shows it, then extract the ZIP.

## Update

Close Tarkov and the SPT Launcher. Double-click **Update Pandipak.cmd** and select the folder containing **EscapeFromTarkov.exe**. The updater finds your installed version, downloads each missing release in order, checks its SHA-256 and runs the pack's existing installer. The installer carries personal settings forward and merges new mod defaults. Re-running the updater shows your current version.

If the updater cannot identify the installed version, use the host's current full installer.

## Publish a player update

Keep the last published full installer. Build and test the next full installer, then use Python 3.11 or later to prepare the release.

```powershell
python publish.py "Previous player installer.zip" "New player installer.zip" v1.2.0 --out release-build
```

Review the changed files for public distribution and test the generated update. Run the command with `--publish` using the publisher's authenticated GitHub CLI to upload it. Players who miss a release can catch up on the next run.
