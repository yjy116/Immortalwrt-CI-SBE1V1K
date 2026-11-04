"""Verify moving branches and per-run snapshots with actual local Git repos."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Scripts/checkout_source.py"
COMMAND_TIMEOUT_SECONDS = 20


def git(repository, *arguments):
    return subprocess.run(
        ["git", "-C", str(repository), *arguments], check=True,
        text=True, capture_output=True, timeout=COMMAND_TIMEOUT_SECONDS,
    ).stdout.strip()


class SourceCheckoutTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repository = self.root / "upstream"
        self.repository.mkdir()
        git(self.repository, "init", "--initial-branch=owrt", "--quiet")
        git(self.repository, "config", "user.name", "Source Fixture")
        git(self.repository, "config", "user.email", "fixture@example.invalid")
        self.first = self.commit_version("first")
        self.config = self.root / "source.json"
        self.settings = {"repository": self.repository.as_uri(), "branch": "owrt"}
        self.save_config()

    def save_config(self):
        self.config.write_text(json.dumps(self.settings), encoding="utf-8")

    def commit_version(self, version):
        (self.repository / "version.txt").write_text(version, encoding="utf-8")
        git(self.repository, "add", "version.txt")
        git(self.repository, "commit", "--quiet", "-m", version)
        return git(self.repository, "rev-parse", "HEAD")

    def cli(self, *arguments):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--source-config", str(self.config), *arguments],
            text=True, capture_output=True, timeout=COMMAND_TIMEOUT_SECONDS,
        )

    def checkout(self, name, snapshot=None):
        destination = self.root / name
        arguments = ["--destination", str(destination)]
        if snapshot:
            arguments.extend(["--snapshot", snapshot])
        result = self.cli(*arguments)
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads((destination / "ci-source.json").read_text())
        return destination, evidence

    def test_new_run_follows_branch_after_upstream_advances(self):
        _, first_evidence = self.checkout("first-run")
        second = self.commit_version("second")
        destination, second_evidence = self.checkout("second-run")
        self.assertEqual(first_evidence["commit"], self.first)
        self.assertEqual(second_evidence["commit"], second)
        self.assertEqual((destination / "version.txt").read_text(), "second")
        self.assertEqual(second_evidence["branch"], "owrt")
        self.assertEqual(second_evidence["requested_ref"], "refs/heads/owrt")

    def test_two_checkouts_share_snapshot_when_branch_advances_between_them(self):
        resolved = self.cli("--resolve-only")
        self.assertEqual(resolved.returncode, 0, resolved.stderr)
        snapshot = resolved.stdout.strip()
        self.assertEqual(snapshot, self.first)
        first_destination, first_evidence = self.checkout("wifi", snapshot)
        self.commit_version("second")
        second_destination, second_evidence = self.checkout("wired", snapshot)
        self.assertEqual(first_evidence["commit"], self.first)
        self.assertEqual(second_evidence["commit"], self.first)
        self.assertEqual(second_evidence["requested_ref"], snapshot)
        self.assertEqual(git(first_destination, "rev-parse", "HEAD"), snapshot)
        self.assertEqual(git(second_destination, "rev-parse", "HEAD"), snapshot)
        next_run = self.cli("--resolve-only")
        self.assertEqual(next_run.returncode, 0, next_run.stderr)
        self.assertNotEqual(next_run.stdout.strip(), snapshot)

    def test_branch_name_does_not_resolve_to_same_named_tag(self):
        git(self.repository, "tag", "owrt", self.first)
        latest = self.commit_version("second")
        _, evidence = self.checkout("branch-not-tag")
        self.assertEqual(evidence["commit"], latest)

    def test_missing_branch_fails_before_creating_destination(self):
        self.settings["branch"] = "missing"
        self.save_config()
        destination = self.root / "missing-branch"
        result = self.cli("--destination", str(destination))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ls-remote", result.stderr)
        self.assertFalse(destination.exists())

    def test_snapshot_does_not_accept_arbitrary_branch_override(self):
        destination = self.root / "invalid-snapshot"
        result = self.cli("--destination", str(destination), "--snapshot", "other-branch")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("full commit SHA", result.stderr)
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
