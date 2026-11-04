"""Verify renamed release downloads and byte-preserving provenance archives."""
from argparse import Namespace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Scripts"))
from collect_artifacts import DEVICE, IMAGE_SUFFIXES, REQUIRED_PACKAGES, WIRELESS_PACKAGES
from release_layout import prepare

REPOSITORY = "yjy116/Immortalwrt-CI-SBE1V1K"
CI_COMMIT = "a" * 40
ORIGINAL_PREFIX = "immortalwrt-qualcommbe-ipq95xx-askey_sbe1v1k"
RELEASE_PREFIX = "qualcommbe-ipq95xx-askey_sbe1v1k"
STAMP = "26.11.04-04.56.08"
RUN = {"id": 123, "path": ".github/workflows/SBE1V1K.yml", "head_sha": CI_COMMIT,
       "created_at": "2026-11-03T20:56:08Z"}


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def file_snapshot(directory):
    return {path.name: path.read_bytes() for path in directory.iterdir() if path.is_file()}


class ReleaseLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.run_metadata = self.root / "run.json"
        self.run_metadata.write_text(json.dumps(RUN), encoding="utf-8")
        self.artifacts = self.create_artifacts("yes")

    def create_artifacts(self, wifi):
        directory = self.root / f"artifacts-{wifi}"
        directory.mkdir()
        images = []
        for suffix in IMAGE_SUFFIXES:
            name = ORIGINAL_PREFIX + suffix
            content = b"\x00\xfffirmware:" + wifi.encode() + suffix.encode()
            (directory / name).write_bytes(content)
            images.append({"name": name, "sha256": sha256(content)})
        source = {"repository": "https://github.com/yjy116/immortalwrt.git", "branch": "owrt",
                  "commit": "b" * 40, "requested_ref": "refs/heads/owrt",
                  "target": "qualcommbe", "subtarget": "ipq95xx", "device": DEVICE}
        packages = REQUIRED_PACKAGES | (WIRELESS_PACKAGES if wifi == "yes" else set())
        manifest = "kernel - 6.18.1~fixture\nluci-app-homeproxy - 1\nluci-theme-vantage - 1\n"
        manifest += "".join(f"{name} - 1\n" for name in sorted(packages))
        records = {
            "ci-source.json": json.dumps(source).encode(),
            "profiles.json": json.dumps({"profiles": {DEVICE: {"images": images}}}).encode(),
            "config.txt": f"# original config\nCONFIG_TARGET_qualcommbe=y\n# wifi={wifi}\n".encode(),
            ORIGINAL_PREFIX + ".manifest": manifest.encode(),
            "ci-feeds.json": b'{"packages":"fixture"}\n',
            "ci-packages.json": b'{"sources":[]}\n',
            "version.buildinfo": b"r123-fixture\n",
            "opaque-record.dat": b"\x00\xfforiginal binary record\r\n",
            "sha256sums": "".join(f"{item['sha256']}  {item['name']}\n" for item in images).encode(),
        }
        for name, content in records.items():
            (directory / name).write_bytes(content)
        self.write_checksums(directory)
        return directory

    def write_checksums(self, directory):
        files = sorted(path for path in directory.iterdir() if path.name != "SHA256SUMS-CI")
        text = "".join(f"{sha256(path.read_bytes())}  {path.name}\n" for path in files)
        (directory / "SHA256SUMS-CI").write_text(text, encoding="utf-8")

    def arguments(self, wifi="yes"):
        return Namespace(artifacts=self.root / f"artifacts-{wifi}", output=self.root / f"release-{wifi}",
                         wifi=wifi, run_metadata=self.run_metadata, repository=REPOSITORY,
                         tag=f"sbe1v1k-wifi-{wifi}-123-1", ci_commit=CI_COMMIT)

    def test_utc_creation_time_becomes_beijing_time_across_midnight(self):
        plan = prepare(self.arguments())
        expected = datetime(2026, 11, 4, 4, 56, 8, tzinfo=timezone(timedelta(hours=8)))
        self.assertEqual(datetime.fromisoformat(plan["build_time"]), expected)
        self.assertEqual(datetime.fromisoformat(plan["build_time"]).utcoffset(), timedelta(hours=8))
        self.assertEqual(plan["title"], f"SBE1V1K-WIFI-YES-yjy116-owrt-{STAMP}")
        self.assertEqual((plan["tag"], plan["run_id"], plan["ci_commit"], plan["wifi"]),
                         ("sbe1v1k-wifi-yes-123-1", 123, CI_COMMIT, "yes"))

    def test_exact_download_layout_and_complete_checksum_table(self):
        args = self.arguments()
        plan = prepare(args)
        title = f"SBE1V1K-WIFI-YES-yjy116-owrt-{STAMP}"
        suffix = f"yjy116-owrt-wifi-yes-{STAMP}"
        expected = {
            f"{RELEASE_PREFIX}-initramfs-uImage-{suffix}.itb",
            f"{RELEASE_PREFIX}-squashfs-sysupgrade-{suffix}.bin",
            f"{RELEASE_PREFIX}-squashfs-factory-{suffix}.bin",
            f"Config-{title}.txt", f"{RELEASE_PREFIX}-{suffix}.manifest",
            f"build-records-{title}.tar.gz", f"SHA256SUMS-{title}",
        }
        assets = args.output / "assets"
        self.assertEqual({path.name for path in assets.iterdir()}, expected)
        self.assertEqual({item["name"] for item in plan["assets"]}, expected)
        self.assertEqual(len(plan["assets"]), 7)
        for item in plan["assets"]:
            content = (assets / item["name"]).read_bytes()
            self.assertEqual((item["sha256"], item["size"]), (sha256(content), len(content)))
        lines = (assets / plan["checksum_file"]).read_text().splitlines()
        checksums = {name: checksum for checksum, name in (line.split("  ", 1) for line in lines)}
        self.assertEqual(len(lines), 6)
        self.assertEqual(set(checksums), expected - {plan["checksum_file"]})
        for name, checksum in checksums.items():
            self.assertEqual(checksum, sha256((assets / name).read_bytes()))
        self.assertEqual({path.name for path in args.output.iterdir()},
                         {"assets", "release-notes.md", "release-plan.json"})
        self.assertEqual(json.loads((args.output / "release-plan.json").read_text()), plan)

    def test_firmware_config_and_manifest_are_only_renamed(self):
        originals = file_snapshot(self.artifacts)
        args = self.arguments()
        plan = prepare(args)
        self.assertEqual(len(plan["firmware"]), 3)
        for item in plan["assets"]:
            if item["original"] is not None:
                self.assertEqual((args.output / "assets" / item["name"]).read_bytes(),
                                 originals[item["original"]])
        for item in plan["firmware"]:
            self.assertIn(item, plan["assets"])
            self.assertEqual(item["sha256"], sha256(originals[item["original"]]))
        self.assertEqual(file_snapshot(self.artifacts), originals)

    def test_modes_have_disjoint_asset_names(self):
        self.create_artifacts("no")
        wireless = prepare(self.arguments("yes"))
        wired = prepare(self.arguments("no"))
        names = [{item["name"] for item in plan["assets"]} for plan in (wireless, wired)]
        self.assertFalse(names[0] & names[1])
        self.assertEqual(wired["wifi"], "no")
        self.assertEqual(wired["title"], f"SBE1V1K-WIFI-NO-yjy116-owrt-{STAMP}")

    def test_notes_link_directly_to_actual_download_assets(self):
        args = self.arguments()
        plan = prepare(args)
        notes = (args.output / "release-notes.md").read_text(encoding="utf-8")
        config = next(item for item in plan["assets"] if item["original"] == "config.txt")
        names = [item["name"] for item in plan["firmware"]] + [config["name"], plan["checksum_file"]]
        for name in names:
            expected = f"https://github.com/{REPOSITORY}/releases/download/{args.tag}/{quote(name, safe='')}"
            self.assertIn(expected, notes)
        self.assertIn(f"https://github.com/{REPOSITORY}/actions/runs/123", notes)

    def test_archive_preserves_every_original_record_and_rename_mapping(self):
        originals = file_snapshot(self.artifacts)
        args = self.arguments()
        plan = prepare(args)
        images = {item["original"] for item in plan["firmware"]}
        name = next(item["name"] for item in plan["assets"] if item["name"].endswith(".tar.gz"))
        with tarfile.open(args.output / "assets" / name, "r:gz") as archive:
            self.assertEqual(set(archive.getnames()), (set(originals) - images) | {"release-files.json"})
            for original in set(originals) - images:
                self.assertEqual(archive.extractfile(original).read(), originals[original])
            mapping = json.load(archive.extractfile("release-files.json"))
        expected = [item for item in plan["assets"] if item["original"] is not None]
        self.assertEqual(len(mapping["assets"]), 5)
        self.assertEqual({item["original"]: item for item in mapping["assets"]},
                         {item["original"]: item for item in expected})
        self.assertEqual(file_snapshot(self.artifacts), originals)

    def test_tampered_file_is_rejected_by_original_checksum(self):
        (self.artifacts / "config.txt").write_bytes(b"changed after build")
        with self.assertRaisesRegex(ValueError, "checksum"):
            prepare(self.arguments())
        self.assertFalse(self.arguments().output.exists())

    def test_original_checksum_must_cover_all_artifact_files(self):
        checksum_file = self.artifacts / "SHA256SUMS-CI"
        lines = checksum_file.read_text().splitlines()
        checksum_file.write_text("\n".join(lines[:-1]) + "\n")
        with self.assertRaisesRegex(ValueError, "complete artifact"):
            prepare(self.arguments())

    def test_unsafe_checksum_path_is_rejected_even_when_external_file_exists(self):
        outside = self.root / "outside.bin"
        outside.write_bytes(b"external file sentinel")
        checksum_file = self.artifacts / "SHA256SUMS-CI"
        with checksum_file.open("a", encoding="utf-8") as stream:
            stream.write(f"{sha256(outside.read_bytes())}  ../outside.bin\n")
        with self.assertRaisesRegex(ValueError, "checksum entry"):
            prepare(self.arguments())
        self.assertEqual(outside.read_bytes(), b"external file sentinel")

    def test_wrong_original_ci_revision_is_rejected(self):
        args = self.arguments()
        args.ci_commit = "c" * 40
        with self.assertRaisesRegex(ValueError, "CI revision"):
            prepare(args)
        self.assertFalse(args.output.exists())

    def test_profile_hash_is_rechecked_after_artifact_checksum_verifies(self):
        path = self.artifacts / "profiles.json"
        profile = json.loads(path.read_text())
        profile["profiles"][DEVICE]["images"][0]["sha256"] = "0" * 64
        path.write_text(json.dumps(profile), encoding="utf-8")
        self.write_checksums(self.artifacts)
        with self.assertRaisesRegex(ValueError, "Image hash mismatch"):
            prepare(self.arguments())

    def test_existing_output_is_rejected_without_changing_published_bytes(self):
        args = self.arguments()
        prepare(args)
        assets_before = file_snapshot(args.output / "assets")
        notes_before = (args.output / "release-notes.md").read_bytes()
        with self.assertRaises(FileExistsError):
            prepare(args)
        self.assertEqual(file_snapshot(args.output / "assets"), assets_before)
        self.assertEqual((args.output / "release-notes.md").read_bytes(), notes_before)


if __name__ == "__main__":
    unittest.main()
