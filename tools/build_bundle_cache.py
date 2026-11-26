"""Match the live SPT bundle manifest and server hashes to pinned author archives."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


def members(path, seven):
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            return [(e.filename, e.file_size, e.CRC) for e in archive.infolist() if not e.is_dir()]
    listing = subprocess.check_output([seven, "l", "-slt", "-sccUTF-8", str(path)], encoding="utf8")
    result = []
    for block in listing.split("----------\n")[-1].split("\n\n"):
        fields = dict(line.split(" = ", 1) for line in block.splitlines() if " = " in line)
        if fields.get("CRC"):
            result.append((fields["Path"].replace("\\", "/"), int(fields["Size"]), int(fields["CRC"], 16)))
    return result


def build(manifest, hashes, sources, seven):
    pins = {(r["mod"], r["name"].casefold()):r["sha"] for r in hashes}
    sources_by_mod = {r["mod"]:r for r in sources}
    groups = {}
    seen = set()
    for row in manifest:
        mod = row["ModPath"].split("/")[-1]
        name = row["FileName"]
        source = sources_by_mod[mod]
        if mod not in groups:
            archive = Path(source["path"])
            with archive.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != source["sha256"]:
                raise ValueError(f"Archive checksum mismatch for {mod}")
            by_crc = {}
            for member, size, crc in members(archive, seven):
                by_crc.setdefault((size,crc), []).append(member)
            groups[mod] = (dict(name=mod,url=source["url"],size=archive.stat().st_size,
                                sha256=digest,files=[]), by_crc)
        group, by_crc = groups[mod]
        crc = row["Crc"]
        matches = [m for m in by_crc.get((row["Size"],crc), [])
                   if m.replace("\\","/").casefold().endswith("/bundles/"+name.casefold())]
        if len(matches) != 1:
            raise ValueError(f"{mod}/{name} has {len(matches)} matching archive members")
        cache_path = f"{crc:08X}/{name}"
        if cache_path.casefold() in seen:
            raise ValueError(f"Duplicate SPT bundle path: {cache_path}")
        seen.add(cache_path.casefold())
        group["files"].append(dict(path=cache_path,member=matches[0],size=row["Size"],
                                   sha256=pins[(mod,name.casefold())]))
    return [groups[k][0] for k in sorted(groups)]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("manifest","hashes","sources","out"):
        parser.add_argument(key,type=Path)
    parser.add_argument("--seven",default="7z")
    args = parser.parse_args()
    groups = build(*(json.loads(arg.read_bytes()) for arg in (args.manifest,args.hashes,args.sources)),args.seven)
    args.out.write_text(json.dumps(groups,separators=(",",":"))+"\n",encoding="utf8")
    print(f"{sum(len(g['files']) for g in groups)} verified manifest entries in {len(groups)} archives")
