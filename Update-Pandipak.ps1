param([string]$Game)
$ErrorActionPreference = 'Stop'
$repo = 'PandizeLive/spt-pandipak'
if (!(Get-Command gh -ErrorAction SilentlyContinue)) { throw 'Install GitHub CLI from https://cli.github.com and run gh auth login once.' }
if (!$Game) {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = 'Select the player folder that contains EscapeFromTarkov.exe'
    $dialog.ShowNewFolderButton = $false
    try { if ($dialog.ShowDialog() -ne 'OK') { return }; $Game = $dialog.SelectedPath } finally { $dialog.Dispose() }
}
$Game = (Resolve-Path -LiteralPath $Game).Path
$receipt = Join-Path $Game '.msi-player-pack/installed.json'
if (!(Test-Path -LiteralPath $receipt)) { throw 'Run the full Pandipak player installer first.' }
function Read-ReleaseApi([string]$Route, [string]$Filter) {
    $lines = & gh api --hostname github.com --paginate "repos/$repo/releases$Route" --jq $Filter
    if ($LASTEXITCODE) { throw 'GitHub access failed. Accept the private repo invitation and run gh auth login.' }
    return $lines
}
function Get-Checksum([string]$Path) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        $stream = [IO.File]::OpenRead($Path)
        try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
        finally { $stream.Dispose() }
    } finally { $algorithm.Dispose() }
}
$latest = Read-ReleaseApi '/latest' '.tag_name'
$versions = @{}
$steps = @{}
foreach ($line in (Read-ReleaseApi '?per_page=100' '.[] | select(.draft == false and .prerelease == false) | {tag: .tag_name, body: .body} | @json')) {
    $release = $line | ConvertFrom-Json
    foreach ($entry in ($release.body -split '\r?\n')) {
        if ($entry -notmatch '^Pandipak-Update ([a-f0-9]{64}) ([a-f0-9]{64}) ([a-f0-9]{64})$') { continue }
        $from,$to,$sha = $Matches[1],$Matches[2],$Matches[3]
        if ($steps.ContainsKey($from)) { throw 'Two releases claim the same starting version. Contact the host.' }
        $steps[$from] = @{ Tag=$release.tag; Next=$to; Sha=$sha }
        $versions[$release.tag] = $to
    }
}
if (!$versions.ContainsKey($latest)) { throw 'Latest release has no verified update metadata.' }
$current = Get-Checksum $receipt
$seen = @{}
while ($current -ne $versions[$latest]) {
    if ($seen.ContainsKey($current) -or !$steps.ContainsKey($current)) { throw 'This pack has no update path. Run the current full installer.' }
    $seen[$current] = $true
    $step = $steps[$current]
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    $temp = [IO.Path]::Combine($tempRoot, 'pandipak-' + [guid]::NewGuid().ToString('N'))
    [void][IO.Directory]::CreateDirectory($temp)
    try {
        Write-Host "Downloading $($step.Tag)..."
        & gh release download $step.Tag --repo $repo --pattern 'Pandipak-update.zip' --dir $temp
        if ($LASTEXITCODE) { throw 'Release download failed.' }
        $zip = Join-Path $temp 'Pandipak-update.zip'
        if ((Get-Checksum $zip) -ne $step.Sha) { throw 'Release checksum mismatch.' }
        $kit = Join-Path $temp 'kit'
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [IO.Compression.ZipFile]::ExtractToDirectory($zip, $kit)
        & "$kit/runtime/python.exe" -I "$kit/setup.py" $Game
        if ($LASTEXITCODE) { throw 'Pack verification failed. See the installer message above.' }
        $current = Get-Checksum $receipt
        if ($current -ne $step.Next) { throw 'Installed receipt differs from the published release.' }
    } finally {
        $resolved = (Resolve-Path -LiteralPath $temp).Path
        if ([IO.Path]::GetDirectoryName($resolved).TrimEnd('\') -eq $tempRoot.TrimEnd('\') -and
            [IO.Path]::GetFileName($resolved) -match '^pandipak-[0-9a-f]{32}$') { Remove-Item -LiteralPath $resolved -Recurse -Force }
    }
}
Write-Host "Pandipak is current ($latest)."
