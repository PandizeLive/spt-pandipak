"""Build an install capsule from a player kit, pinned source mapping and local author archives."""
import argparse
from pathlib import Path
import hashlib
import json
import lzma
import re
import struct
import subprocess
import zipfile

def stamp(part, stream):
    stream.seek(part["start"])
    digest=hashlib.sha256()
    left=part["length"]
    while left:
        data=stream.read(min(left,4*1024*1024))
        if not data:raise ValueError("Source archive ended early.")
        digest.update(data)
        left-=len(data)
    part["sha"]=digest.hexdigest()
    return part

def zip_parts(path,members):
    entries=[]
    with zipfile.ZipFile(path) as z,path.open("rb") as src:
        for rel,member in members.items():
            i=z.getinfo(member)
            src.seek(i.header_offset+26)
            name,extra=struct.unpack("<HH",src.read(4))
            start=i.header_offset+30+name+extra
            entries.append(dict(path=rel,offset=start,compressed=i.compress_size,method=i.compress_type))
        parts=[]
        for e in sorted(entries,key=lambda v:v["offset"]):
            start=e["offset"]
            if not parts or start>parts[-1]["start"]+parts[-1]["length"]+256*1024:
                parts.append(dict(start=start,length=0,kind="zip-slice",entries=[]))
            part=parts[-1]
            e["offset"]-=part["start"]
            part["length"]=e["offset"]+e["compressed"]
            part["entries"].append(e)
        return [stamp(p,src) for p in parts]

def solid_parts(path,members,seven):
    # The WTT release archives use contiguous LZMA2 folders, optionally with the x86 BCJ filter.
    listing=subprocess.check_output([seven,"l","-slt","-sccUTF-8",path],encoding="utf8")
    blocks={}
    for section in listing.split("----------\n")[-1].split("\n\n"):
        row=dict(s.split(" = ",1) for s in section.splitlines() if " = " in s)
        if row.get("Block"):blocks.setdefault(int(row["Block"]),[]).append(row)
    wanted={v:k for k,v in members.items()}
    packed=32
    parts=[]
    with path.open("rb") as src:
        for _,rows in sorted(blocks.items()):
            first=rows[0]
            size=int(first["Packed Size"])
            entries=[]
            offset=end=0
            for row in rows:
                name=row["Path"].replace("\\","/")
                length=int(row["Size"])
                if name in wanted:
                    entries.append(dict(path=wanted[name],offset=offset,size=length))
                    end=offset+length
                offset+=length
            if entries:
                method=re.fullmatch(r"(BCJ )?LZMA2:(\d+)",first["Method"])
                if not method:raise ValueError("Unsupported solid archive method: "+first["Method"])
                bcj=bool(method[1]);dictionary=1<<int(method[2])
                filters=([{"id":lzma.FILTER_X86}] if bcj else [])+[{"id":lzma.FILTER_LZMA2,"dict_size":dictionary}]
                decoder=lzma.LZMADecompressor(format=lzma.FORMAT_RAW,filters=filters)
                src.seek(packed); consumed=produced=0
                while produced<end:
                    chunk=src.read(min(256*1024,size-consumed)) if decoder.needs_input else b""
                    if not chunk and decoder.needs_input:raise ValueError("Truncated solid block.")
                    consumed+=len(chunk)
                    produced+=len(decoder.decompress(chunk,min(1024*1024,end-produced)))
                parts.append(stamp(dict(start=packed,length=consumed,kind="solid",bcj=bcj,
                                        dictionary=dictionary,end=end,entries=entries),src))
            packed+=size
    if sum(len(p["entries"]) for p in parts)!=len(members):raise ValueError("Missing solid members.")
    return parts

def build(kit,recipe,locations,out,tag,seven):
    base=Path(__file__).resolve().parents[1]/"installer"
    out.mkdir(parents=True,exist_ok=True)
    sources=[]
    archive_hashes={}
    local={}
    paths=json.loads(locations.read_bytes())
    mapped=set()
    for group in json.loads(recipe.read_bytes()):
        path=Path(paths[group["archive"]])
        members=group["members"]
        if mapped.intersection(members):raise ValueError("Duplicate player file in recipe.")
        mapped.update(members)
        if group["size"]<80*1024**2:
            parts=[dict(kind="archive",start=0,length=group["size"],sha=group["sha"],
                        entries=[dict(path=k,member=v) for k,v in members.items()])]
        elif zipfile.is_zipfile(path):parts=zip_parts(path,members)
        else:parts=solid_parts(path,members,seven)
        sources.append(dict(name=path.stem,url=group["url"],size=group["size"],parts=parts))
        if any(part["length"] != group["size"] for part in parts):
            archive_hashes[group["url"]] = group["sha"]
        for part in parts: local[part["sha"]]=[str(path),part["start"],part["length"]]
    capsule=out/"Pandipak-full.zip"
    with zipfile.ZipFile(kit) as original,zipfile.ZipFile(capsule,"w",zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        raw=original.read("manifest.json")
        for n in original.namelist():
            if n.startswith(("runtime/","notices/")) or n in ("setup.py","manifest.json"):z.writestr(n,original.read(n))
        for rel,row in json.loads(raw)["files"].items():
            if rel in mapped or rel.startswith("BepInEx/plugins/spt/") or rel=="BepInEx/patchers/spt-prepatch.dll":continue
            if row["mode"]=="file" and rel not in ("BepInEx/plugins/StoryInsurance.dll","BepInEx/plugins/MSI.MarketActions.dll"):
                raise ValueError("Unaccounted third-party file: "+rel)
            z.writestr("files/"+rel,original.read("files/"+rel))
        z.write(base/"full_install.py","full_install.py")
        z.write(base/"bundle_cache.py","bundle_cache.py")
        z.writestr("sources.json",json.dumps(sources,separators=(",",":")))
        z.writestr("archive-hashes.json",json.dumps(archive_hashes,separators=(",",":")))
    with capsule.open("rb") as f:sha=hashlib.file_digest(f,"sha256").hexdigest()
    descriptor=dict(url=f"https://github.com/PandizeLive/spt-pandipak/releases/download/{tag}/{capsule.name}",
                    sha256=sha,receipt=hashlib.sha256(raw).hexdigest())
    (out/"full-install.json").write_text(json.dumps(descriptor,indent=2)+"\n",encoding="utf8")
    (out/"local-validation.json").write_text(json.dumps(local),encoding="utf8")
    print(f"{len(mapped)} source files; {sum(p['length'] for g in sources for p in g['parts']):,} source bytes; {capsule.stat().st_size:,} capsule bytes.")

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ("kit","recipe","locations","out"):parser.add_argument(key,type=Path)
    parser.add_argument("tag")
    parser.add_argument("--seven",default="7z")
    args=parser.parse_args()
    build(args.kit,args.recipe,args.locations,args.out,args.tag,args.seven)
