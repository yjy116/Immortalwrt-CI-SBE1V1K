"""Prepare compact firmware downloads from an unchanged, verified build artifact."""
import argparse
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import tarfile
from urllib.parse import urlparse

from collect_artifacts import DEVICE, verify_images
from release_notes import render_notes

BUILD_TIMEZONE = timezone(timedelta(hours=8))


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_original(directory):
    checksums = (directory / "SHA256SUMS-CI").read_text().splitlines()
    checked = set()
    for line in checksums:
        match = re.fullmatch(r"([0-9a-f]{64})  ([^/\\]+)", line)
        if not match or match[2] in {".", "..", "SHA256SUMS-CI"}:
            raise ValueError("Invalid original checksum entry")
        name = match[2]
        if name in checked or not (directory / name).is_file():
            raise ValueError(f"Duplicate or missing original file: {name}")
        if (directory / name).is_symlink() or digest(directory / name) != match[1]:
            raise ValueError(f"Original artifact checksum mismatch: {name}")
        checked.add(name)
    expected = {path.name for path in directory.iterdir()} - {"SHA256SUMS-CI"}
    if checked != expected:
        raise ValueError("Original checksum list does not cover the complete artifact")


def identity(args):
    run = read_json(args.run_metadata)
    tag = re.fullmatch(r"sbe1v1k-wifi-(yes|no)-([0-9]+)-([0-9]+)", args.tag)
    if not tag or tag[1] != args.wifi or int(tag[2]) != run["id"]:
        raise ValueError("Release tag does not match the original build")
    if run["head_sha"] != args.ci_commit or run["path"] != ".github/workflows/SBE1V1K.yml":
        raise ValueError("Original build CI revision or workflow does not match")
    created = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
    if created.tzinfo is None:
        raise ValueError("Build creation time must have a timezone")
    local_time = created.astimezone(BUILD_TIMEZONE)
    source = read_json(args.artifacts / "ci-source.json")
    parsed = urlparse(source["repository"])
    owner = parsed.path.strip("/").split("/")[0]
    components = (owner, source["branch"])
    if parsed.hostname != "github.com" or not all(re.fullmatch(r"[\w.-]+", s) for s in components):
        raise ValueError("Source repository or branch cannot be used in release filenames")
    stamp = local_time.strftime("%y.%m.%d-%H.%M.%S")
    suffix = f"{owner}-{source['branch']}-wifi-{args.wifi}-{stamp}"
    title = f"SBE1V1K-WIFI-{args.wifi.upper()}-{owner}-{source['branch']}-{stamp}"
    return {"title": title, "tag": args.tag, "run_id": run["id"],
            "ci_commit": args.ci_commit, "build_time": local_time.isoformat(),
            "wifi": args.wifi, "suffix": suffix, "source": source}


def asset_record(path, original=None):
    return {"original": original, "name": path.name,
            "sha256": digest(path), "size": path.stat().st_size}


def copy_asset(directory, destination, names):
    original, renamed = names
    target = destination / renamed
    shutil.copy2(directory / original, target)
    return asset_record(target, original)


def copy_downloads(args, plan, destination):
    profile = read_json(args.artifacts / "profiles.json")["profiles"][DEVICE]
    firmware = []
    for entry in profile["images"]:
        original = entry["name"]
        path = Path(original.removeprefix("immortalwrt-"))
        renamed = f"{path.stem}-{plan['suffix']}{path.suffix}"
        firmware.append(copy_asset(args.artifacts, destination, (original, renamed)))
    config = copy_asset(args.artifacts, destination,
                        ("config.txt", f"Config-{plan['title']}.txt"))
    manifest = next(args.artifacts.glob("*.manifest"))
    manifest_name = f"qualcommbe-ipq95xx-{DEVICE}-{plan['suffix']}.manifest"
    listing = copy_asset(args.artifacts, destination, (manifest.name, manifest_name))
    return firmware, [*firmware, config, listing]


def tar_entry(archive, name, data):
    entry = tarfile.TarInfo(name)
    entry.size = len(data)
    entry.mode = 0o644
    archive.addfile(entry, io.BytesIO(data))


def archive_records(args, plan, destination):
    target = destination / f"build-records-{plan['title']}.tar.gz"
    images = {item["original"] for item in plan["firmware"]}
    mapping = {key: plan[key] for key in
               ("title", "tag", "run_id", "ci_commit", "build_time", "wifi", "assets")}
    with (target.open("wb") as output,
          gzip.GzipFile(fileobj=output, mode="wb", mtime=0, filename="") as compressed,
          tarfile.open(fileobj=compressed, mode="w") as archive):
        for path in sorted(args.artifacts.iterdir()):
            if path.name not in images:
                tar_entry(archive, path.name, path.read_bytes())
        tar_entry(archive, "release-files.json", (json.dumps(mapping, indent=2) + "\n").encode())
    return asset_record(target)


def write_checksums(plan, destination):
    target = destination / f"SHA256SUMS-{plan['title']}"
    entries = sorted(plan["assets"], key=lambda item: item["name"])
    target.write_text("".join(f"{item['sha256']}  {item['name']}\n" for item in entries), encoding="utf-8")
    return asset_record(target)


def prepare(args):
    verify_original(args.artifacts)
    verify_images(args.artifacts, args.wifi)
    plan = identity(args)
    destination = args.output / "assets"
    destination.mkdir(parents=True, exist_ok=False)
    firmware, assets = copy_downloads(args, plan, destination)
    plan = {**plan, "firmware": firmware, "assets": assets}
    records = archive_records(args, plan, destination)
    plan = {**plan, "assets": [*assets, records]}
    checksums = write_checksums(plan, destination)
    plan = {**plan, "checksum_file": checksums["name"], "assets": [*plan["assets"], checksums]}
    notes = render_notes(args, plan)
    (args.output / "release-notes.md").write_text(notes, encoding="utf-8")
    (args.output / "release-plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-metadata", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--ci-commit", required=True)
    parser.add_argument("--wifi", choices=["yes", "no"], required=True)
    print(prepare(parser.parse_args())["title"])


if __name__ == "__main__":
    main()
