"""Backend adapter contracts; full behavior checks run on fetched branch sources."""
import importlib.util
from pathlib import Path
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("integrate_backends", ROOT / "Scripts/integrate_backends.py")
BACKENDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BACKENDS)


class BackendContractTests(unittest.TestCase):
    def test_patches_have_context_for_branch_drift(self):
        for name in ("daede", "honk"):
            patches = list((ROOT / "Patches" / name).glob("*.patch"))
            self.assertTrue(patches, name)
            for path in patches:
                chunks = re.split(r"(?m)^@@ .*@@.*\n", path.read_text(encoding="utf-8"))[1:]
                self.assertTrue(chunks, path.name)
                for chunk in chunks:
                    context = [line for line in chunk.splitlines() if line.startswith(" ")]
                    self.assertGreaterEqual(len(context), 3, path.name)

    def test_missing_source_recipe_fails_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Makefile"
            path.write_text("PKG_VERSION:=1\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Incomplete source recipe"):
                BACKENDS.recipe(path)

    def test_existing_migration_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "luci-app-daede/root/etc/uci-defaults/89-daede-migrate"
            target.parent.mkdir(parents=True)
            target.write_text("upstream migration sentinel", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Upstream now provides"):
                BACKENDS.install_migration(root)
            self.assertEqual(target.read_text(), "upstream migration sentinel")


class HonkSourceRecipeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def write_recipes(self, core_changes=None, ui_changes=None):
        # Source identifiers from upstream d3ff4e0, with a small parsing fixture.
        core = {
            "PKG_VERSION": "2026.11.18.1", "PKG_RELEASE": "1",
            "PKG_SOURCE": "$(HONK_ASSET)", "PKG_SOURCE_URL": "$(HONK_SOURCE_URL)/",
            "PKG_HASH": "$(HONK_HASH)", "HONK_SOURCE_TAG": "source-verified-20261117",
            "CORE_COMMIT": "64848881b7304e250e7a25422f4f1d86a5975eca",
            "HONK_HASH_X86_64": "496157e2ec9d8af457fce9be1b00758b4fec7b1fcce8d1e916162982fd599981",
            "HONK_HASH_AARCH64": "c32e88cb138c31963b309c5ee150ec094868d91ab13020f1ee0f2bbd054e83d6",
            "HONK_HASH_ARMV7": "53d75ef91db267a112fb7cacf5c3521b43e69ed10f6acdabb4dbf4ab2125d5ba",
        }
        ui = {
            "PKG_VERSION": "2026.11.18.1", "PKG_RELEASE": "1",
            "PKG_SOURCE": "doona-0123456789ab.tar.gz", "PKG_SOURCE_URL": "$(HONK_SOURCE_URL)/",
            "PKG_HASH": "0123456789abcdef" * 4, "HONK_SOURCE_TAG": "source-verified-20261117",
        }
        files = {"honk/Makefile": core | (core_changes or {}),
                 "luci-app-honk/Makefile": ui | (ui_changes or {})}
        for name, fields in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("".join(f"{key}?={value}\n" for key, value in fields.items()), encoding="utf-8")
        config = self.root / "honk/files/honk.config"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text("option enabled '0'\noption initialized '0'\n", encoding="utf-8")
        pins = self.root / "ci/pins.env"
        pins.parent.mkdir(parents=True, exist_ok=True)
        pins.write_text("HONK_REF=main\n", encoding="utf-8")

    def test_verified_source_release_is_accepted_without_rewriting_recipe(self):
        self.write_recipes()
        before = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        result = BACKENDS.inspect_honk(self.root)
        self.assertEqual(result["honk"]["fields"]["HONK_SOURCE_TAG"], "source-verified-20261117")
        self.assertEqual(result["doona"]["fields"]["HONK_SOURCE_TAG"], "source-verified-20261117")
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_numeric_release_tag_remains_supported(self):
        self.write_recipes({"HONK_SOURCE_TAG": "source-12345678"}, {"HONK_SOURCE_TAG": "source-12345678"})
        result = BACKENDS.inspect_honk(self.root)
        self.assertEqual(result["honk"]["fields"]["HONK_SOURCE_TAG"], "source-12345678")

    def test_unversioned_or_malformed_source_tag_is_rejected(self):
        for tag in ("", "main", "latest", "source-verified", "source-verified-2026111", "source-123/other"):
            with self.subTest(tag=tag):
                self.write_recipes({"HONK_SOURCE_TAG": tag}, {"HONK_SOURCE_TAG": tag})
                with self.assertRaisesRegex(ValueError, "source release tag"):
                    BACKENDS.inspect_honk(self.root)

    def test_verified_release_still_requires_matching_doona_tag(self):
        self.write_recipes(ui_changes={"HONK_SOURCE_TAG": "source-12345678"})
        with self.assertRaisesRegex(ValueError, "source tags differ"):
            BACKENDS.inspect_honk(self.root)

    def test_verified_release_still_requires_commit_and_archive_hashes(self):
        cases = (
            ({"CORE_COMMIT": "main"}, {}, "Invalid Honk core commit"),
            ({"HONK_HASH_AARCH64": "skip"}, {}, "Invalid Honk AARCH64 SHA-256"),
            ({}, {"PKG_HASH": "skip"}, "Invalid Doona archive SHA-256"),
            ({}, {"PKG_SOURCE": "doona-latest.tar.gz"}, "not content-addressed"),
        )
        for core, ui, error in cases:
            with self.subTest(error=error):
                self.write_recipes(core, ui)
                with self.assertRaisesRegex(ValueError, error):
                    BACKENDS.inspect_honk(self.root)


if __name__ == "__main__":
    unittest.main()
