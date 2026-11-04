#!/usr/bin/env python3
"""Integrate current branch recipes without replacing their component pins."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT_SECONDS = 60
MAKE_ASSIGNMENT = re.compile(r"^([A-Z][A-Z0-9_]*)\s*[:?+]?=\s*(.*?)\s*$", re.M)
SHA256 = re.compile(r"[0-9a-f]{64}")
RECIPE_FIELDS = ("PKG_VERSION", "PKG_RELEASE", "PKG_SOURCE", "PKG_SOURCE_URL", "PKG_HASH")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def assignments(path: Path) -> dict[str, str]:
    return dict(MAKE_ASSIGNMENT.findall(read(path)))


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recipe(path: Path) -> dict:
    values = assignments(path)
    require(all(key in values for key in RECIPE_FIELDS), f"Incomplete source recipe: {path}")
    return {"file_sha256": checksum(path), "fields": values}


def inspect_daede(directory: Path) -> dict:
    result = {}
    for name in ("dae", "daed"):
        entry = recipe(directory / name / "Makefile")
        values = entry["fields"]
        digest = values["PKG_HASH"]
        require(bool(SHA256.fullmatch(digest)), f"Invalid {name} source SHA-256")
        require(digest[:12] in values["PKG_SOURCE"], f"{name} source archive is not content-addressed")
        config = read(directory / name / "files" / f"{name}.config")
        require("option enabled '0'" in config, f"{name} must default to disabled")
        result[name] = entry
    result["component_pins"] = assignments(directory / "ci/pins.env")
    return result


def inspect_honk(directory: Path) -> dict:
    core = recipe(directory / "honk/Makefile")
    ui = recipe(directory / "luci-app-honk/Makefile")
    values, ui_values = core["fields"], ui["fields"]
    tag = values.get("HONK_SOURCE_TAG", "")
    require(bool(re.fullmatch(r"source-\d+", tag)), "Honk requires an immutable source release tag")
    require(ui_values.get("HONK_SOURCE_TAG") == tag, "Honk/Doona source tags differ")
    require(bool(re.fullmatch(r"[0-9a-f]{40}", values.get("CORE_COMMIT", ""))), "Invalid Honk core commit")
    for arch in ("X86_64", "AARCH64", "ARMV7"):
        require(bool(SHA256.fullmatch(values.get(f"HONK_HASH_{arch}", ""))), f"Invalid Honk {arch} SHA-256")
    require(bool(SHA256.fullmatch(ui_values["PKG_HASH"])), "Invalid Doona archive SHA-256")
    require(ui_values["PKG_HASH"][:12] in ui_values["PKG_SOURCE"], "Doona source archive is not content-addressed")
    for name in ("honk/generated-stage.mk", "luci-app-honk/generated-doona-stage.mk"):
        require(not (directory / name).exists(), f"Unexpected source recipe override: {name}")
    config = read(directory / "honk/files/honk.config")
    for name in ("enabled", "initialized"):
        require(f"option {name} '0'" in config, f"Honk must default to {name}=0")
    return {"honk": core, "doona": ui, "component_pins": assignments(directory / "ci/pins.env")}


def run(command: list[str], directory: Path) -> None:
    subprocess.run(command, cwd=directory, check=True, timeout=TIMEOUT_SECONDS)


def apply_patches(directory: Path, name: str) -> list[dict]:
    patch_tool = shutil.which("patch")
    require(patch_tool is not None, "patch is required for backend integration")
    result = []
    for path in sorted((ROOT / "Patches" / name).glob("*.patch")):
        command = [patch_tool, "-p1", "--fuzz=0", "--batch", "--forward", "-i", str(path)]
        run(command + ["--dry-run"], directory)
        run(command, directory)
        result.append({"path": path.relative_to(ROOT).as_posix(), "sha256": checksum(path)})
    require(bool(result), f"No backend integration patches found for {name}")
    return result


def install_migration(directory: Path) -> str:
    source = ROOT / "files/etc/uci-defaults/89-daede-migrate"
    target = directory / "luci-app-daede/root/etc/uci-defaults/89-daede-migrate"
    require(not target.exists(), "Upstream now provides 89-daede-migrate; review the migration")
    shutil.copyfile(source, target)
    target.chmod(0o755)
    return checksum(target)


def verify_honk_ui(directory: Path) -> None:
    overview = read(directory / "luci-app-honk/htdocs/luci-static/resources/view/honk/overview.js")
    for fragment in ("runAction(running ? 'stop' : 'start')", "runAction('restart')",
                     "running ? _('Stop') : _('Start')",
                     "running ? _('Running') : _('Stopped')", "honk.localWebUi(status)",
                     "honk[method]().then(honk.ensureOk)"):
        require(fragment in overview, f"Honk upstream UI action contract changed: {fragment}")
    rpc = read(directory / "luci-app-honk/htdocs/luci-static/resources/view/honk/rpc.js")
    for method in ("start", "stop", "restart"):
        require(f"method: '{method}'" in rpc, f"Honk UI RPC method missing: {method}")
        require(f"{method}: call{method.title()}" in rpc, f"Honk UI RPC export missing: {method}")
    control = read(directory / "honk/files/control.sh")
    require("ui: '/usr/share/doona'" in control, "Doona is no longer served by the Honk native API")


def validate_backends(paths: dict[str, Path]) -> None:
    bash, node = shutil.which("bash"), shutil.which("node")
    require(bash is not None and node is not None, "bash and node are required for backend regression checks")
    shell_tests = (
        ("migration", []), ("service", [paths["daede"]]),
        ("coexistence", [paths["daede"], paths["honk"]]),
        ("honk", [paths["honk"]]), ("geodata", [paths["geodata"]]),
    )
    for name, args in shell_tests:
        run([bash, str(ROOT / "Tests" / f"test_backends_{name}.sh"), *map(str, args)], ROOT)
    run([node, str(ROOT / "Tests/test_backends_switch.cjs"), str(paths["daede"])], ROOT)
    verify_honk_ui(paths["honk"])


def integrate(source: Path) -> Path:
    custom = source / "package/custom-ci"
    paths = {name: custom / name for name in ("daede", "honk")}
    paths["geodata"] = custom / "reference-tools/v2ray-geodata-updater"
    report = {"daede": inspect_daede(paths["daede"]), "honk": inspect_honk(paths["honk"])}
    report["recipe_stage"] = "raw upstream Makefile assignments before integration patches, not evaluated make values"
    report["patches"] = {"daede": apply_patches(paths["daede"], "daede"), "honk": []}
    report["migration_sha256"] = install_migration(paths["daede"])
    validate_backends(paths)
    report["validation"] = "real upstream shell/JS with router I/O fixtures; no device or BPF runtime verification"
    destination = source / "ci-build/backend-components.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Prepared ImmortalWrt source directory")
    args = parser.parse_args()
    print(f"Backend integration verified: {integrate(args.source.resolve())}")


if __name__ == "__main__":
    main()
