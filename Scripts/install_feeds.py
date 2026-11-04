#!/usr/bin/env python3
"""Install selected official feed packages and explicit custom build dependencies."""

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def selected_packages(config, manifest):
    requested = set(re.findall(r"^CONFIG_PACKAGE_([^=]+)=y$", config, re.MULTILINE))
    custom = {package["name"] for source in manifest["sources"] for package in source["packages"]}
    return requested - custom


def install(source):
    manifest = json.loads((ROOT / "Config/packages.json").read_text())
    config = (ROOT / "Config/GENERAL.txt").read_text()
    listing = subprocess.check_output(["./scripts/feeds", "list"], cwd=source, text=True)
    available = {line.split()[0] for line in listing.splitlines() if line.strip()}
    dependencies = set(manifest["feed_dependencies"])
    missing = dependencies - available
    if missing:
        raise ValueError(f"Missing external package feed dependencies: {sorted(missing)}")
    packages = sorted((selected_packages(config, manifest) & available) | dependencies)
    if not packages:
        raise ValueError("No selected packages found in official feeds")
    subprocess.run(["./scripts/feeds", "install", *packages], cwd=source, check=True)
    print(f"Installed {len(packages)} requested official feed packages and their dependencies")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    install(parser.parse_args().source.resolve())


if __name__ == "__main__":
    main()
