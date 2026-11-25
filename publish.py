"""Build an incremental Windows player update from two approved full installer ZIPs."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

REPO = "PandizeLive/spt-pandipak"
HERE = Path(__file__).resolve().parent

def fingerprint(manifest):
    receipt = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    return hashlib.sha256(receipt).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("previous", type=Path)
    parser.add_argument("current", type=Path)
    parser.add_argument("tag")
    parser.add_argument("--also-from", type=Path, action="append", default=[],
                        help="Accept an additional previously shipped installer ZIP or manifest JSON.")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out/"Pandipak-update.zip"
    with zipfile.ZipFile(args.previous) as old, zipfile.ZipFile(args.current) as new:
        if "update-from.json" in old.namelist() or "update-from.json" in new.namelist():
            raise ValueError("Supply the two full installer ZIPs.")
        before, after = [json.loads(z.read("manifest.json")) for z in (old,new)]
        baselines = {fingerprint(before): before}
        for source in args.also_from:
            if source.suffix.lower() == ".zip":
                with zipfile.ZipFile(source) as archive:
                    extra = json.loads(archive.read("manifest.json"))
            else:
                extra = json.loads(source.read_bytes())
            baselines[fingerprint(extra)] = extra
        if fingerprint(after) in baselines:
            raise ValueError("The target is included in the starting versions.")
        if fingerprint(before)==fingerprint(after):
            raise ValueError("The two manifests are identical.")
        payload = []
        for rel, row in after["files"].items():
            if row["mode"]!="file" or any(m["files"].get(rel,{}).get("sha")!=row["sha"] for m in baselines.values()):
                payload.append("files/"+rel)
                if row["mode"]=="file": print("Changed file:",rel)
        payload += [k for k in new.namelist() if k.startswith(("runtime/","notices/"))]
        if "server-address.txt" not in new.namelist():
            raise ValueError("Rebuild the group installer with separate host settings before publishing.")
        endpoint = new.read("server-address.txt").decode("utf8").strip()
        host = endpoint.rsplit(":", 1)[0].strip("[]")
        if not host:
            raise ValueError("Missing host address in the group installer.")
        payload += ["setup.py","manifest.json"]
        with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED,compresslevel=1) as out:
            for key in payload:
                content=new.read(key)
                if any(host.encode(encoding) in content for encoding in ("utf8","utf-16le")):
                    raise ValueError("Group host address in public payload: "+key)
                if key.startswith("files/") and hashlib.sha256(content).hexdigest()!=after["files"][key[6:]]["sha"]:
                    raise ValueError("Hash mismatch in approved installer: "+key)
                out.writestr(key,content)
            ids=[hashlib.sha256(json.dumps(m,sort_keys=True,separators=(",",":")).encode()).hexdigest()
                 for m in baselines.values()]
            out.writestr("update-from.json",json.dumps({"base":ids[0],"also":ids[1:]}))
    with path.open("rb") as f: checksum=hashlib.file_digest(f,"sha256").hexdigest()
    if path.stat().st_size>=2*1024**3: raise ValueError("Update exceeds GitHub's single-asset limit.")
    starter=args.out/"Pandipak-Updater.zip"
    with zipfile.ZipFile(starter,"w",zipfile.ZIP_DEFLATED) as z:
        for filename in ("Update Pandipak.cmd","Update-Pandipak.ps1","README.md"):
            z.write(HERE/filename,filename)
    notes=args.out/"release-notes.txt"
    notes.write_text("Run Update Pandipak.cmd from the extracted updater.\n\n"
                     + "".join(f"Pandipak-Update {source} {fingerprint(after)} {checksum}\n" for source in baselines),encoding="utf8")
    print(path, path.stat().st_size, "bytes")
    if args.publish:
        def gh(*arguments):
            return subprocess.check_output(["gh",*arguments],text=True).strip()
        if gh("repo","view",REPO,"--json","visibility","--jq",".visibility")!="PUBLIC":
            raise ValueError("Expected the public player update repository.")
        releases=json.loads(gh("api",f"repos/{REPO}/releases?per_page=100"))
        if releases:
            latest=json.loads(gh("api",f"repos/{REPO}/releases/latest"))
            if not any(line.startswith("Pandipak-Update ") and len(line.split())==4 and
                       line.split()[2]==fingerprint(before) for line in latest["body"].splitlines()):
                raise ValueError("Previous installer must match the latest published release.")
        gh("release","create",args.tag,str(path),str(starter),"--repo",REPO,
           "--title",args.tag,"--notes-file",str(notes),"--draft")
        print(gh("release","edit",args.tag,"--draft=false","--latest","--repo",REPO))

if __name__=="__main__": main()
