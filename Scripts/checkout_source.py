#!/usr/bin/env python3
"""Fetch the requested upstream revision and record its resolved commit."""

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_git(destination, arguments):
    return subprocess.check_output(
        ["git", "-C", str(destination), *arguments], text=True
    ).strip()


def checkout(destination, requested_ref):
    settings = json.loads((ROOT / "Config/source.json").read_text())
    revision = requested_ref or settings["revision"]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", revision):
        raise ValueError("SOURCE_REF must be a commit, tag or branch name")
    destination.mkdir(parents=True, exist_ok=False)
    run_git(destination, ["init"])
    run_git(destination, ["remote", "add", "origin", settings["repository"]])
    run_git(destination, ["fetch", "--depth=1", "origin", revision])
    run_git(destination, ["checkout", "--detach", "FETCH_HEAD"])
    evidence = dict(settings, requested_ref=revision)
    evidence["commit"] = run_git(destination, ["rev-parse", "HEAD"])
    output = destination / "ci-source.json"
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--ref", default="")
    args = parser.parse_args()
    checkout(args.destination, args.ref)


if __name__ == "__main__":
    main()
