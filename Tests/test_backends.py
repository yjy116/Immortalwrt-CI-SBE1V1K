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


if __name__ == "__main__":
    unittest.main()
