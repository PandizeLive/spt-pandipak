# Pandipak for SPT 4.1.6

**[Download SPTpp Launcher for Windows](https://github.com/PandizeLive/spt-pandipak/releases/download/launcher-v1.0.1/SPTpp-Launcher.exe)**

## One-time setup

Open the EXE and select your SPT 4.1.6 player folder (EFT build 40743). If you need SPT, choose the official installer option and use your own Tarkov installation. After installing SPT, select its folder.

Click **Install Pandipak**. The launcher prepares **Backports1**, **Backports2**, **Backports3** and **Misc** automatically. The installer also fills the local cache for remote play. The SPT 4.1.6 bundle set occupies about 17 GiB once installed. Downloads and temporary extraction require additional space. Keep the game folder between updates so verified files can be reused. All four groups use the same release manifest. The installer checks the player files before applying them. Enter the connection details your host gives you in the normal SPT server selector.

The public release fetches third-party mod files directly from their pinned author downloads. [Player mod credits and download links](CREDITS.md)

## Update

Open **SPTpp Launcher**. It checks GitHub on startup. Click **Check for updates** to check again. When an update is available, close Tarkov and click the gold-bordered **Update Pandipak** button. The installer carries personal settings forward and merges new mod defaults. Keep the `.msi-player-pack` folder with your game for its update receipt and backups. Existing players can continue using **Update Pandipak.cmd**.

Launcher 1.0.0 users can close it and replace the EXE once using the download above. Starting with launcher 1.0.1, **Update launcher** appears when a newer executable is available. It verifies the download and reopens the same installation. Host-managed installations can also check the latest published player-pack version.

If a mod author removes a pinned download or its contents change, first installation stops and identifies the source. Retry after the host restores a verified source.

Maintainers can find the build and verification steps in the [release guide](docs/releasing.md).
