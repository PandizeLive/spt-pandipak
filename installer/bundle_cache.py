"""Populate the remote SPT launcher's CRC-addressed cache from pinned releases."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import zipfile


def install(groups, game, downloads, fetched, fetch, setup):
    cache = setup.safe(game, "SPT_Runtime/user/cache/bundles")
    cache.mkdir(parents=True, exist_ok=True)
    for group in groups:
        pending = []
        for entry in group["files"]:
            if not re.fullmatch(r"[0-9A-F]{8}/.+", entry["path"]):
                raise ValueError("Invalid bundle cache key")
            target = setup.safe(cache, entry["path"])
            if target.is_file() and target.stat().st_size == entry["size"] and setup.digest(target) == entry["sha256"]:
                continue
            pending.append((entry,target))
        if not pending:
            continue
        print(f'Preparing {len(pending)} bundles from {group["name"]}', flush=True)
        part = dict(start=0,length=group["size"],sha=group["sha256"])
        archive = fetch(group, part, downloads, fetched)
        fetched.add(archive)
        # Stage and verify before each atomic replacement; earlier files survive an interruption.
        with tempfile.TemporaryDirectory(dir=cache) as temp:
            stage = Path(temp)
            for entry,_ in pending:
                setup.safe(stage,entry["member"])
            if zipfile.is_zipfile(archive):
                with zipfile.ZipFile(archive) as source:
                    for entry,target in pending:
                        with source.open(entry["member"]) as reader, (stage/"bundle.tmp").open("wb") as writer:
                            shutil.copyfileobj(reader,writer,1024*1024)
                        commit(stage/"bundle.tmp",entry,target,setup)
            else:
                names = stage/"members.txt"
                names.write_text("".join(entry["member"]+"\n" for entry,_ in pending),encoding="utf8")
                tar = Path(os.environ["SystemRoot"])/"System32/tar.exe"
                subprocess.run([tar,"-xf",archive,"-C",stage,"-T",names],check=True)
                for entry,target in pending:
                    commit(setup.safe(stage,entry["member"]),entry,target,setup)


def commit(staged, entry, target, setup):
    if staged.stat().st_size != entry["size"] or setup.digest(staged) != entry["sha256"]:
        raise ValueError("Bundle differs from the server release: "+entry["path"])
    target.parent.mkdir(parents=True,exist_ok=True)
    os.replace(staged,target)
