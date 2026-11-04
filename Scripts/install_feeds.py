#!/usr/bin/env python3
"""Install selected official feed packages and explicit custom build dependencies."""

import argparse
import re
import subprocess
from pathlib import Path

from package_manifest import NAME, matches, read_manifest

ROOT = Path(__file__).resolve().parents[1]


def selected_packages(config, manifest):
    requested = set(re.findall(r"^CONFIG_PACKAGE_([^=]+)=y$", config, re.MULTILINE))
    custom = {package["name"] for source in manifest["sources"] for package in source["packages"]}
    return {name for name in requested - custom if not name.startswith("luci-i18n-")}


def installation_packages(config, manifest, available):
    dependencies = manifest.get("feed_dependencies")
    if not isinstance(dependencies, list) or not all(matches(name, NAME) for name in dependencies):
        raise ValueError("Manifest feed_dependencies must be a list of package names")
    missing = set(dependencies) - available
    if missing:
        raise ValueError(f"Missing external package feed dependencies: {sorted(missing)}")
    packages = sorted((selected_packages(config, manifest) & available) | set(dependencies))
    if not packages:
        raise ValueError("No selected packages found in official feeds")
    return packages


def install(source):
    manifest = read_manifest(ROOT / "Config/packages.json")
    config = (ROOT / "Config/GENERAL.txt").read_text()
    listing = subprocess.check_output(["./scripts/feeds", "list"], cwd=source, text=True)
    available = {line.split()[0] for line in listing.splitlines() if line.strip()}
    packages = installation_packages(config, manifest, available)
    subprocess.run(["./scripts/feeds", "install", *packages], cwd=source, check=True)
    print(f"Installed {len(packages)} requested official feed packages and their dependencies")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    install(parser.parse_args().source.resolve())


if __name__ == "__main__":
    main()
