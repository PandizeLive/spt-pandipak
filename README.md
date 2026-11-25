# Pandipak player updates

Install the group's full SPT 4.1.6 player pack once. Keep the `.msi-player-pack` folder inside your game directory. It records your installed version and backups.

## One-time setup

1. Accept the host's invitation to this private GitHub repository.
2. Install [GitHub CLI](https://cli.github.com/) and run `gh auth login`. Choose GitHub.com and sign in with your own account.
3. The current full installer already includes **Update Pandipak.cmd**. If you used an older installer, download **Pandipak-Updater.zip** from the [latest release](https://github.com/PandizeLive/spt-pandipak/releases/latest). Windows may mark browser downloads as coming from the internet. Open the trusted ZIP's Properties, select **Unblock** if shown, then extract it.

## Update

Close Tarkov and the SPT Launcher. Double-click **Update Pandipak.cmd** and select the folder containing **EscapeFromTarkov.exe**. The updater finds your installed version, downloads each missing release in order, checks its SHA-256 and runs the pack's existing installer. The installer carries personal settings forward and merges new mod defaults. Re-running the updater shows your current version.

If GitHub reports that the repository is missing, check the invitation and the account shown by `gh auth status`. If the updater cannot identify the installed version, use the host's current full installer.

## Publish a player update

Keep the last published full installer. Build and test the next full installer, then use Python 3.11 or later to prepare the release.

```powershell
python publish.py "Previous player installer.zip" "New player installer.zip" v1.2.0 --out release-build
```

Review the changed files and test the generated update. Repeat the command with `--publish` to upload it to the private repository. Each release starts at the preceding full installer's exact version, so players can skip a session and catch up later.
