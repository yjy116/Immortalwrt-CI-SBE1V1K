#!/usr/bin/env python3
"""Key compatible OpenWrt tools/toolchains and refresh restored install stamps."""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import time
from pathlib import Path

from configure import parse_config

ROOT = Path(__file__).resolve().parents[1]
CACHE_VERSION = "sbe1v1k-build-v1"
SOURCE_PATHS = (
    "Makefile", "rules.mk", "config", "include", "scripts", "tools", "toolchain",
    "target/linux/generic", "target/linux/qualcommbe",
)
ENGINE_PATHS = ("Scripts/build_cache.py", "Scripts/setup_runner.sh")


def checksum(data):
    return hashlib.sha256(data).hexdigest()


def command(arguments):
    return subprocess.check_output(arguments, text=True).strip()


def source_objects(source):
    objects = {}
    for name in SOURCE_PATHS:
        if not (source / name).exists():
            raise ValueError(f"Missing cache source path: {name}")
        objects[name] = command(["git", "-C", str(source), "rev-parse", f"HEAD:{name}"])
    return objects


def working_changes(source):
    git = ["git", "-C", str(source)]
    diff = subprocess.check_output([*git, "diff", "--binary", "HEAD", "--", *SOURCE_PATHS])
    names = subprocess.check_output(
        [*git, "ls-files", "--others", "--exclude-standard", "-z", "--", *SOURCE_PATHS]
    ).decode().split("\0")
    untracked = {}
    for name in filter(None, names):
        path = source / name
        if not path.resolve().is_relative_to(source.resolve()):
            raise ValueError(f"Cache source file escapes checkout: {name}")
        untracked[name] = checksum(path.read_bytes())
    return {"tracked_sha256": checksum(diff), "untracked": untracked}


def cache_identity(source, host):
    provenance = json.loads((source / "ci-source.json").read_text(encoding="utf-8"))
    inputs = {
        "version": CACHE_VERSION, "host": host, "build_directory": str(source.resolve()),
        "repository": provenance["repository"], "branch": provenance["branch"],
        "source_objects": source_objects(source),
        "working_changes": working_changes(source),
        "config": parse_config((source / ".config").read_text(encoding="utf-8")),
        "engine": {name: checksum((ROOT / name).read_bytes()) for name in ENGINE_PATHS},
    }
    serialized = json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()
    return {"key": f"{CACHE_VERSION}-{checksum(serialized)}", "inputs": inputs}


def host_signature():
    os_release = Path("/etc/os-release").read_text(encoding="utf-8")
    return {
        "os_release": os_release, "architecture": platform.machine(),
        "gcc": command(["gcc", "-dumpfullversion"]),
        "g++": command(["g++", "-dumpfullversion"]),
        "libc": command(["ldd", "--version"]).splitlines()[0],
        "linker": command(["ld", "--version"]).splitlines()[0],
    }


def refresh_stamps(source):
    staging = source / "staging_dir"
    roots = [staging / "host", *sorted(staging.glob("toolchain-*"))]
    if len(roots) < 2 or not all(path.is_dir() for path in roots):
        raise ValueError("Restored cache is missing host tools or target toolchain")
    count = 0
    timestamp = time.time_ns()
    for root in roots:
        count += refresh_root(root, staging, timestamp)
    if count == 0:
        raise ValueError("Restored cache has no installed tool/toolchain stamps")
    (source / "tmp").mkdir(exist_ok=True)
    (source / "tmp/.build").write_text("1\n", encoding="utf-8")
    return count


def refresh_root(root, staging, timestamp):
    if not root.resolve().is_relative_to(staging.resolve()):
        raise ValueError(f"Cache root escapes staging directory: {root}")
    files = [path for stamp in root.rglob("stamp") if stamp.is_dir()
             for path in stamp.rglob("*") if path.is_file()]
    for path in files:
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Cache stamp escapes its root: {path}")
        os.utime(path, ns=(timestamp, timestamp))
    return len(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["key", "refresh"])
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    if args.action == "refresh":
        print(f"Refreshed {refresh_stamps(source)} compatible installed stamps")
        return
    identity = cache_identity(source, host_signature())
    output = source / "ci-build/cache.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    print(identity["key"])


if __name__ == "__main__":
    main()
