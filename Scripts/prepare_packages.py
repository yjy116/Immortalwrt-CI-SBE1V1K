#!/usr/bin/env python3
"""Install this run's external source snapshots before defconfig.

Only explicit source directories are copied into package/custom-ci. Existing
destinations are errors: use a clean build tree when changing the manifest.
Do not run feeds install again after replacement; its index predates removal.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from package_manifest import SCHEMA_VERSION, read_manifest, source_snapshots


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
        validate_tree(directory, repo)
    if entry.get("layout") == "repository":
        validate_tree(repo, repo)
    for filename in entry.get("files", []):
        if not within(repo / filename, repo).is_file():
            raise ValueError(f"Missing shared source file: {filename}")


def validate_tree(directory, repository):
    for root, directories, files in os.walk(directory, followlinks=False):
        directories[:] = [name for name in directories if name != ".git"]
        for name in directories + files:
            within(Path(root) / name, repository)


def copy_source(repository, staged, entry):
    ignore = shutil.ignore_patterns(".git")
    if entry.get("layout") == "repository":
        shutil.copytree(repository, staged, ignore=ignore)
        return
    staged.mkdir(parents=True)
    for package in entry["packages"]:
        shutil.copytree(repository / package["path"], staged / package["name"], ignore=ignore)
    for filename in entry.get("files", []):
        destination = staged / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repository / filename, destination)


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
    copy_source(repository, staged, entry)
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


def prepare(arguments):
    source = arguments.source.resolve()
    output = arguments.output.resolve()
    manifest = read_manifest(arguments.manifest)
    check_layout(source, output)
    plan = prepare_installation(source, manifest["sources"])
    sources = source_snapshots(manifest, arguments.snapshots)
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
    print(f"Installed {len(sources)} package source snapshots; provenance: {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--snapshots", type=Path, help="Source-name to commit JSON for this run")
    arguments = parser.parse_args()
    prepare(arguments)


if __name__ == "__main__":
    main()
