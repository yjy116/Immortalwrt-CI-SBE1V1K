#!/usr/bin/env python3
"""Follow the configured branch, optionally sharing one workflow-run snapshot."""

import argparse
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
COMMIT_SHA = re.compile(r"[0-9a-f]{40}\Z")


def run_git(destination, arguments):
    return subprocess.check_output(
        ["git", "-C", str(destination), *arguments], text=True
    ).strip()


def read_settings(path):
    settings = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(settings, dict):
        raise ValueError("Source settings must be a JSON object")
    branch = settings.get("branch")
    repository = settings.get("repository")
    if not isinstance(branch, str) or not branch:
        raise ValueError("Source branch must be a nonempty string")
    if not isinstance(repository, str):
        raise ValueError("Source repository must be a URL")
    url = urlparse(repository)
    if url.scheme not in {"https", "file"} or not url.path:
        raise ValueError("Source repository must use HTTPS or local file transport")
    subprocess.run(["git", "check-ref-format", f"refs/heads/{branch}"], check=True)
    return settings


def resolve_branch(settings):
    branch_ref = f"refs/heads/{settings['branch']}"
    result = subprocess.check_output(
        ["git", "ls-remote", "--exit-code", settings["repository"], branch_ref],
        text=True,
    ).strip().splitlines()
    if len(result) != 1:
        raise ValueError(f"Expected exactly one remote branch: {branch_ref}")
    fields = result[0].split()
    if len(fields) != 2 or fields[1] != branch_ref or not COMMIT_SHA.fullmatch(fields[0]):
        raise ValueError(f"Invalid remote branch response: {branch_ref}")
    return fields[0]


def checkout(destination, settings, snapshot=None):
    if snapshot is not None and not COMMIT_SHA.fullmatch(snapshot):
        raise ValueError("Run snapshot must be a full commit SHA")
    revision = snapshot or resolve_branch(settings)
    requested_ref = snapshot or f"refs/heads/{settings['branch']}"
    destination.mkdir(parents=True, exist_ok=False)
    run_git(destination, ["init", "--quiet"])
    run_git(destination, ["remote", "add", "origin", settings["repository"]])
    run_git(destination, ["fetch", "--depth=1", "origin", revision])
    run_git(destination, ["checkout", "--quiet", "--detach", "FETCH_HEAD"])
    actual = run_git(destination, ["rev-parse", "HEAD"])
    if actual != revision:
        raise ValueError(f"Fetched source commit differs from run snapshot: {actual}")
    evidence = dict(settings, requested_ref=requested_ref, commit=actual)
    output = destination / "ci-source.json"
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--source-config", type=Path, default=ROOT / "Config/source.json")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--resolve-only", action="store_true")
    mode.add_argument("--snapshot", help="Commit resolved once for this workflow run")
    args = parser.parse_args()
    if not args.resolve_only and args.destination is None:
        parser.error("--destination is required unless --resolve-only is used")
    settings = read_settings(args.source_config)
    if args.resolve_only:
        print(resolve_branch(settings))
        return
    checkout(args.destination, settings, args.snapshot)


if __name__ == "__main__":
    main()
