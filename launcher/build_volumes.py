"""Build the four Pandipak volumes from the verified player kit and author download recipe."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

from build_full import stamp

BACKPORTS = {"visitapi", "manimals-halloween-2026-backport", "sound-full", "storyline", "com.wtt.contentbackport"}
NAMES = ("Backports1", "Backports2", "Backports3", "Misc")
LIMIT = 2 * 1024**3
URL = "https://github.com/PandizeLive/spt-pandipak/releases/download/"


def fingerprint(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def pack_groups(sources, locations, original):
    """Keep solid blocks together. Split the oversized Storyline ZIP on member boundaries."""
    batches = {name: [] for name in NAMES}
    weights = {name: 0 for name in NAMES[:3]}
    candidates = []
    for group in sources:
        if group["name"] not in BACKPORTS:
            batches["Misc"].append(group)
            continue
        for part in group["parts"]:
            parts = [part]
            if part["length"] >= LIMIT:
                if part["kind"] != "zip-slice":
                    raise ValueError("Oversized indivisible block in " + group["name"])
                parts = []
                with Path(locations[part["sha"]][0]).open("rb") as src:
                    for entry in part["entries"]:
                        piece = dict(start=part["start"] + entry["offset"], length=entry["compressed"],
                                     kind="zip-slice", entries=[dict(entry, offset=0)])
                        parts.append(stamp(piece, src))
            for piece in parts:
                packed = sum(original.getinfo("files/" + e["path"]).compress_size for e in piece["entries"])
                weight = max(packed, piece["length"])
                candidates.append((weight, dict(group, parts=[piece])))
    for weight, group in sorted(candidates, key=lambda x: x[0], reverse=True):
        name = min(weights, key=weights.get)
        weights[name] += weight
        batches[name].append(group)
    if max(weights.values()) >= LIMIT:
        raise ValueError("The backports no longer fit three volumes.")
    return batches


def write_zip(path):
    return zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=1)


def copy_entry(source, dest, name):
    with source.open(name) as reader, dest.open(name, "w") as writer:
        shutil.copyfileobj(reader, writer, 1024 * 1024)


def summary(path, tag):
    length = path.stat().st_size
    if length >= LIMIT:
        raise ValueError(f"{path.name} exceeds GitHub's asset limit.")
    return dict(name=path.stem, url=f"{URL}{tag}/{path.name}", size=length, sha256=fingerprint(path))


def build(args):
    output = args.out
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.kit) as original, zipfile.ZipFile(args.capsule) as capsule:
        raw = original.read("manifest.json")
        if raw != capsule.read("manifest.json"):
            raise ValueError("Full kit and download recipe have different receipts.")
        batches = pack_groups(json.loads(capsule.read("sources.json")),
                              json.loads(args.locations.read_bytes()), original)
        volumes = []
        backport_files = set()
        for name in NAMES[:3]:
            groups = batches[name]
            members = ["files/" + e["path"] for g in groups for p in g["parts"] for e in p["entries"]]
            if len(set(members)) != len(members) or backport_files.intersection(members):
                raise ValueError("Duplicate player file in backport volumes.")
            backport_files.update(members)
            archive = output / (name + ".zip")
            with write_zip(archive) as z:
                if args.complete:
                    for member in sorted(members):
                        copy_entry(original, z, member)
                else:
                    z.writestr("sources.json", json.dumps(groups, separators=(",", ":")))
            volumes.append(summary(archive, args.tag))
            print(name, archive.stat().st_size, len(members), "player files", flush=True)
        misc = output / "Misc.zip"
        with write_zip(misc) as z:
            source = original if args.complete else capsule
            for entry in source.namelist():
                if entry == "Install or update.cmd" and args.complete:
                    z.writestr(entry, source.read(entry).replace(b"setup.py", b"full_install.py"))
                elif entry == "Start here.txt" and args.complete:
                    z.writestr(entry, "Keep Backports1.zip, Backports2.zip and Backports3.zip beside Misc.zip.\r\n"
                               "Extract Misc.zip into its own folder. Run Install or update.cmd inside that folder.\r\n"
                               "Choose an SPT 4.1.6 guest installation. Enter your host's connection details privately.\r\n")
                elif entry not in backport_files and entry not in {"sources.json", "full_install.py"}:
                    copy_entry(source, z, entry)
            z.write(Path(__file__).with_name("full_install.py"), "full_install.py")
            z.writestr("sources.json", json.dumps([] if args.complete else batches["Misc"], separators=(",", ":")))
            z.writestr("volumes.json", json.dumps(volumes, separators=(",", ":")))
        base = summary(misc, args.tag)
        descriptor = dict(url=base["url"], sha256=base["sha256"], receipt=hashlib.sha256(raw).hexdigest())
        (output/"full-install.json").write_text(json.dumps(descriptor, indent=2)+"\n", encoding="utf8")
        print("Misc", base["size"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("kit", "capsule", "locations", "out"):
        parser.add_argument(field, type=Path)
    parser.add_argument("tag")
    parser.add_argument("--complete", action="store_true", help="Include all mod bytes for a complete offline kit.")
    build(parser.parse_args())
