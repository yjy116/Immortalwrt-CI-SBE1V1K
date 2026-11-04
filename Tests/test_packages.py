"""Exercise the package installer through its CLI using real local Git commits."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Scripts" / "prepare_packages.py"
RESOLVER = ROOT / "Scripts" / "resolve_packages.py"
TIMEOUT_SECONDS = 30
WINDOWS_PRIVILEGE_NOT_HELD = 1314


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True,
        text=True, timeout=TIMEOUT_SECONDS,
    ).stdout.strip()


class PackageInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "openwrt"
        self.source.mkdir()
        for name in ["Makefile", "include/package.mk", "feeds/luci/luci.mk"]:
            self.write(self.source / name, "# fixture\n")
        (self.source / "package/feeds/luci").mkdir(parents=True)
        self.repo = self.root / "upstream"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "--initial-branch=main")
        git(self.repo, "config", "user.name", "Package Fixture")
        git(self.repo, "config", "user.email", "fixture@example.invalid")
        self.write(self.repo / "luci-app-demo/Makefile", "# pinned package\n")
        self.write(self.repo / "luci-app-demo/version", "first\n")
        self.write(self.repo / "version.mk", "VERSION:=first\n")
        self.commit = self.commit_repository("initial package")
        self.manifest = self.root / "manifest.json"
        self.output = self.root / "metadata.json"
        self.snapshots = None
        self.definition = {
            "schema": 2,
            "sources": [{
                "name": "demo", "url": self.repo.as_uri(),
                "branch": "main",
                "packages": [{"name": "luci-app-demo", "path": "luci-app-demo"}],
                "files": ["version.mk"],
            }],
        }

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit_repository(self, message):
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", message)
        return git(self.repo, "rev-parse", "HEAD")

    def run_installer(self):
        self.manifest.write_text(json.dumps(self.definition), encoding="utf-8")
        arguments = ["--source", str(self.source), "--manifest", str(self.manifest),
                     "--output", str(self.output)]
        if self.snapshots is not None:
            snapshots = self.root / "snapshots.json"
            snapshots.write_text(json.dumps(self.snapshots), encoding="utf-8")
            arguments.extend(["--snapshots", str(snapshots)])
        return subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
        )

    def provider(self, name="luci-app-demo"):
        provider = self.source / "feeds/luci/applications" / name
        self.write(provider / "Makefile", "# old provider\n")
        return provider

    def assert_failed_without_installation(self, result):
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("can't open file", result.stderr)
        self.assertFalse(self.output.exists())
        self.assertFalse((self.source / "package/custom-ci/demo").exists())

    def test_fetches_exact_commit_not_new_head_and_records_provenance(self):
        self.snapshots = {"demo": self.commit}
        self.write(self.repo / "luci-app-demo/version", "second\n")
        self.commit_repository("later revision")
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        installed = self.source / "package/custom-ci/demo"
        self.assertEqual((installed / "luci-app-demo/version").read_text(), "first\n")
        self.assertEqual((installed / "version.mk").read_text(), "VERSION:=first\n")
        self.assertFalse((installed / ".git").exists())
        provenance = json.loads(self.output.read_text())
        self.assertEqual(provenance["sources"][0]["commit"], self.commit)
        self.assertEqual(provenance["sources"][0]["url"], self.repo.as_uri())

    def test_removes_exact_feed_provider_and_preserves_similar_names(self):
        original = self.provider()
        similar = self.provider("luci-app-demo-extra")
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(original.exists())
        self.assertTrue((similar / "Makefile").is_file())

    def test_removes_feed_symlink_without_deleting_external_target(self):
        external = self.root / "external"
        external.mkdir()
        link = self.source / "package/feeds/luci/luci-app-demo"
        try:
            link.symlink_to(external, target_is_directory=True)
        except OSError as error:
            if getattr(error, "winerror", None) != WINDOWS_PRIVILEGE_NOT_HELD:
                raise
            self.skipTest(f"Directory symlinks unavailable: {error}")
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(link.is_symlink())
        self.assertTrue(external.is_dir())

    def test_rejects_path_traversal_before_touching_feeds(self):
        original = self.provider()
        self.definition["sources"][0]["packages"][0]["path"] = "../outside"
        self.assert_failed_without_installation(self.run_installer())
        self.assertTrue(original.is_dir())

    def test_rejects_invalid_branch_ref(self):
        self.definition["sources"][0]["branch"] = "main/../escape"
        self.assert_failed_without_installation(self.run_installer())

    def test_rejects_duplicate_package_provider(self):
        duplicate = dict(self.definition["sources"][0], name="other")
        self.definition["sources"].append(duplicate)
        self.assert_failed_without_installation(self.run_installer())

    def test_fetch_failure_does_not_remove_existing_provider(self):
        original = self.provider()
        self.snapshots = {"demo": "0" * 40}
        self.assert_failed_without_installation(self.run_installer())
        self.assertTrue(original.is_dir())

    def test_missing_package_is_error_before_feed_removal(self):
        original = self.provider()
        self.definition["sources"][0]["packages"][0]["path"] = "missing"
        self.assert_failed_without_installation(self.run_installer())
        self.assertTrue(original.is_dir())

    def test_missing_shared_file_is_error_before_feed_removal(self):
        original = self.provider()
        self.definition["sources"][0]["files"] = ["absent.mk"]
        self.assert_failed_without_installation(self.run_installer())
        self.assertTrue(original.is_dir())

    def test_incomplete_feeds_are_rejected(self):
        (self.source / "feeds/luci/luci.mk").unlink()
        result = self.run_installer()
        self.assert_failed_without_installation(result)
        self.assertIn("Missing OpenWrt/feed marker", result.stderr)

    def test_metadata_can_be_created_inside_source_tree(self):
        self.output = self.source / "ci-packages.json"
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.output.read_text())["sources"][0]["commit"], self.commit)

    def test_refuses_unmanaged_existing_destination(self):
        destination = self.source / "package/custom-ci/demo"
        self.write(destination / "keep.txt", "user content")
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((destination / "keep.txt").read_text(), "user content")

    def test_rejects_output_overwriting_source_file(self):
        self.output = self.source / "Makefile"
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.output.read_text(), "# fixture\n")

    def test_default_resolution_follows_new_branch_head(self):
        self.write(self.repo / "luci-app-demo/version", "second\n")
        latest = self.commit_repository("advance branch")
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        provenance = json.loads(self.output.read_text())
        self.assertEqual(provenance["sources"][0]["branch"], "main")
        self.assertEqual(provenance["sources"][0]["commit"], latest)

    def test_resolver_emits_exact_source_name_to_commit_mapping(self):
        self.manifest.write_text(json.dumps(self.definition), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(RESOLVER), "--manifest", str(self.manifest)],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"demo": self.commit})

    def test_two_build_trees_share_snapshot_after_branch_advances(self):
        self.snapshots = {"demo": self.commit}
        for name in ["wifi", "wired"]:
            self.source = self.root / name
            for marker in ["Makefile", "include/package.mk", "feeds/luci/luci.mk"]:
                self.write(self.source / marker, "# fixture\n")
            (self.source / "package/feeds/luci").mkdir(parents=True)
            self.output = self.root / f"{name}.json"
            result = self.run_installer()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(self.output.read_text())["sources"][0]["commit"], self.commit)
            if name == "wifi":
                self.write(self.repo / "luci-app-demo/version", "branch advanced\n")
                self.commit_repository("update between matrix builds")

    def test_incomplete_snapshot_fails_before_feed_removal(self):
        original = self.provider()
        self.snapshots = {}
        self.assert_failed_without_installation(self.run_installer())
        self.assertTrue(original.is_dir())

    def test_repository_layout_keeps_shared_ci_and_excludes_git(self):
        self.write(self.repo / "ci/pins.env", "UPSTREAM=example\n")
        self.commit_repository("shared source provenance")
        self.definition["sources"][0]["layout"] = "repository"
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        destination = self.source / "package/custom-ci/demo"
        self.assertEqual((destination / "ci/pins.env").read_text(), "UPSTREAM=example\n")
        self.assertTrue((destination / "luci-app-demo/Makefile").is_file())
        self.assertFalse((destination / ".git").exists())

    def test_package_can_be_at_repository_root(self):
        self.write(self.repo / "Makefile", "# root package\n")
        self.commit_repository("root package layout")
        self.definition["sources"][0]["packages"][0]["path"] = "."
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        destination = self.source / "package/custom-ci/demo/luci-app-demo"
        self.assertEqual((destination / "Makefile").read_text(), "# root package\n")
        self.assertFalse((destination / ".git").exists())


if __name__ == "__main__":
    unittest.main()
