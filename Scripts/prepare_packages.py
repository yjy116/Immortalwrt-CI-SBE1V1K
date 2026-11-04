#!/usr/bin/env python3
"""Install pinned external packages after feeds update/install, before defconfig.

Only explicit source directories are copied into package/custom-ci. Existing
destinations are errors: use a clean build tree when changing the manifest.
Do not run feeds install again after replacement; its index predates removal.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
from urllib.parse import urlparse


NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]*\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
SCHEMA_VERSION = 1


def relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"Invalid relative path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValueError(f"Unsafe relative path: {value!r}")
    if any(":" in part for part in path.parts):
        raise ValueError(f"Unsafe relative path: {value!r}")
    return path


def validate_url(value):
    if not isinstance(value, str):
        raise ValueError("Repository URL must be a string")
    url = urlparse(value)
    if url.scheme not in {"https", "file"} or not url.path:
        raise ValueError("Repository URLs must use https or local file transport")
    if url.username or url.password or url.query or url.fragment:
        raise ValueError("Repository URLs must not contain credentials, queries or fragments")
    if url.scheme == "https" and not url.hostname:
        raise ValueError("HTTPS repository URL requires a host")


def validate_name(value, pattern):
    return isinstance(value, str) and pattern.fullmatch(value)


def validate_package(package):
    if not isinstance(package, dict) or not validate_name(package.get("name"), NAME):
        raise ValueError("Each package requires a safe provider name")
    path = relative_path(package.get("path"))
    if path.name != package["name"]:
        raise ValueError("Package path basename must equal its provider name")


def validate_source(entry):
    if not isinstance(entry, dict) or not validate_name(entry.get("name"), NAME):
        raise ValueError("Each source requires a safe name")
    if not validate_name(entry.get("commit"), SHA):
        raise ValueError("Each source requires a full lowercase Git commit SHA")
    validate_url(entry.get("url"))
    packages = entry.get("packages")
    if not isinstance(packages, list) or not packages:
        raise ValueError("Each source requires explicit packages")
    for package in packages:
        validate_package(package)
    files = entry.get("files", [])
    if not isinstance(files, list):
        raise ValueError("Source files must be a list")
    for filename in files:
        relative_path(filename)


def read_manifest(path):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA_VERSION:
        raise ValueError("Unsupported package manifest schema")
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        raise ValueError("Manifest sources must be a list")
    for entry in sources:
        validate_source(entry)
    names = [entry["name"] for entry in sources]
    packages = [p["name"] for entry in sources for p in entry["packages"]]
    if len(names) != len(set(names)) or len(packages) != len(set(packages)):
        raise ValueError("Duplicate source or package provider in manifest")
    return sources


def within(path, root):
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes permitted directory: {path}")
    return resolved


def check_layout(source, output):
    for marker in ["Makefile", "include/package.mk", "feeds/luci/luci.mk"]:
        if not (source / marker).is_file():
            raise ValueError(f"Missing OpenWrt/feed marker: {marker}")
    for directory in ["package", "package/feeds", "feeds"]:
        if not within(source / directory, source).is_dir():
            raise ValueError(f"Run feeds update and install first: {directory}")
    if output.exists():
        raise ValueError("Metadata output must be a new file")
    within(source / "package/custom-ci", source)
    if (source / "package/custom-ci").is_symlink():
        raise ValueError("package/custom-ci must not be a symlink")


def git(repository, arguments):
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments], check=True,
        text=True, stdout=subprocess.PIPE,
    )
    return completed.stdout.strip()


def validate_checkout(repo, entry):
    for package in entry["packages"]:
        directory = within(repo / package["path"], repo)
        if not (directory / "Makefile").is_file():
            raise ValueError(f"Missing package Makefile: {package['path']}")
        for root, directories, files in os.walk(directory, followlinks=False):
            for name in directories + files:
                within(Path(root) / name, repo)
    for filename in entry.get("files", []):
        if not within(repo / filename, repo).is_file():
            raise ValueError(f"Missing shared source file: {filename}")


def stage_source(entry, temporary):
    repository = temporary / "repos" / entry["name"]
    repository.mkdir(parents=True)
    git(repository, ["init", "--quiet"])
    git(repository, ["remote", "add", "origin", entry["url"]])
    git(repository, ["fetch", "--depth=1", "origin", entry["commit"]])
    git(repository, ["checkout", "--quiet", "--detach", "FETCH_HEAD"])
    actual = git(repository, ["rev-parse", "HEAD"])
    if actual != entry["commit"]:
        raise ValueError(f"Fetched commit mismatch for {entry['name']}: {actual}")
    validate_checkout(repository, entry)
    staged = temporary / "packages" / entry["name"]
    staged.mkdir(parents=True)
    for package in entry["packages"]:
        shutil.copytree(repository / package["path"], staged / package["name"])
    for filename in entry.get("files", []):
        destination = staged / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repository / filename, destination)
    return staged


def feed_providers(source, names):
    feeds = source / "feeds"
    providers = []
    for root, directories, files in os.walk(feeds, followlinks=False):
        directories[:] = [name for name in directories if name != ".git"]
        path = Path(root)
        if path.name in names and "Makefile" in files:
            providers.append(within(path, feeds))
            directories.clear()
    return providers


def feed_links(source, names, providers):
    installed = source / "package/feeds"
    links = []
    for feed in installed.iterdir():
        within(feed, installed)
        if not feed.is_dir():
            continue
        for path in feed.iterdir():
            if path.name not in names and path.resolve() not in providers:
                continue
            if not path.is_symlink():
                raise ValueError(f"Expected feed installation symlink: {path}")
            links.append(path)
    return links


def prepare_installation(source, sources):
    destination = source / "package/custom-ci"
    for entry in sources:
        path = destination / entry["name"]
        if path.exists() or path.is_symlink():
            raise ValueError(f"Package destination already exists: {path}")
    names = {p["name"] for entry in sources for p in entry["packages"]}
    providers = feed_providers(source, names)
    links = feed_links(source, names, providers)
    return destination, providers, links


def install_sources(staged, source, plan):
    destination, providers, links = plan
    removed = [str(path.relative_to(source)) for path in links + providers]
    for link in links:
        link.unlink()
    for provider in providers:
        within(provider, source / "feeds")
        shutil.rmtree(provider)
    destination.mkdir(parents=True, exist_ok=True)
    for package_source in staged:
        shutil.copytree(package_source, destination / package_source.name)
    return removed


def prepare(source, manifest, output):
    source = source.resolve()
    output = output.resolve()
    sources = read_manifest(manifest)
    check_layout(source, output)
    plan = prepare_installation(source, sources)
    with tempfile.TemporaryDirectory(prefix="openwrt-packages-") as temporary:
        staged = [stage_source(entry, Path(temporary)) for entry in sources]
        removed = install_sources(staged, source, plan)
    metadata = {
        "schema": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "removed_providers": removed,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Installed {len(sources)} pinned package sources; provenance: {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    prepare(arguments.source, arguments.manifest, arguments.output)


if __name__ == "__main__":
    main()
