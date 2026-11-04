"""Check official dependency selection independently of source installation."""
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Scripts"))
from install_feeds import installation_packages


class FeedSelectionTests(unittest.TestCase):
    def test_selects_official_dependencies_without_custom_translations_or_core(self):
        manifest = {
            "sources": [{"packages": [{"name": "luci-app-demo"}]}],
            "feed_dependencies": ["golang", "curl"],
        }
        config = "\n".join([
            "CONFIG_PACKAGE_luci=y", "CONFIG_PACKAGE_luci-app-demo=y",
            "CONFIG_PACKAGE_luci-i18n-demo-zh-cn=y", "CONFIG_PACKAGE_firewall4=y",
            "CONFIG_PACKAGE_unused=n",
        ])
        available = {"luci", "luci-app-demo", "luci-i18n-demo-zh-cn", "golang", "curl", "unused"}
        self.assertEqual(installation_packages(config, manifest, available), ["curl", "golang", "luci"])

    def test_missing_external_dependency_fails_explicitly(self):
        manifest = {"sources": [], "feed_dependencies": ["missing-host-tool"]}
        with self.assertRaisesRegex(ValueError, "missing-host-tool"):
            installation_packages("CONFIG_PACKAGE_luci=y", manifest, {"luci"})


if __name__ == "__main__":
    unittest.main()
