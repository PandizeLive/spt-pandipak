using System.Diagnostics;
using System.IO.Compression;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;

namespace SPTarkov.Launcher;

internal static class Pandipak
{
    internal const string Releases = "https://github.com/PandizeLive/spt-pandipak/releases";
    internal static string Root => Directory.GetParent(Environment.CurrentDirectory)!.FullName;
    internal static string Receipt => Path.Combine(Root, ".msi-player-pack", "installed.json");
    internal static bool Managed => File.Exists(Path.Combine(Root,"HeadlessConfig.json"))
        || Directory.Exists(Path.Combine(Root,"MSI-RaidHost"))
        || File.Exists(Path.Combine(Root,"BepInEx/plugins/Fika/Fika.Headless.dll"));
    internal record Release(string Tag, string[] Steps);
    internal record Index(string Latest, Release[] Releases);
    internal record Step(string Tag, string Target, string Hash);
    internal record Plan(string Version, List<Step> Steps);
    internal record BaseKit(string Url, string Sha256, string Receipt);
    static readonly HttpClient Web = new(){ Timeout = TimeSpan.FromMinutes(30) };

    [DllImport("user32.dll", CharSet=CharSet.Unicode)]
    static extern int MessageBoxW(IntPtr window, string text, string title, uint type);

    internal static bool SelectInstallation(string[] args)
    {
        try { return ChooseGame(args); }
        catch (Exception error)
        {
            MessageBoxW(IntPtr.Zero,error.Message,"SPTpp Launcher",0x10);
            return false;
        }
    }

