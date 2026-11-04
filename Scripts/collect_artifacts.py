#!/usr/bin/env python3
"""Verify device images and collect firmware plus reproducibility records."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from integrate_local import verify_local_packages

DEVICE = "askey_sbe1v1k"
REQUIRED_PACKAGES = {
    "f2fsck", "mkf2fs", "f2fs-tools", "kmod-fs-f2fs", "kmod-qcom-ppe",
    "kmod-hwmon-pwmfan", "kmod-phy-realtek", "rtl826x-firmware"
}
WIRELESS_PACKAGES = {"kmod-ath12k", "ath12k-firmware-qcn9274-ddwrt", "ipq-wifi-askey_sbe1v1k"}
ALL_WIRELESS_PACKAGES = WIRELESS_PACKAGES | {"ath12k-firmware-qcn9274"}
IMAGE_SUFFIXES = ("-initramfs-uImage.itb", "-squashfs-sysupgrade.bin", "-squashfs-factory.bin")


def verify_manifest(path, wifi):
    packages = {line.split(" - ", 1)[0] for line in path.read_text().splitlines()}
    required = REQUIRED_PACKAGES | (WIRELESS_PACKAGES if wifi == "yes" else set())
    missing = required - packages
    if missing:
        raise ValueError(f"Missing device packages in {path.name}: {sorted(missing)}")
    if wifi == "no" and packages & ALL_WIRELESS_PACKAGES:
        raise ValueError(f"Wireless packages remain: {sorted(packages & ALL_WIRELESS_PACKAGES)}")


def verify_images(target, wifi):
    profiles = json.loads((target / "profiles.json").read_text())["profiles"]
    if set(profiles) != {DEVICE}:
        raise ValueError(f"Unexpected firmware profiles: {sorted(profiles)}")
    images = [entry["name"] for entry in profiles[DEVICE]["images"]]
    for suffix in IMAGE_SUFFIXES:
        matches = [name for name in images if name.endswith(suffix)]
        if len(matches) != 1:
            raise ValueError(f"Expected one {suffix} image, got {matches}")
    for entry in profiles[DEVICE]["images"]:
        path = target / entry["name"]
        if path.parent.resolve() != target.resolve() or not path.is_file():
            raise ValueError(f"Invalid or missing firmware image: {path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry["sha256"]:
            raise ValueError(f"Image hash mismatch: {path.name}")
    manifests = list(target.glob("*.manifest"))
    if len(manifests) != 1:
        raise ValueError(f"Expected one firmware manifest, got {manifests}")
    verify_manifest(manifests[0], wifi)


def collect(args):
    args.output.mkdir(parents=True, exist_ok=False)
    records = [".config", "ci-source.json", "ci-feeds.json", "ci-packages.json", "ci-diffconfig.txt"]
    for name in records:
        shutil.copy2(args.source / name, args.output / ("config.txt" if name == ".config" else name))
    for name in ("backend-components.json", "package-integration.json", "local-packages.json", "cache.json"):
        shutil.copy2(args.source / "ci-build" / name, args.output / f"ci-{name}")
    if not args.config_only:
        target = args.source / "bin/targets/qualcommbe/ipq95xx"
        verify_images(target, args.wifi)
        verify_local_packages(target, args.source / "ci-build/local-packages.json")
        for path in target.iterdir():
            if path.is_dir():
                shutil.make_archive(str(args.output / path.name), "gztar", root_dir=path)
            else:
                shutil.copy2(path, args.output / path.name)
    records = sorted(path for path in args.output.rglob("*") if path.is_file())
    lines = [f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(args.output).as_posix()}"
             for path in records]
    (args.output / "SHA256SUMS-CI").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wifi", choices=["yes", "no"], required=True)
    parser.add_argument("--config-only", action="store_true")
    collect(parser.parse_args())


if __name__ == "__main__":
    main()
