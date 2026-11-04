#!/usr/bin/env python3
"""Align shared package ownership and record the paired UPnP source recipes."""

import argparse
import hashlib
import json
import re
from pathlib import Path


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tailscale_recipe(text):
    patterns = (
        r"\t\$\(INSTALL_BIN\) \./files/+tailscale\.init \$\(1\)/etc/init\.d/tailscale",
        r"\t\$\(INSTALL_DATA\) \./files/+tailscale\.conf \$\(1\)/etc/config/tailscale",
    )
    for pattern in patterns:
        text, count = re.subn("^" + pattern + "$", "", text, flags=re.M)
        if count != 1:
            raise ValueError("Tailscale install recipe changed; review init/config ownership")
    if re.search(r"^.*\./files/.*$", text, re.M):
        raise ValueError("Additional Tailscale runtime files need ownership review")
    return text


def align_tailscale(source):
    ui = source / "package/custom-ci/tailscale-ui/luci-app-tailscale"
    required = ("root/etc/init.d/tailscale", "root/etc/config/tailscale")
    for name in required:
        if not (ui / name).is_file():
            raise ValueError(f"Missing Tailscale UI runtime provider: {name}")
    path = source / "feeds/packages/net/tailscale/Makefile"
    original = checksum(path)
    updated = tailscale_recipe(path.read_text(encoding="utf-8"))
    path.write_text(updated, encoding="utf-8")
    return {"runtime_provider": "asvow/luci-app-tailscale", "original_sha256": original,
            "integrated_sha256": checksum(path),
            "runtime_files": {name: checksum(ui / name) for name in required}}


def make_values(path, fields):
    values = dict(re.findall(r"^(\w+):=(.*)$", path.read_text(encoding="utf-8"), re.M))
    missing = set(fields) - values.keys()
    if missing:
        raise ValueError(f"Missing recipe fields in {path}: {sorted(missing)}")
    return {key: values[key] for key in fields}


def upnp_pair(source):
    metadata = json.loads((source / "ci-packages.json").read_text(encoding="utf-8"))
    provider = next(entry for entry in metadata["sources"] if entry["name"] == "viking")
    root = source / "package/custom-ci/viking"
    core, ui = root / "miniupnpd/Makefile", root / "luci-app-upnp/Makefile"
    rpc = root / "luci-app-upnp/root/usr/share/rpcd/ucode/luci.upnp"
    return {
        "mode": "upstream-pair", "provider": provider["url"],
        "branch": provider["branch"], "commit": provider["commit"],
        "miniupnpd": make_values(core, ("PKG_VERSION", "PKG_RELEASE", "PKG_SOURCE_VERSION", "PKG_HASH")),
        "luci-app-upnp": make_values(ui, ("PKG_VERSION", "PKG_RELEASE")),
        "file_sha256": {path.relative_to(root).as_posix(): checksum(path) for path in (core, ui, rpc)},
    }


def integrate(source):
    report = {"upnp": upnp_pair(source), "tailscale": align_tailscale(source)}
    output = source / "ci-build/package-integration.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Package integration recorded: {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    integrate(parser.parse_args().source.resolve())


if __name__ == "__main__":
    main()