    static bool ChooseGame(string[] args)
    {
        var saved = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"SPTpp","installation.txt");
        static bool Valid(string? folder) => !string.IsNullOrWhiteSpace(folder)
            && File.Exists(Path.Combine(folder,"EscapeFromTarkov.exe"))
            && FileVersionInfo.GetVersionInfo(Path.Combine(folder,"EscapeFromTarkov.exe")).FileVersion == "0.16.9.40743"
            && File.Exists(Path.Combine(folder,"SPT_Runtime","SPT.Launcher.exe"))
            && FileVersionInfo.GetVersionInfo(Path.Combine(folder,"SPT_Runtime","SPT.Launcher.exe")).FileVersion == "4.1.6.0";
        var candidates = new[] {
            args.Length == 2 && args[0] == "--game" ? args[1] : null,
            AppContext.BaseDirectory, Directory.GetParent(Path.TrimEndingDirectorySeparator(AppContext.BaseDirectory))?.FullName,
            File.Exists(saved) ? File.ReadAllText(saved).Trim() : null
        };
        var game = candidates.FirstOrDefault(Valid);
        bool picked = false;
        while (!Valid(game))
        {
            const string picker = """
                Add-Type -AssemblyName System.Windows.Forms
                $answer = [Windows.Forms.MessageBox]::Show("Do you already have SPT 4.1.6 installed?`n`nYes: choose its game folder.`nNo: open the official SPT installer, select 4.1.6 and install it using your own Tarkov copy.", 'SPTpp Launcher', 'YesNoCancel')
                if ($answer -eq 'Cancel') { exit }
                if ($answer -eq 'No') { [Console]::Write(':INSTALL:'); exit }
                $d = New-Object Windows.Forms.FolderBrowserDialog
                $d.Description = 'SPTpp Launcher: select your SPT 4.1.6 game folder containing EscapeFromTarkov.exe. Install SPT 4.1.6 first if needed.'
                $d.ShowNewFolderButton = $false
                if ($d.ShowDialog() -eq 'OK') { [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false); [Console]::Write($d.SelectedPath) }
                """;
            var psi = new ProcessStartInfo("powershell.exe"){ UseShellExecute=false, CreateNoWindow=true, RedirectStandardOutput=true, StandardOutputEncoding=Encoding.UTF8 };
            foreach (var arg in new[]{"-NoProfile","-STA","-EncodedCommand",Convert.ToBase64String(Encoding.Unicode.GetBytes(picker))}) psi.ArgumentList.Add(arg);
            using var process = Process.Start(psi)!;
            game = process.StandardOutput.ReadToEnd();
            process.WaitForExit();
            if (string.IsNullOrWhiteSpace(game)) return false;
            if (game==":INSTALL:")
            {
                var installer=Path.Combine(Path.GetDirectoryName(saved)!,"SPTInstaller.exe");
                Directory.CreateDirectory(Path.GetDirectoryName(saved)!);
                const string hash="c3020824e4be59c0a99c445abda1e485433ccdab46727af87527c34a0c8276c2";
                if (!File.Exists(installer) || Hash(installer).GetAwaiter().GetResult()!=hash)
                    Download("https://github.com/SP-Tushonka/installer/releases/download/v3.0.0.0/SPTInstaller.exe",
                             hash,installer,new Progress<string>()).GetAwaiter().GetResult();
                using var setup=Process.Start(new ProcessStartInfo(installer){ UseShellExecute=true,WorkingDirectory=Path.GetDirectoryName(installer)! });
                setup?.WaitForExit();
                game=null;
                continue;
            }
            picked = true;
            if (!Valid(game))
                MessageBoxW(IntPtr.Zero,"Choose the folder containing SPT 4.1.6 and EscapeFromTarkov.exe build 40743.","SPTpp Launcher",0x30);
        }
        if (picked)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(saved)!);
            File.WriteAllText(saved,game!);
        }
        Directory.SetCurrentDirectory(Path.Combine(Path.GetFullPath(game!),"SPT_Runtime"));
        return true;
    }

    static async Task<string> Hash(string path)
    {
        await using var file = File.OpenRead(path);
        return Convert.ToHexStringLower(await SHA256.HashDataAsync(file));
    }

    internal static async Task<Plan> Check()
    {
        var index = await Web.GetFromJsonAsync<Index>(Releases+"/latest/download/Pandipak-index.json")
            ?? throw new InvalidDataException("Empty release index.");
        var steps = new Dictionary<string,Step>();
        string? latest = null;
        foreach (var release in index.Releases)
        {
            if (!Regex.IsMatch(release.Tag,@"\A[A-Za-z0-9][A-Za-z0-9._-]*\z")) throw new InvalidDataException("Invalid release tag.");
            foreach (var line in release.Steps)
            {
                if (!Regex.IsMatch(line,@"\A[0-9a-f]{64}( [0-9a-f]{64}){2}\z")) throw new InvalidDataException("Invalid release metadata.");
                var parts = line.Split(' ');
                steps.Add(parts[0], new(release.Tag,parts[1],parts[2]));
                if (release.Tag == index.Latest) latest = parts[1];
            }
        }
        if (latest is null) throw new InvalidDataException("The latest pack version is missing.");
        var current = await Hash(Receipt);
        var path = new List<Step>();
        while (current != latest)
        {
            if (!steps.Remove(current,out var step)) throw new InvalidDataException("This installed pack has no update path to "+index.Latest+".");
            path.Add(step);
            current = step.Target;
        }
        return new(index.Latest,path);
    }

    static async Task Download(string url, string sha, string path, IProgress<string> progress)
    {
        using var reply = await Web.GetAsync(url,HttpCompletionOption.ResponseHeadersRead);
        reply.EnsureSuccessStatusCode();
        await using var stream = await reply.Content.ReadAsStreamAsync();
        await using (var output = File.Create(path))
        {
            var buffer = new byte[131072];
            var timer = Stopwatch.StartNew();
            int n;
            while ((n = await stream.ReadAsync(buffer)) != 0)
            {
                await output.WriteAsync(buffer.AsMemory(0,n));
                if (timer.ElapsedMilliseconds < 300) continue;
                progress.Report($"Downloading · {output.Position / 1048576:N0} MB");
                timer.Restart();
            }
        }
        if (!string.Equals(await Hash(path),sha,StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Download checksum mismatch. Try again.");
    }

    internal static async Task Apply(bool fresh,IProgress<string> progress)
    {
        if (Managed) throw new InvalidOperationException("This installation is managed by the host.");
        if (fresh)
        {
            var kit = await Web.GetFromJsonAsync<BaseKit>("https://raw.githubusercontent.com/PandizeLive/spt-pandipak/main/full-install.json")
                ?? throw new InvalidDataException("Full install is unavailable.");
            if (!kit.Url.StartsWith(Releases+"/download/",StringComparison.Ordinal)) throw new InvalidDataException("Invalid kit location.");
            await RunKit(kit.Url,kit.Sha256,kit.Receipt,true,progress);
        }
        var plan = await Check();
        foreach (var step in plan.Steps)
            await RunKit($"{Releases}/download/{step.Tag}/Pandipak-update.zip",step.Hash,step.Target,false,progress);
    }

    static async Task RunKit(string url,string checksum,string receipt,bool fresh,IProgress<string> progress)
    {
        var dir = Directory.CreateTempSubdirectory("sptpp-");
        try
        {
            var zip = Path.Combine(dir.FullName,"download.zip");
            await Download(url,checksum,zip,progress);
            var kit = Path.Combine(dir.FullName,"kit");
            await Task.Run(()=>ZipFile.ExtractToDirectory(zip,kit));
            var psi = new ProcessStartInfo(Path.Combine(kit,"runtime","python.exe")){
                WorkingDirectory=kit,UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true};
            foreach (var arg in new[]{"-I","-u",fresh?"full_install.py":"setup.py",Root}) psi.ArgumentList.Add(arg);
            progress.Report("Verifying player files…");
            using var child=Process.Start(psi)!;
            var error=child.StandardError.ReadToEndAsync();
            while (await child.StandardOutput.ReadLineAsync() is { } line) progress.Report(line);
            await child.WaitForExitAsync();
            var detail=(await error).Trim();
            if (child.ExitCode!=0) throw new InvalidOperationException(detail.Length==0?"Installation stopped.":detail);
            if (await Hash(Receipt)!=receipt) throw new InvalidDataException("Installation receipt differs from the release.");
        }
        finally { dir.Delete(true); }
    }
}
