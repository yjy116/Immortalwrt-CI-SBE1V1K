#!/usr/bin/env python3
"""Print one JSON source-name to commit mapping for this workflow run."""
import argparse
import json
from pathlib import Path

from package_manifest import read_manifest, resolve_snapshots


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    manifest = read_manifest(parser.parse_args().manifest)
    print(json.dumps(resolve_snapshots(manifest["sources"]), sort_keys=True))


if __name__ == "__main__":
    main()
