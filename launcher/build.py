"""Build SPTpp from the pinned upstream SPT 4.1.6 Windows launcher."""
import argparse
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
UPSTREAM = "21225a2fc49ae1a7ece5185586322194de8fe662"

def build(source, out, dotnet):
    if subprocess.check_output(["git","-C",source,"rev-parse","HEAD"],text=True).strip()!=UPSTREAM:
        raise ValueError("Expected the upstream 4.1.6 launcher commit.")
    out.mkdir(parents=True,exist_ok=True)
    tree=out/"src"
    for directory in ("SPTushonka.Core","SPTushonka.Launcher"):
        shutil.copytree(source/directory,tree/directory,dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("bin","obj"))
    shutil.copy2(source/"Build.props",tree/"Build.props")
    ui=tree/"SPTushonka.Launcher"
    for name in ("Pandipak.cs","PandipakPanel.razor"):
        shutil.copy2(HERE/name,ui/name)
    (ui/"App.razor").write_text("<PandipakPanel><Routes/></PandipakPanel>\n",encoding="utf8")
    def replace(path, old, new):
        data=path.read_text(encoding="utf-8-sig")
        if data.count(old)!=1: raise ValueError("Upstream source changed: "+str(path))
        path.write_text(data.replace(old,new),encoding="utf8")
    replace(ui/"Launcher.cs","        SetNvidiaLinuxEnv();",
            "        if (!Pandipak.SelectInstallation(args)) return;\n        SetNvidiaLinuxEnv();")
    replace(ui/"Helpers/TitleHelper.cs",'"SPT Launcher"','"SPTpp Launcher"')
    replace(ui/"Platform/SingleInstanceGuard.cs","var identity = Environment.ProcessPath;",
            'var identity = Path.Combine(Environment.CurrentDirectory, "SPT.Launcher.exe");')
    shutil.copy2(source/"LICENSE.md",ui/"wwwroot/UPSTREAM-LICENSE.txt")
    subprocess.run([dotnet,"publish",ui/"SPTushonka.Launcher.csproj","-c","Release","-r","win-x64",
                    "--self-contained","true","-p:PublishSingleFile=true","-p:SptVersion=4.1.6",
                    "-p:SptCommitTag=731d7a2","-p:DebugType=None","-p:DebugSymbols=false",
                    "-p:PathMap="+str(tree)+"=/_/src","--verbosity","quiet"],check=True)
    shutil.copyfile(tree/"Build/SPT.Launcher.exe",out/"SPTpp-Launcher.exe")
    shutil.copyfile(source/"LICENSE.md",out/"SPT-Launcher-LICENSE.txt")

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path)
    parser.add_argument("out",type=Path)
    parser.add_argument("--dotnet",default="dotnet")
    args=parser.parse_args()
    build(args.source.resolve(),args.out.resolve(),args.dotnet)
