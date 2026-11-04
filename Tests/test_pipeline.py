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
from defaults import LAN_IP, apply_defaults
from install_feeds import selected_packages


class ConfigTests(unittest.TestCase):
    def test_feed_selection_excludes_custom_and_disabled_packages(self):
        manifest = {"sources": [{"packages": [{"name": "luci-theme-vantage"}]}]}
        config = "CONFIG_PACKAGE_luci=y\nCONFIG_PACKAGE_luci-theme-vantage=y\nCONFIG_PACKAGE_unused=n\n"
        self.assertEqual(selected_packages(config, manifest), {"luci"})

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

class DefaultsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name)
        self.generator = self.source / "package/base-files/files/bin/config_generate"
        self.luci = self.source / "feeds/luci/modules/luci-base/root/etc/config/luci"
        self.wireless = self.source / "package/network/config/wifi-scripts/files/lib/wifi/mac80211.uc"
        self.generator.parent.mkdir(parents=True)
        self.luci.parent.mkdir(parents=True)
        self.generator.write_text('lan) ipad=${ipaddr:-"192.168.1.1"} ;;\nhostname=\'OWRT\'\n')
        self.luci.write_text("option mediaurlbase '/luci-static/bootstrap'\n")
        self.wireless.parent.mkdir(parents=True)
        self.wireless.write_text("\n".join([
            "set ${s}.country='${country || 'CN'}'",
            "set ${si}.ssid='${defaults?.ssid || 'OWRT'}'",
            "set ${si}.encryption='${defaults?.encryption || 'psk2+ccmp'}'",
            "set ${si}.key='${defaults?.key || '12345678'}'",
            "set ${si}.disabled='0'",
        ]))

    def test_changes_only_generation_defaults(self):
        self.assertEqual(LAN_IP, "192.168.70.1")
        apply_defaults(self.source)
        self.assertIn('ipad=${ipaddr:-"192.168.70.1"}', self.generator.read_text())
        self.assertIn("hostname='SBE1V1K'", self.generator.read_text())
        self.assertIn("/luci-static/vantage", self.luci.read_text())
        self.assertFalse((self.source / "files/etc/uci-defaults").exists())

    def test_wifi_starts_disabled_without_shared_country_or_password(self):
        apply_defaults(self.source)
        wireless = self.wireless.read_text()
        self.assertIn("set ${si}.disabled='1'", wireless)
        self.assertIn("${defaults?.encryption || encryption}", wireless)
        self.assertNotIn("12345678", wireless)
        self.assertNotIn("'CN'", wireless)

    def test_wireless_drift_preserves_all_original_files(self):
        generator, luci = self.generator.read_text(), self.luci.read_text()
        self.wireless.write_text("changed upstream\n")
        with self.assertRaisesRegex(ValueError, "Expected one upstream"):
            apply_defaults(self.source)
        self.assertEqual(self.generator.read_text(), generator)
        self.assertEqual(self.luci.read_text(), luci)

    def test_upstream_drift_fails_before_any_file_change(self):
        original = self.generator.read_text()
        self.luci.write_text("changed upstream\n")
        with self.assertRaisesRegex(ValueError, "Expected one upstream"):
            apply_defaults(self.source)
        self.assertEqual(self.generator.read_text(), original)


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

    def test_rejects_usb_peripherals_in_both_variants(self):
        for wifi in ("yes", "no"):
            for package in ("kmod-usb3", "kmod-usb-net-rndis", "p910nd"):
                with self.subTest(wifi=wifi, package=package):
                    self.manifest(REQUIRED_PACKAGES | WIRELESS_PACKAGES | {package}
                                  if wifi == "yes" else REQUIRED_PACKAGES | {package})
                    with self.assertRaisesRegex(ValueError, "USB peripheral packages remain"):
                        verify_images(self.target, wifi)

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

    def test_rejects_vanilla_wireless_in_wired_manifest(self):
        self.manifest(REQUIRED_PACKAGES | {"ath12k-firmware-qcn9274"})
        with self.assertRaisesRegex(ValueError, "Wireless packages remain"):
            verify_images(self.target, "no")

    def test_rejects_missing_phy_firmware(self):
        self.manifest((REQUIRED_PACKAGES | WIRELESS_PACKAGES) - {"rtl826x-firmware"})
        with self.assertRaisesRegex(ValueError, "Missing device packages"):
            verify_images(self.target, "yes")

    def test_rejects_vanilla_firmware_instead_of_owrt_firmware(self):
        packages = REQUIRED_PACKAGES | WIRELESS_PACKAGES
        packages = (packages - {"ath12k-firmware-qcn9274-ddwrt"}) | {"ath12k-firmware-qcn9274"}
        self.manifest(packages)
        with self.assertRaisesRegex(ValueError, "ath12k-firmware-qcn9274-ddwrt"):
            verify_images(self.target, "yes")


if __name__ == "__main__":
    unittest.main()
