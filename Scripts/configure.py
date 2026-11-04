#!/usr/bin/env python3
"""Expand and verify the SBE1V1K configuration against real upstream Kconfig."""

import argparse
import json
import re
import subprocess
from pathlib import Path

from defaults import apply_defaults

ROOT = Path(__file__).resolve().parents[1]
DEVICE_SYMBOL = "CONFIG_TARGET_qualcommbe_ipq95xx_DEVICE_askey_sbe1v1k"


def parse_config(text):
    result = {}
    for line in text.splitlines():
        enabled = re.fullmatch(r"(CONFIG_[^= ]+)=(.*)", line)
        disabled = re.fullmatch(r"# (CONFIG_[^ ]+) is not set", line)
        if enabled:
            result[enabled[1]] = enabled[2]
        elif disabled:
            result[disabled[1]] = "n"
    return result


def verify(requested, expanded):
    errors = []
    for symbol, value in requested.items():
        if expanded.get(symbol, "n") != value:
            errors.append(f"{symbol}: requested {value}, got {expanded.get(symbol)}")
    devices = [key for key, value in expanded.items()
               if key.startswith("CONFIG_TARGET_") and "_DEVICE_" in key
               and not key.startswith("CONFIG_TARGET_DEVICE_PACKAGES_")
               and value == "y"]
    if devices != [DEVICE_SYMBOL]:
        errors.append(f"Expected exactly SBE1V1K, got {devices}")
    if errors:
        raise ValueError("Configuration did not survive make defconfig:\n" + "\n".join(errors))


def record_feeds(source):
    result = {}
    for feed in sorted((source / "feeds").iterdir()):
        if not feed.is_dir() or not (feed / ".git").exists():
            continue
        result[feed.name] = subprocess.check_output(
            ["git", "-C", str(feed), "rev-parse", "HEAD"], text=True
        ).strip()
    if not result:
        raise ValueError("No Git feed revisions were recorded")
    (source / "ci-feeds.json").write_text(json.dumps(result, indent=2) + "\n")


def expand_config(source):
    result = subprocess.run(["make", "defconfig"], cwd=source, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(result.stdout, end="", flush=True)
    (source / "ci-defconfig.log").write_text(result.stdout, encoding="utf-8")
    result.check_returncode()
    if re.search(r"(^|\n).*\berror:", result.stdout, re.IGNORECASE):
        raise ValueError("Kconfig reported errors; see ci-defconfig.log")


def configure(source, wifi):
    profile = ROOT / "Config" / f"SBE1V1K-WIFI-{wifi.upper()}.txt"
    fragments = [profile, ROOT / "Config/GENERAL.txt"]
    text = "\n".join(path.read_text() for path in fragments)
    requested = parse_config(text)
    config = source / ".config"
    config.write_text(text, encoding="utf-8")
    apply_defaults(source)
    expand_config(source)
    verify(requested, parse_config(config.read_text()))
    record_feeds(source)
    diff = subprocess.check_output(["./scripts/diffconfig.sh"], cwd=source)
    (source / "ci-diffconfig.txt").write_bytes(diff)
    print(f"Validated {len(requested)} requested options for WiFi-{wifi}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--wifi", choices=["yes", "no"], required=True)
    args = parser.parse_args()
    configure(args.source.resolve(), args.wifi)


if __name__ == "__main__":
    main()
