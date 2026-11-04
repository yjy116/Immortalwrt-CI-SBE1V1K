"""Cache identity and stamp boundaries using real local Git history."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Scripts"))
from build_cache import cache_identity, refresh_stamps

COMMAND_TIMEOUT_SECONDS = 10
OLD_MTIME_NS = 1_600_000_000_000_000_000
CORE_DIRECTORIES = (
    "config", "include", "scripts", "tools", "toolchain",
    "target/linux/generic", "target/linux/qualcommbe",
)
REQUIRED_PATHS = (".config", "ci-source.json", "Makefile", "rules.mk", *CORE_DIRECTORIES)
BASE_CONFIG = (
    "CONFIG_TARGET_qualcommbe=y\n"
    "CONFIG_PACKAGE_luci=y\n"
    "CONFIG_TARGET_BOARD=\"qualcommbe\"\n"
    "# CONFIG_PACKAGE_unused is not set\n"
)


def git(source, *arguments):
    return subprocess.run(
        ["git", "-C", str(source), *arguments], check=True, capture_output=True,
        text=True, timeout=COMMAND_TIMEOUT_SECONDS,
    ).stdout.strip()


def write(source, name, content):
    path = source / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class BuildCacheIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name)
        git(self.source, "init", "-q", "--initial-branch=owrt")
        git(self.source, "config", "user.name", "Cache Fixture")
        git(self.source, "config", "user.email", "cache@example.invalid")
        write(self.source, ".gitignore", ".config\nci-*.json\nstaging_dir/\ntmp/\n")
        for name in ("Makefile", "rules.mk"):
            write(self.source, name, "# core build rules\n")
        for name in CORE_DIRECTORIES:
            write(self.source, f"{name}/fixture.txt", f"{name} initial\n")
        write(self.source, "package/demo/Makefile", "PKG_VERSION:=1\n")
        self.initial_commit = self.commit("initial core")
        self.metadata = {"repository": "https://example.invalid/source.git", "branch": "owrt"}
        self.save_metadata(self.metadata)
        write(self.source, ".config", BASE_CONFIG)
        self.host = {"os": "ubuntu", "compiler": {"gcc": "14"}, "features": ["x64", True, None]}

    def commit(self, message):
        git(self.source, "add", ".")
        git(self.source, "commit", "-qm", message)
        return git(self.source, "rev-parse", "HEAD")

    def save_metadata(self, metadata):
        write(self.source, "ci-source.json", json.dumps(metadata))

    def key(self):
        return cache_identity(self.source, self.host)["key"]

    def test_key_has_versioned_sha256_identity(self):
        self.assertRegex(self.key(), r"^sbe1v1k-build-v1-[0-9a-f]{64}$")
        self.assertEqual(self.key(), self.key())

    def test_package_only_commit_does_not_invalidate_core_cache(self):
        before = self.key()
        write(self.source, "package/demo/Makefile", "PKG_VERSION:=2\n")
        latest = self.commit("package-only update")
        self.assertNotEqual(latest, self.initial_commit)
        self.save_metadata({**self.metadata, "commit": latest, "requested_ref": latest})
        self.assertEqual(self.key(), before)

    def test_each_core_tree_change_invalidates_cache(self):
        before = self.key()
        for name in CORE_DIRECTORIES:
            with self.subTest(path=name):
                write(self.source, f"{name}/fixture.txt", f"{name} changed\n")
                self.commit(f"change {name}")
                after = self.key()
                self.assertNotEqual(after, before)
                before = after

    def test_top_level_build_rules_invalidate_cache(self):
        before = self.key()
        for name in ("Makefile", "rules.mk"):
            with self.subTest(path=name):
                write(self.source, name, "# changed core build rule\n")
                self.commit(f"change {name}")
                after = self.key()
                self.assertNotEqual(after, before)
                before = after

    def test_uncommitted_and_untracked_tool_sources_invalidate_cache(self):
        before = self.key()
        write(self.source, "tools/fixture.txt", "local tool patch\n")
        self.assertNotEqual(self.key(), before)
        write(self.source, "tools/fixture.txt", "tools initial\n")
        self.assertEqual(self.key(), before)
        write(self.source, "tools/new-source.txt", "first local source\n")
        first_untracked = self.key()
        self.assertNotEqual(first_untracked, before)
        write(self.source, "tools/new-source.txt", "changed local source\n")
        self.assertNotEqual(self.key(), first_untracked)
        self.assertEqual(git(self.source, "rev-parse", "HEAD"), self.initial_commit)

    def test_config_comments_and_order_do_not_invalidate_cache(self):
        before = self.key()
        reordered = "# Generated on another date\n\n" + "\n".join(reversed(BASE_CONFIG.splitlines()))
        write(self.source, ".config", reordered + "\n# unrelated comment\n")
        self.assertEqual(self.key(), before)

    def test_effective_config_changes_invalidate_cache(self):
        before = self.key()
        variants = (
            BASE_CONFIG.replace("CONFIG_PACKAGE_luci=y", "CONFIG_PACKAGE_luci=m"),
            BASE_CONFIG.replace("# CONFIG_PACKAGE_unused is not set", "CONFIG_PACKAGE_unused=y"),
            BASE_CONFIG.replace('CONFIG_TARGET_BOARD="qualcommbe"', 'CONFIG_TARGET_BOARD="other"'),
        )
        for config in variants:
            with self.subTest(config=config):
                write(self.source, ".config", config)
                self.assertNotEqual(self.key(), before)

    def test_host_signature_changes_invalidate_cache(self):
        before = self.key()
        changed_host = {**self.host, "compiler": {"gcc": "15"}}
        self.assertNotEqual(cache_identity(self.source, changed_host)["key"], before)

    def test_build_directory_change_invalidates_cache(self):
        before = self.key()
        with tempfile.TemporaryDirectory() as directory:
            relocated = Path(directory) / "source"
            shutil.copytree(self.source, relocated)
            self.assertNotEqual(cache_identity(relocated, self.host)["key"], before)

    def test_repository_and_branch_changes_invalidate_cache(self):
        before = self.key()
        for field, value in (("repository", "https://example.invalid/fork.git"), ("branch", "main")):
            with self.subTest(field=field):
                self.save_metadata({**self.metadata, field: value})
                self.assertNotEqual(self.key(), before)

    def test_per_run_commit_and_feed_records_do_not_invalidate_cache(self):
        before = self.key()
        self.save_metadata({**self.metadata, "commit": "a" * 40, "requested_ref": "owrt"})
        write(self.source, "ci-feeds.json", json.dumps({"packages": "a" * 40}))
        write(self.source, "ci-packages.json", json.dumps({"sources": [{"commit": "b" * 40}]}))
        self.assertEqual(self.key(), before)
        self.save_metadata({**self.metadata, "commit": "c" * 40, "requested_ref": "c" * 40})
        write(self.source, "ci-feeds.json", json.dumps({"packages": "d" * 40}))
        write(self.source, "ci-packages.json", json.dumps({"sources": [{"commit": "e" * 40}]}))
        self.assertEqual(self.key(), before)

    def test_missing_required_input_reports_failure(self):
        for name in REQUIRED_PATHS:
            with self.subTest(path=name):
                path = self.source / name
                saved = path.with_name(path.name + ".saved")
                path.rename(saved)
                try:
                    with self.assertRaises((ValueError, FileNotFoundError, RuntimeError)) as caught:
                        self.key()
                    self.assertIn(path.name, str(caught.exception))
                finally:
                    saved.rename(path)


class BuildCacheStampTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name)

    def fixture(self, name):
        path = write(self.source, name, f"unchanged {name}\n")
        os.utime(path, ns=(OLD_MTIME_NS, OLD_MTIME_NS))
        return path

    def test_refresh_touches_only_existing_host_and_toolchain_stamp_files(self):
        stamps = [self.fixture(name) for name in (
            "staging_dir/host/stamp/.pkg_compile",
            "staging_dir/toolchain-aarch64/stamp/.gcc_final_installed",
            "staging_dir/toolchain-aarch64/stamp/nested/.libc_installed",
            "staging_dir/toolchain-other/stamp/.binutils_installed",
        )]
        protected = [self.fixture(name) for name in (
            "staging_dir/host/bin/compiler", "staging_dir/hostpkg/stamp/.pkg_compile",
            "staging_dir/target-aarch64/stamp/.package_compile",
            "build_dir/host/tool/.built", ".config", "tmp/.packageinfo",
            "tmp/.targetinfo", "tmp/.config-feeds.in",
        )]
        original = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in stamps + protected}
        before_files = {path.relative_to(self.source) for path in self.source.rglob("*") if path.is_file()}
        refresh_stamps(self.source)
        after_files = {path.relative_to(self.source) for path in self.source.rglob("*") if path.is_file()}
        self.assertEqual(after_files - before_files, {Path("tmp/.build")})
        self.assertEqual(before_files - after_files, set())
        for path in stamps:
            self.assertGreater(path.stat().st_mtime_ns, OLD_MTIME_NS, str(path))
            self.assertEqual(path.read_bytes(), original[path][0])
        for path in protected:
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), original[path], str(path))
        refreshed_times = {path.stat().st_mtime_ns for path in stamps}
        self.assertEqual(len(refreshed_times), 1)
        self.assertGreaterEqual((self.source / "tmp/.build").stat().st_mtime_ns, next(iter(refreshed_times)))

    def test_empty_stamp_cache_fails_without_inventing_success_marker(self):
        (self.source / "staging_dir/host/stamp").mkdir(parents=True)
        (self.source / "staging_dir/toolchain-aarch64/stamp").mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "no installed.*stamps"):
            refresh_stamps(self.source)
        files = {path.relative_to(self.source) for path in self.source.rglob("*") if path.is_file()}
        self.assertEqual(files, set())


if __name__ == "__main__":
    unittest.main()
