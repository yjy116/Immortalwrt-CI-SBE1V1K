"""Check local-package provenance and the firmware installation gate."""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Scripts"))
from integrate_local import LOCAL_PACKAGES, integrate, verify_local_packages


class LocalPackageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.packages = self.root / "packages"
        for name in LOCAL_PACKAGES:
            package = self.packages / name
            package.mkdir(parents=True)
            (package / "Makefile").write_bytes(b"recipe\n")

    def test_installs_exact_local_sources_and_records_digests(self):
        integrate(self.source, self.packages)
        record = self.source / "ci-build/local-packages.json"
        metadata = json.loads(record.read_text())
        for name in LOCAL_PACKAGES:
            self.assertEqual((self.source / "package/custom-ci/local" / name / "Makefile").read_bytes(), b"recipe\n")
            self.assertEqual(metadata["packages"][name]["Makefile"], hashlib.sha256(b"recipe\n").hexdigest())

    def test_never_overwrites_an_existing_local_package(self):
        integrate(self.source, self.packages)
        with self.assertRaisesRegex(ValueError, "already exists"):
            integrate(self.source, self.packages)

    def test_manifest_must_include_local_plugin(self):
        integrate(self.source, self.packages)
        manifest = self.source / "firmware.manifest"
        manifest.write_text("kmod-hwmon-pwmfan - 1\n")
        record = self.source / "ci-build/local-packages.json"
        with self.assertRaisesRegex(ValueError, "Missing local device packages"):
            verify_local_packages(self.source, record)
        manifest.write_text("\n".join(f"{name} - 1" for name in LOCAL_PACKAGES))
        verify_local_packages(self.source, record)


if __name__ == "__main__":
    unittest.main()
