"""Run actual Lua 5.1 backend contracts; Linux requires the CI Lua dependency."""
import os
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
LUA_TIMEOUT_SECONDS = 30


class FanControlTests(unittest.TestCase):
    def run_lua(self, script):
        lua = shutil.which("lua5.1") or shutil.which("lua")
        if not lua and os.name == "nt":
            self.skipTest("Lua is unavailable on Windows; Linux CI requires Lua 5.1")
        self.assertIsNotNone(lua, "Install lua5.1: Linux must execute fancontrol tests")
        result = subprocess.run(
            [lua, str(ROOT / "Tests" / script), str(ROOT)],
            cwd=ROOT, capture_output=True, text=True, timeout=LUA_TIMEOUT_SECONDS,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_real_lua_backend_contracts(self):
        self.assertIn("fancontrol scenarios passed", self.run_lua("test_fancontrol.lua"))

    def test_rpc_discovery_declares_objects_without_hardware_access(self):
        methods = json.loads(self.run_lua("fan_rpc.lua"))
        self.assertEqual(methods["status"], {})
        self.assertEqual(set(methods), {"status", "configure"})
        self.assertEqual(set(methods["configure"]), {"custom", "t0", "t1", "t2", "t3"})
        self.assertIs(type(methods["configure"]["custom"]), bool)
        for key in ("t0", "t1", "t2", "t3"):
            self.assertIs(type(methods["configure"][key]), int)


if __name__ == "__main__":
    unittest.main()
