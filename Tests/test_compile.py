"""Exercise the compile wrapper with GNU make and actual failing recipes."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Scripts/compile_firmware.sh"
TIMEOUT_SECONDS = 60
WARNING = "::warning::Parallel build failed; retrying with one job and verbose output."
MAKEFILE = """SHELL := sh
PHASE := $(if $(filter s,$(V)),retry,normal)
.PHONY: all
all:
\t@printf 'phase=%s V=%s flags=%s\\n' '$(PHASE)' '$(V)' '$(MAKEFLAGS)' >> attempts.txt
\t@printf 'stdout:%s\\n' '$(PHASE)'
\t@printf 'stderr:%s\\n' '$(PHASE)' >&2
\t@{outcome}
"""


class FirmwareCompileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.make = shutil.which("make")
        if cls.make is None and os.name == "nt":
            raise unittest.SkipTest("GNU make is unavailable on Windows; no simulated make is used")
        if cls.make is None:
            raise RuntimeError("GNU make is required to execute compile-wrapper tests on Linux CI")
        version = subprocess.run(
            [cls.make, "--version"], capture_output=True, text=True,
            check=True, timeout=TIMEOUT_SECONDS,
        ).stdout
        if "GNU Make" not in version:
            raise RuntimeError(f"Expected GNU make, got: {version.splitlines()[0]}")
        cls.bash = shutil.which("bash")
        if cls.bash is None:
            raise RuntimeError("bash is required to execute the real compile wrapper")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name)

    def compile(self, outcome):
        (self.source / "Makefile").write_text(MAKEFILE.format(outcome=outcome), encoding="utf-8")
        environment = {key: value for key, value in os.environ.items()
                       if key not in {"MAKEFLAGS", "GNUMAKEFLAGS", "MFLAGS", "V"}}
        environment["PATH"] = os.pathsep.join((
            str(Path(self.make).parent), str(Path(self.bash).parent), environment.get("PATH", ""),
        ))
        return subprocess.run(
            [self.bash, SCRIPT.as_posix()], cwd=self.source, env=environment,
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
        )

    def assert_attempts(self, phases):
        attempts = (self.source / "attempts.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(attempts), len(phases), attempts)
        for attempt, phase in zip(attempts, phases):
            self.assertTrue(attempt.startswith(f"phase={phase} "), attempt)
            self.assertRegex(attempt, r"(?:^|\s)-j\d+(?:\s|$)")
            if phase == "retry":
                self.assertIn(" V=s ", attempt)
                self.assertRegex(attempt, r"(?:^|\s)-j1(?:\s|$)")
            else:
                self.assertIn(" V= ", attempt)

    def assert_log(self, filename, phase):
        content = (self.source / filename).read_text(encoding="utf-8")
        self.assertIn(f"stdout:{phase}", content)
        self.assertIn(f"stderr:{phase}", content)
        other = "normal" if phase == "retry" else "retry"
        self.assertNotIn(f"stdout:{other}", content)
        return content

    def assert_retry_evidence(self, result):
        self.assert_attempts(("normal", "retry"))
        self.assertEqual(result.stdout.count(WARNING), 1, result.stdout + result.stderr)
        initial = self.assert_log("ci-compile.log", "normal")
        retry = self.assert_log("ci-compile-retry.log", "retry")
        self.assertIn("recipe-failure:normal", initial)
        return retry

    def test_first_success_does_not_retry(self):
        result = self.compile("printf 'recipe-success:%s\\n' '$(PHASE)'")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_attempts(("normal",))
        self.assertIn("recipe-success:normal", self.assert_log("ci-compile.log", "normal"))
        self.assertFalse((self.source / "ci-compile-retry.log").exists())
        self.assertNotIn("::warning::", result.stdout + result.stderr)

    def test_first_failure_retries_serial_verbose_and_preserves_both_logs(self):
        result = self.compile(
            "if [ '$(V)' != s ]; then printf 'recipe-failure:normal\\n' >&2; exit 7; fi; "
            "printf 'recipe-success:retry\\n'"
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("recipe-success:retry", self.assert_retry_evidence(result))

    def test_two_failures_propagate_nonzero_status_and_preserve_both_logs(self):
        result = self.compile("printf 'recipe-failure:%s\\n' '$(PHASE)' >&2; exit 9")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("recipe-failure:retry", self.assert_retry_evidence(result))


if __name__ == "__main__":
    unittest.main()
