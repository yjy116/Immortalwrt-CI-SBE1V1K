"""Validate package sources and resolve moving branches for one CI run."""
import json
from pathlib import PurePosixPath
import re
import subprocess
from urllib.parse import urlparse


SCHEMA_VERSION = 2
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]*\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")


def matches(value, pattern):
    return isinstance(value, str) and pattern.fullmatch(value)


def relative_path(value, allow_root=False):
    if value == "." and allow_root:
        return PurePosixPath(value)
    return nonroot_path(value)


def nonroot_path(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"Invalid relative path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", "..", ".git"} for part in value.split("/")):
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


def validate_package(package):
    if not isinstance(package, dict) or not matches(package.get("name"), NAME):
        raise ValueError("Each package requires a safe provider name")
    relative_path(package.get("path"), allow_root=True)


def validate_source(entry):
    if not isinstance(entry, dict) or not matches(entry.get("name"), NAME):
        raise ValueError("Each source requires a safe name")
    if "commit" in entry or not isinstance(entry.get("branch"), str):
        raise ValueError("Package sources must follow a branch, without a pinned commit")
    subprocess.run(["git", "check-ref-format", f"refs/heads/{entry['branch']}"], check=True)
    validate_url(entry.get("url"))
    if entry.get("layout", "selected") not in {"selected", "repository"}:
        raise ValueError("Package layout must be selected or repository")
    packages = entry.get("packages")
    if not isinstance(packages, list) or not packages:
        raise ValueError("Each source requires explicit packages")
    for package in packages:
        validate_package(package)
    validate_files(entry.get("files", []))


def validate_files(files):
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
    return manifest


def resolve_branch(entry):
    branch_ref = f"refs/heads/{entry['branch']}"
    output = subprocess.check_output(
        ["git", "ls-remote", "--exit-code", entry["url"], branch_ref], text=True,
    ).strip().splitlines()
    if len(output) != 1:
        raise ValueError(f"Expected one branch for {entry['name']}: {branch_ref}")
    fields = output[0].split()
    if len(fields) != 2 or fields[1] != branch_ref or not matches(fields[0], SHA):
        raise ValueError(f"Invalid branch response for {entry['name']}")
    return fields[0]


def resolve_snapshots(sources):
    return {entry["name"]: resolve_branch(entry) for entry in sources}


def read_snapshots(path, sources):
    snapshots = json.loads(path.read_text(encoding="utf-8"))
    names = {entry["name"] for entry in sources}
    if not isinstance(snapshots, dict) or set(snapshots) != names:
        raise ValueError("Snapshots must contain exactly the configured source names")
    if not all(matches(commit, SHA) for commit in snapshots.values()):
        raise ValueError("Every package snapshot must be a full lowercase commit SHA")
    return snapshots


def source_snapshots(manifest, snapshots_path=None):
    sources = manifest["sources"]
    snapshots = (read_snapshots(snapshots_path, sources) if snapshots_path
                 else resolve_snapshots(sources))
    return [dict(entry, commit=snapshots[entry["name"]]) for entry in sources]
