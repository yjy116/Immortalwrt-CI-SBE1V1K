#!/usr/bin/env python3
"""Install repository-owned device packages and record their exact source files."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_PACKAGES = ("luci-app-sbe1v1k-fan",)


def integrate(source, packages):
    destination = source / "package/custom-ci/local"
    if destination.exists():
        raise ValueError(f"Local package destination already exists: {destination}")
    records = {}
    for name in LOCAL_PACKAGES:
        package = packages / name
        if not (package / "Makefile").is_file():
            raise ValueError(f"Missing local package recipe: {name}")
        records[name] = {
            path.relative_to(package).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(package.rglob("*")) if path.is_file()
        }
    destination.mkdir(parents=True)
    for name in LOCAL_PACKAGES:
        shutil.copytree(packages / name, destination / name)
    output = source / "ci-build/local-packages.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"schema": 1, "packages": records}, indent=2) + "\n", encoding="utf-8")
    print(f"Installed local device packages: {', '.join(LOCAL_PACKAGES)}")


def verify_local_packages(target, record):
    metadata = json.loads(record.read_text(encoding="utf-8"))
    manifests = list(target.glob("*.manifest"))
    if len(manifests) != 1:
        raise ValueError("Expected exactly one firmware package manifest")
    installed = {line.split(" - ", 1)[0] for line in manifests[0].read_text().splitlines()}
    missing = set(metadata["packages"]) - installed
    if missing:
        raise ValueError(f"Missing local device packages in firmware: {sorted(missing)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    integrate(parser.parse_args().source.resolve(), ROOT / "packages")


if __name__ == "__main__":
    main()
