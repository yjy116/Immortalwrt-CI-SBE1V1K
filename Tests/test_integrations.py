"""Check ownership changes against changed upstream installation recipes."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Scripts"))
from integrate_packages import tailscale_recipe

RUNTIME = (
    "\t$(INSTALL_BIN) ./files//tailscale.init $(1)/etc/init.d/tailscale\n"
    "\t$(INSTALL_DATA) ./files//tailscale.conf $(1)/etc/config/tailscale\n"
)
BINARY = "\t$(INSTALL_BIN) $(GO_PKG_BUILD_BIN_DIR)/tailscaled $(1)/usr/sbin\n"


class TailscaleOwnershipTests(unittest.TestCase):
    def test_keeps_core_binary_and_ui_owns_runtime_files(self):
        result = tailscale_recipe(BINARY + RUNTIME)
        self.assertIn(BINARY, result)
        self.assertNotIn("./files/", result)

    def test_rejects_unknown_new_runtime_file(self):
        with self.assertRaisesRegex(ValueError, "Additional Tailscale"):
            tailscale_recipe(RUNTIME + "\t$(INSTALL_BIN) ./files/new-hook $(1)/etc/hook\n")

    def test_rejects_changed_init_installation(self):
        with self.assertRaisesRegex(ValueError, "recipe changed"):
            tailscale_recipe(RUNTIME.replace("tailscale.init", "tailscale.start"))


if __name__ == "__main__":
    unittest.main()
