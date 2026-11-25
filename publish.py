"""Build an incremental Windows player update from two approved full installer ZIPs."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess
import zipfile

REPO = "PandizeLive/spt-pandipak"
HERE = Path(__file__).resolve().parent

def fingerprint(manifest):
    receipt = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    return hashlib.sha256(receipt).hexdigest()

def write_index(path, tag, releases):
    entries = []
    seen = set()
    for release in releases:
        steps = []
        for line in release["body"].splitlines():
            if not line.startswith("Pandipak-Update "):
                continue
            value = line.removeprefix("Pandipak-Update ")
            if not re.fullmatch(r"[0-9a-f]{64}( [0-9a-f]{64}){2}", value):
                raise ValueError("Invalid release metadata.")
            source = value.split()[0]
            if source in seen:
                raise ValueError("Overlapping release paths.")
            seen.add(source)
            steps.append(value)
        if steps:
            entries.append({"tag":release["tag_name"], "steps":steps})
    path.write_text(json.dumps({"latest":tag,"releases":entries}, indent=2)+"\n",encoding="utf8")

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
        if "server-address.txt" in new.namelist() or b"def server_settings(" in new.read("setup.py"):
            raise ValueError("Rebuild the player installer without bundled server settings.")
        payload += ["setup.py","manifest.json"]
        with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED,compresslevel=1) as out:
            for key in payload:
                content=new.read(key)
                if not key.startswith(("runtime/","notices/")):
                    visible = content.replace(b"\x00", b"").lower()
                    if b".ts.net" in visible or re.search(rb"\b100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d+\.\d+\b",visible):
                        raise ValueError("Tailnet address in player payload: "+key)
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
    index = args.out/"Pandipak-index.json"
    current_release = {"tag_name":args.tag, "body":notes.read_text(encoding="utf8")}
    write_index(index, args.tag, [current_release])
    if args.publish:
        def gh(*arguments):
            return subprocess.check_output(["gh",*arguments],text=True).strip()
        if gh("repo","view",REPO,"--json","visibility","--jq",".visibility")!="PUBLIC":
            raise ValueError("Expected the public player update repository.")
        pages=json.loads(gh("api","--paginate","--slurp",f"repos/{REPO}/releases?per_page=100"))
        releases=[r for page in pages for r in page if not r["draft"] and not r["prerelease"]]
        if releases:
            latest=json.loads(gh("api",f"repos/{REPO}/releases/latest"))
            if not any(line.startswith("Pandipak-Update ") and len(line.split())==4 and
                       line.split()[2]==fingerprint(before) for line in latest["body"].splitlines()):
                raise ValueError("Previous installer must match the latest published release.")
        write_index(index, args.tag, releases+[current_release])
        gh("release","create",args.tag,str(path),str(starter),str(index),"--repo",REPO,
           "--title",args.tag,"--notes-file",str(notes),"--draft")
        print(gh("release","edit",args.tag,"--draft=false","--latest","--repo",REPO))

if __name__=="__main__": main()
