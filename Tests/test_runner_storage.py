"""Exercise cleanup guards with real Bash and a sudo boundary that never deletes."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Scripts/free_runner_space.sh"
TIMEOUT_SECONDS = 15
SUDO_FAILURE_STATUS = 73
ALLOWED_ENVIRONMENT = {
    "GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted", "RUNNER_OS": "Linux",
}
EXPECTED_SDKS = {
    "/usr/share/swift", "/usr/share/miniconda", "/usr/local/.ghcup",
    "/opt/hostedtoolcache/CodeQL", "/usr/local/share/chromedriver-linux64",
    "/usr/local/share/chromium", "/usr/local/share/edge_driver",
    "/usr/local/share/gecko_driver", "/usr/local/share/powershell", "/usr/local/share/vcpkg",
}
HARNESS = r'''
sudo() {
    printf '%s\t' "$@" >> "$CALLS_FILE"
    printf '\n' >> "$CALLS_FILE"
    if [[ "${SUDO_FAILURE_COMMAND:-}" == "$1" ]]; then return 73; fi
    return 0
}
export -f sudo
source "$1"
declare -p UNUSED_SDKS > "$DECLARATION_FILE"
printf '%s\n' "${UNUSED_SDKS[@]}" > "$WHITELIST_FILE"
'''


def bash_executable():
    bash = shutil.which("bash")
    if bash:
        return bash
    git = shutil.which("git")
    if os.name == "nt" and git:
        candidate = Path(git).resolve().parents[1] / "bin/bash.exe"
        if candidate.is_file():
            return str(candidate)
    raise RuntimeError("Bash is required to execute runner cleanup guard tests")


class RunnerStorageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.bash = bash_executable()

    def run_cleanup(self, settings, failure_command=""):
        environment = {key: value for key, value in os.environ.items()
                       if key not in ALLOWED_ENVIRONMENT}
        environment.update(settings)
        environment.update({
            "CALLS_FILE": (self.directory / "sudo-calls.txt").as_posix(),
            "DECLARATION_FILE": (self.directory / "declaration.txt").as_posix(),
            "WHITELIST_FILE": (self.directory / "whitelist.txt").as_posix(),
            "SUDO_FAILURE_COMMAND": failure_command, "LC_ALL": "C",
        })
        result = subprocess.run(
            [self.bash, "-c", HARNESS, "cleanup-test", SCRIPT.as_posix()],
            cwd=self.directory, env=environment, capture_output=True,
            text=True, timeout=TIMEOUT_SECONDS,
        )
        log = self.directory / "sudo-calls.txt"
        calls = [line.rstrip("\t").split("\t") for line in log.read_text().splitlines()] if log.exists() else []
        return result, calls

    def test_non_hosted_environments_reject_before_any_sudo(self):
        cases = [{}, {**ALLOWED_ENVIRONMENT, "GITHUB_ACTIONS": "false"},
                 {**ALLOWED_ENVIRONMENT, "RUNNER_ENVIRONMENT": "self-hosted"},
                 {**ALLOWED_ENVIRONMENT, "RUNNER_OS": "Windows"}]
        cases += [{key: value for key, value in ALLOWED_ENVIRONMENT.items() if key != missing}
                  for missing in ALLOWED_ENVIRONMENT]
        for environment in cases:
            with self.subTest(environment=environment):
                result, calls = self.run_cleanup(environment)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("GitHub-hosted Linux", result.stderr)
                self.assertEqual(calls, [], "Unauthorized cleanup reached sudo")

    def test_hosted_cleanup_uses_only_readonly_sdk_allowlist(self):
        result, calls = self.run_cleanup(ALLOWED_ENVIRONMENT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        declaration = (self.directory / "declaration.txt").read_text()
        self.assertIn("declare -ar UNUSED_SDKS=", declaration)
        whitelist = (self.directory / "whitelist.txt").read_text().splitlines()
        self.assertEqual(set(whitelist), EXPECTED_SDKS)
        self.assertEqual(len(whitelist), len(EXPECTED_SDKS))
        self.assertEqual(calls[-1], ["apt-get", "clean"])
        if len(calls) > 1:
            self.assertEqual(len(calls), 3, calls)
            self.assertEqual(calls[0][:3], ["du", "-sh", "--"])
            self.assertEqual(calls[1][:3], ["rm", "-rf", "--"])
            self.assertEqual(calls[0][3:], calls[1][3:])
            for path in calls[1][3:]:
                self.assertTrue(path in EXPECTED_SDKS or self.is_versioned_julia(path), path)
        self.assertIn("Runner storage: before-sdk-cleanup", result.stdout)
        self.assertIn("Runner storage: after-sdk-cleanup", result.stdout)
        self.assertIn("Inodes", result.stdout)

    @staticmethod
    def is_versioned_julia(path):
        prefix = "/usr/local/julia"
        return path.startswith(prefix) and path[len(prefix):len(prefix) + 1].isdigit()

    def test_sudo_failure_propagates_without_success_snapshot(self):
        result, calls = self.run_cleanup(ALLOWED_ENVIRONMENT, "apt-get")
        self.assertEqual(result.returncode, SUDO_FAILURE_STATUS, result.stdout + result.stderr)
        self.assertEqual(calls[-1], ["apt-get", "clean"])
        self.assertNotIn("Runner storage: after-sdk-cleanup", result.stdout)


if __name__ == "__main__":
    unittest.main()
