"""Exercise config drift and firmware verification with isolated file fixtures."""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Scripts"))
from collect_artifacts import IMAGE_SUFFIXES, REQUIRED_PACKAGES, WIRELESS_PACKAGES, verify_images
from configure import DEVICE_SYMBOL, parse_config, verify


class ConfigTests(unittest.TestCase):
    def test_configs_request_only_the_expected_device(self):
        for mode in ("YES", "NO"):
            with self.subTest(mode=mode):
                config = parse_config((ROOT / f"Config/SBE1V1K-WIFI-{mode}.txt").read_text())
                verify(config, config)
                self.assertEqual(config[DEVICE_SYMBOL], "y")
                for package in WIRELESS_PACKAGES:
                    self.assertEqual(config[f"CONFIG_PACKAGE_{package}"], "y" if mode == "YES" else "n")

    def test_rejects_dropped_package(self):
        with self.assertRaisesRegex(ValueError, "requested y"):
            verify({"CONFIG_PACKAGE_luci": "y"}, {DEVICE_SYMBOL: "y"})

    def test_rejects_wireless_reenabled_by_dependency(self):
        with self.assertRaisesRegex(ValueError, "requested n"):
            verify({"CONFIG_PACKAGE_kmod-ath12k": "n"},
                   {DEVICE_SYMBOL: "y", "CONFIG_PACKAGE_kmod-ath12k": "y"})

    def test_rejects_second_device(self):
        with self.assertRaisesRegex(ValueError, "Expected exactly"):
            verify({}, {DEVICE_SYMBOL: "y", "CONFIG_TARGET_qualcommbe_ipq95xx_DEVICE_qcom_rdp433": "y"})

    def test_overlay_uses_requested_lan_address(self):
        overlay = (ROOT / "files/etc/uci-defaults/99-sbe1v1k-ci").read_text()
        self.assertIn("network.lan.ipaddr='192.168.70.1'", overlay)


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.target = Path(self.temporary.name)
        self.images = []
        for suffix in IMAGE_SUFFIXES:
            name = f"immortalwrt-qualcommbe-ipq95xx-askey_sbe1v1k{suffix}"
            content = suffix.encode()
            (self.target / name).write_bytes(content)
            self.images.append({"name": name, "sha256": hashlib.sha256(content).hexdigest()})
        self.write_profile()

    def write_profile(self):
        payload = {"profiles": {"askey_sbe1v1k": {"images": self.images}}}
        (self.target / "profiles.json").write_text(json.dumps(payload))

    def manifest(self, packages):
        (self.target / "firmware.manifest").write_text("\n".join(f"{name} - 1" for name in packages))

    def test_accepts_wifi_images_with_matching_hashes(self):
        self.manifest(REQUIRED_PACKAGES | WIRELESS_PACKAGES)
        verify_images(self.target, "yes")

    def test_accepts_wired_images_without_wireless_packages(self):
        self.manifest(REQUIRED_PACKAGES)
        verify_images(self.target, "no")

    def test_rejects_missing_recovery_image(self):
        self.images.pop(0)
        self.write_profile()
        with self.assertRaisesRegex(ValueError, "Expected one"):
            verify_images(self.target, "yes")

    def test_rejects_corrupt_firmware(self):
        (self.target / self.images[0]["name"]).write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            verify_images(self.target, "yes")

    def test_rejects_wireless_in_wired_manifest(self):
        self.manifest(REQUIRED_PACKAGES | WIRELESS_PACKAGES)
        with self.assertRaisesRegex(ValueError, "Wireless packages remain"):
            verify_images(self.target, "no")

    def test_rejects_missing_phy_firmware(self):
        self.manifest((REQUIRED_PACKAGES | WIRELESS_PACKAGES) - {"rtl826x-firmware"})
        with self.assertRaisesRegex(ValueError, "Missing device packages"):
            verify_images(self.target, "yes")


if __name__ == "__main__":
    unittest.main()
