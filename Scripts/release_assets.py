"""Verify draft uploads and remove only known legacy artifact attachments."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from release_layout import verify_original

EXPECTED_ASSET_COUNT = 7


def github(arguments):
    result = subprocess.run(
        ["gh", "api", *arguments], check=True, encoding="utf-8", stdout=subprocess.PIPE,
    )
    return json.loads(result.stdout) if result.stdout.strip() else None


def valid_name(name):
    return (isinstance(name, str) and name not in {".", ".."}
            and re.fullmatch(r"[^/\\\x00-\x1f]+", name) is not None)


def validate_context(plan):
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", plan["repository"]):
        raise ValueError("Invalid GitHub repository")
    if not re.fullmatch(r"sbe1v1k-wifi-(yes|no)-[1-9][0-9]*-[1-9][0-9]*", plan["tag"]):
        raise ValueError("Invalid release tag")


def validate_expected_asset(asset):
    if not valid_name(asset["name"]):
        raise ValueError("Invalid planned asset name")
    if not isinstance(asset["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", asset["sha256"]):
        raise ValueError(f"Invalid planned SHA256: {asset['name']}")
    if type(asset["size"]) is not int or asset["size"] < 0:
        raise ValueError(f"Invalid planned asset size: {asset['name']}")


def expected_assets(plan):
    validate_context(plan)
    assets = plan["assets"]
    if not isinstance(assets, list) or len(assets) != EXPECTED_ASSET_COUNT:
        raise ValueError("Release plan must contain exactly seven assets")
    expected = {}
    for asset in assets:
        validate_expected_asset(asset)
        if asset["name"] in expected:
            raise ValueError(f"Duplicate planned asset: {asset['name']}")
        expected[asset["name"]] = asset
    return expected


def paginated(api, endpoint):
    pages = api(["--paginate", "--slurp", endpoint])
    if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
        raise ValueError("Expected paginated GitHub arrays")
    entries = [entry for page in pages for entry in page]
    if any(not isinstance(entry, dict) for entry in entries):
        raise ValueError("Expected GitHub object entries")
    return entries


def object_id(item):
    identifier = item.get("id")
    if type(identifier) is not int or identifier <= 0:
        raise ValueError("Invalid GitHub object ID")
    return identifier


def draft_release(plan, api):
    releases = paginated(api, f"repos/{plan['repository']}/releases?per_page=100")
    matches = [entry for entry in releases if entry.get("tag_name") == plan["tag"]]
    if len(matches) != 1 or matches[0].get("draft") is not True:
        raise ValueError("Expected exactly one existing draft release")
    return object_id(matches[0])


def remote_assets(api, endpoint):
    assets = paginated(api, f"{endpoint}/assets?per_page=100")
    indexed = {}
    identifiers = set()
    for asset in assets:
        name = asset.get("name")
        identifier = object_id(asset)
        if not valid_name(name):
            raise ValueError("Invalid remote asset name")
        if name in indexed or identifier in identifiers:
            raise ValueError(f"Duplicate remote asset name or ID: {name}")
        indexed[name] = asset
        identifiers.add(identifier)
    return indexed


def verify_targets(expected, remote):
    missing = set(expected) - set(remote)
    if missing:
        raise ValueError(f"Missing uploaded assets: {sorted(missing)}")
    for name, planned in expected.items():
        uploaded = remote[name]
        if uploaded.get("state") != "uploaded":
            raise ValueError(f"Asset is not uploaded: {name}")
        if uploaded.get("digest") != f"sha256:{planned['sha256']}":
            raise ValueError(f"Uploaded SHA256 mismatch: {name}")
        if type(uploaded.get("size")) is not int or uploaded["size"] != planned["size"]:
            raise ValueError(f"Uploaded size mismatch: {name}")


def finalize_draft(plan, original_names, api):
    expected = expected_assets(plan)
    release_id = draft_release(plan, api)
    endpoint = f"repos/{plan['repository']}/releases/{release_id}"
    remote = remote_assets(api, endpoint)
    verify_targets(expected, remote)
    extras = set(remote) - set(expected)
    unknown = extras - set(original_names)
    if unknown:
        raise ValueError(f"Unknown draft assets; refusing to delete: {sorted(unknown)}")
    for name in sorted(extras):
        api(["--method", "DELETE",
             f"repos/{plan['repository']}/releases/assets/{remote[name]['id']}"])
    remaining = remote_assets(api, endpoint)
    verify_targets(expected, remaining)
    if set(remaining) != set(expected):
        raise ValueError("Draft does not contain exactly the planned assets after cleanup")
    return release_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    if plan["tag"] != args.tag:
        raise ValueError("Requested tag does not match the release plan")
    verify_original(args.artifacts)
    original_names = {path.name for path in args.artifacts.iterdir()}
    settings = {**plan, "repository": os.environ["GH_REPO"]}
    release_id = finalize_draft(settings, original_names, github)
    print(f"Verified draft {release_id}: {EXPECTED_ASSET_COUNT} uploaded assets")


if __name__ == "__main__":
    main()
