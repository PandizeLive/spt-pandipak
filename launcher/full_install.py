"""Prepare the exact pinned player files, then use Pandipak's transactional installer."""
from pathlib import Path
import hashlib
import importlib.util
import json
import lzma
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
import zlib

KIT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pack_setup",KIT/"setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)

def fetch(group, part, cache):
    path=cache/part["sha"]
    if path.exists() and setup.digest(path)==part["sha"]:
        return path
    curl=Path(os.environ["SystemRoot"])/"System32/curl.exe"
    with tempfile.NamedTemporaryFile(dir=cache,delete=False) as f:
        tmp=Path(f.name)
    try:
        args=[str(curl),"-q","--fail","--location","--proto","=https","--proto-redir","=https",
              "--silent","--show-error","--retry","2","--connect-timeout","25","--speed-time","90",
              "--speed-limit","512","--max-filesize",str(part["length"]),"-o",str(tmp)]
        if part["length"]!=group["size"]:
            args+=["--range",f'{part["start"]}-{part["start"]+part["length"]-1}']
        with subprocess.Popen(args+[group["url"]]) as download:
            while True:
                try:
                    status=download.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    with tmp.open("rb") as partial:
                        received=partial.seek(0,os.SEEK_END)
                    print(f'{group["name"]} · {received//1048576:,} / {part["length"]//1048576:,} MiB',flush=True)
                    continue
                if status:
                    raise RuntimeError(f"Download failed (curl {status}). Retry the installation.")
                break
        if tmp.stat().st_size!=part["length"] or setup.digest(tmp)!=part["sha"]:
            raise ValueError("The downloaded bytes differ from the pinned release for "+group["name"]+".")
        os.replace(tmp,path)
        return path
    finally:
        tmp.unlink(missing_ok=True)

def write_zip_slice(data,entry,dest):
    data.seek(entry["offset"])
    remaining=entry["compressed"]
    decoder=zlib.decompressobj(-15) if entry["method"]==zipfile.ZIP_DEFLATED else None
    if not decoder and entry["method"]!=zipfile.ZIP_STORED:raise ValueError("Unsupported ZIP method")
    with dest.open("wb") as output:
        while remaining:
            chunk=data.read(min(remaining,256*1024))
            if not chunk:raise ValueError("Incomplete ZIP member.")
            remaining-=len(chunk)
            output.write(decoder.decompress(chunk) if decoder else chunk)
        if decoder:
            output.write(decoder.flush())
            if not decoder.eof:raise ValueError("Incomplete deflate stream.")

def unpack(group,part,path,folder,files):
    def target(rel):
        if rel not in files or files[rel]["mode"]!="file" or not setup.allowed(rel):
            raise ValueError("Unexpected player file in source recipe.")
        dest=setup.safe(folder,rel)
        dest.parent.mkdir(parents=True,exist_ok=True)
        return dest
    if part["kind"]=="solid":
        filters=[]
        if part["bcj"]:filters.append({"id":lzma.FILTER_X86})
        filters.append({"id":lzma.FILTER_LZMA2,"dict_size":part["dictionary"]})
        decoder=lzma.LZMADecompressor(format=lzma.FORMAT_RAW,filters=filters)
        cursor=0
        with path.open("rb") as data,tempfile.TemporaryFile() as raw:
            while cursor<part["end"]:
                chunk=data.read(256*1024) if decoder.needs_input else b""
                if not chunk and decoder.needs_input:raise ValueError("Incomplete 7z block.")
                decoded=decoder.decompress(chunk,min(1024*1024,part["end"]-cursor))
                cursor+=len(decoded)
                raw.write(decoded)
            for e in part["entries"]:
                raw.seek(e["offset"])
                with target(e["path"]).open("wb") as dest:
                    left=e["size"]
                    while left:
                        b=raw.read(min(1024*1024,left))
                        if not b:raise ValueError("Incomplete player file.")
                        dest.write(b)
                        left-=len(b)
    elif part["kind"]=="zip-slice":
        with path.open("rb") as data:
            for e in part["entries"]:write_zip_slice(data,e,target(e["path"]))
    elif zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for e in part["entries"]:
                with archive.open(e["member"]) as src,target(e["path"]).open("wb") as dest:
                    shutil.copyfileobj(src,dest,1024*1024)
    else:
        tar=Path(os.environ["SystemRoot"])/"System32/tar.exe"
        for e in part["entries"]:
            with target(e["path"]).open("wb") as out:
                subprocess.run([tar,"-xOf",path,"--",e["member"]],stdout=out,check=True)
    for e in part["entries"]:
        if setup.digest(target(e["path"]))!=files[e["path"]]["sha"]:
            raise ValueError("Source file differs from the pack: "+e["path"])

def prepare_sources(groups, game, files, cache, fetched):
    for i,g in enumerate(groups,1):
        print(f'Preparing {g["name"]} ({i}/{len(groups)})',flush=True)
        for part in g["parts"]:
            if all((game/e["path"]).is_file() and setup.digest(game/e["path"])==files[e["path"]]["sha"]
                   for e in part["entries"]):
                continue
            try:
                archive=fetch(g,part,cache)
                unpack(g,part,archive,KIT/"files",files)
                fetched.add(archive)
            except Exception as error:
                raise RuntimeError(f'{g["name"]}: {error}') from error


def prepare_volume(volume, game, files, cache, fetched):
    name = volume["name"]
    print("Preparing " + name, flush=True)
    for directory in (KIT, KIT.parent):
        archive = directory / (name + ".zip")
        if archive.exists():
            if setup.digest(archive) != volume["sha256"]:
                raise ValueError("Checksum mismatch in local " + archive.name)
            break
    else:
        part = dict(sha=volume["sha256"], length=volume["size"], start=0)
        archive = fetch(volume, part, cache)
        fetched.add(archive)
    with zipfile.ZipFile(archive) as z:
        if z.namelist() == ["sources.json"]:
            prepare_sources(json.loads(z.read("sources.json")), game, files, cache, fetched)
            return
        for entry in z.infolist():
            rel = entry.filename.removeprefix("files/")
            if rel == entry.filename or not setup.allowed(rel) or files.get(rel, {}).get("mode") != "file":
                raise ValueError("Unexpected file in " + name)
            dest = setup.safe(KIT/"files", rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(entry) as reader, dest.open("wb") as writer:
                shutil.copyfileobj(reader, writer, 1024 * 1024)
            if setup.digest(dest) != files[rel]["sha"]:
                raise ValueError("Wrong content for " + rel)


def main(game):
    setup.check_install(game)
    files=setup.read_json(KIT/"manifest.json")["files"]
    cache=Path(os.environ["LOCALAPPDATA"])/"SPTpp"/"Downloads"
    cache.mkdir(parents=True,exist_ok=True)
    fetched=set()
    if (KIT/"volumes.json").is_file():
        volumes = setup.read_json(KIT/"volumes.json")
        if [v["name"] for v in volumes] != ["Backports1", "Backports2", "Backports3"]:
            raise ValueError("Incomplete backport volume list.")
        for volume in volumes:
            prepare_volume(volume, game, files, cache, fetched)
    print("Preparing Misc", flush=True)
    prepare_sources(setup.read_json(KIT/"sources.json"), game, files, cache, fetched)
    setup.install(game,KIT)
    for archive in fetched:
        try:archive.unlink(missing_ok=True)
        except OSError:pass

if __name__=="__main__":
    try:main(Path(sys.argv[1]).resolve())
    except Exception as error:
        print("Installation stopped:",error,file=sys.stderr)
        sys.exit(1)
