"""Anchor a build's CI revision before a long build can outlive its branch ref."""
import argparse
import json
import os
import re
import subprocess


def github(arguments):
    result = subprocess.run(
        ["gh", "api", *arguments], check=True, text=True, stdout=subprocess.PIPE,
    )
    return json.loads(result.stdout)


def validate_settings(settings):
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", settings.repository):
        raise ValueError("Invalid GitHub repository")
    if not re.fullmatch(r"sbe1v1k-wifi-(yes|no)-[0-9]+-[0-9]+", settings.tag):
        raise ValueError("Invalid build tag")
    if not re.fullmatch(r"[0-9a-f]{40}", settings.commit):
        raise ValueError("Expected a full CI commit SHA")


def check_tag(settings, api):
    validate_settings(settings)
    repository, tag, commit = settings.repository, settings.tag, settings.commit
    reference = f"refs/tags/{tag}"
    endpoint = f"repos/{repository}/git"
    matches = api([f"{endpoint}/matching-refs/tags/{tag}"])
    exact = [entry for entry in matches if entry["ref"] == reference]
    if not exact:
        if not settings.create:
            raise RuntimeError(f"Missing build tag: {tag}")
        exact = [api([
            "--method", "POST", f"{endpoint}/refs",
            "-f", f"ref={reference}", "-f", f"sha={commit}",
        ])]
    if len(exact) != 1 or exact[0]["ref"] != reference:
        raise RuntimeError(f"Ambiguous build tag: {tag}")
    target = exact[0]["object"]
    if target["type"] != "commit" or target["sha"] != commit:
        raise RuntimeError(f"Build tag does not point to the expected CI commit: {tag}")
    print(f"Verified {reference} at {commit}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--create", action="store_true")
    settings = parser.parse_args()
    settings.repository = os.environ["GH_REPO"]
    settings.commit = os.environ["CI_COMMIT"]
    check_tag(settings, github)


if __name__ == "__main__":
    main()
