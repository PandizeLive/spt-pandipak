using System.Diagnostics;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace SPTarkov.Launcher;

internal static class LauncherUpdate
{
    internal const string CurrentVersion = "1.0.1";
    private static readonly HttpClient Web = new() { Timeout = TimeSpan.FromSeconds(20) };
    internal record Release(string Version, string Sha256);

    internal static async Task<Release?> Check()
    {
        var release = await Web.GetFromJsonAsync<Release>(
            "https://raw.githubusercontent.com/PandizeLive/spt-pandipak/main/launcher-release.json");
        return NewerRelease(release);
    }

    internal static Release? NewerRelease(Release? release)
    {
        if (release is null || !Regex.IsMatch(release.Version ?? "", @"\A[0-9]+\.[0-9]+\.[0-9]+\z")
            || !Version.TryParse(release.Version, out var version)
            || !Regex.IsMatch(release.Sha256 ?? "", @"\A[a-f0-9]{64}\z"))
            throw new InvalidDataException("Invalid launcher release metadata.");
        return version > Version.Parse(CurrentVersion) ? release : null;
    }

    internal static async Task Install(Release release, IProgress<string> progress)
    {
        var target = Environment.ProcessPath ?? throw new IOException("Could not locate this launcher.");
        var stage = Path.Combine(Path.GetDirectoryName(target)!, $".sptpp-{Guid.NewGuid():N}.tmp");
        try
        {
            var url = $"{Pandipak.Releases}/download/launcher-v{release.Version}/SPTpp-Launcher.exe";
            await Pandipak.Download(url, release.Sha256, stage, progress);
            using var current = File.OpenRead(target);
            var oldHash = Convert.ToHexStringLower(await SHA256.HashDataAsync(current));
            var psi = new ProcessStartInfo(Path.Combine(Environment.SystemDirectory, @"WindowsPowerShell\v1.0\powershell.exe"))
            {
                UseShellExecute = false,
                CreateNoWindow = true
            };
            foreach (var arg in new[] { "-NoProfile", "-NonInteractive", "-STA", "-EncodedCommand",
                         Convert.ToBase64String(Encoding.Unicode.GetBytes(ReplaceAfterExit)) })
                psi.ArgumentList.Add(arg);
            psi.Environment["SPTPP_TARGET"] = target;
            psi.Environment["SPTPP_STAGE"] = stage;
            psi.Environment["SPTPP_OLD_HASH"] = oldHash;
            psi.Environment["SPTPP_NEW_HASH"] = release.Sha256;
            psi.Environment["SPTPP_PID"] = Environment.ProcessId.ToString();
            psi.Environment["SPTPP_GAME"] = Pandipak.Root;
            using var worker = Process.Start(psi) ?? throw new IOException("Could not start the launcher updater.");
        }
        catch
        {
            File.Delete(stage);
            throw;
        }
        Launcher.App.MainWindow.Invoke(Launcher.RequestExit);
    }

    // A separate process can replace the executable after Windows releases it.
    private const string ReplaceAfterExit = """
        $ErrorActionPreference = 'Stop'
        $target = $env:SPTPP_TARGET
        $stage = $env:SPTPP_STAGE
        $backup = $stage + '.previous'
        function FileHash($file) {
            $hash = [Security.Cryptography.SHA256]::Create()
            try {
                $stream = [IO.File]::OpenRead($file)
                try { return [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-', '') }
                finally { $stream.Dispose() }
            } finally { $hash.Dispose() }
        }
        try {
            $app = Get-Process -Id ([int]$env:SPTPP_PID) -ErrorAction SilentlyContinue
            if ($app -and !$app.WaitForExit(60000)) { throw 'The launcher is still running.' }
            if ((FileHash $target) -ne $env:SPTPP_OLD_HASH -or
                (FileHash $stage) -ne $env:SPTPP_NEW_HASH) {
                throw 'A launcher file changed during the update.'
            }
            [IO.File]::Replace($stage, $target, $backup)
            try {
                $start = [Diagnostics.ProcessStartInfo]::new()
                $start.FileName = $target
                $start.Arguments = '--game "' + $env:SPTPP_GAME + '"'
                $start.WorkingDirectory = $env:SPTPP_GAME
                $start.UseShellExecute = $false
                [void][Diagnostics.Process]::Start($start)
            } catch {
                [IO.File]::Replace($backup, $target, $stage)
                throw
            }
            [IO.File]::Delete($backup)
        } catch {
            Add-Type -AssemblyName System.Windows.Forms
            [void][Windows.Forms.MessageBox]::Show($_.Exception.Message, 'SPTpp launcher update')
        } finally {
            [IO.File]::Delete($stage)
        }
        """;
}
