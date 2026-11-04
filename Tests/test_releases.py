"""Check release tag decisions with the GitHub API as an injected boundary."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Scripts"))
from release_tag import check_tag

REPOSITORY = "owner/firmware-ci"
TAG = "sbe1v1k-wifi-yes-12345-1"
COMMIT = "a" * 40
REFERENCE = f"refs/tags/{TAG}"
READ = [f"repos/{REPOSITORY}/git/matching-refs/tags/{TAG}"]
CREATE = ["--method", "POST", f"repos/{REPOSITORY}/git/refs",
          "-f", f"ref={REFERENCE}", "-f", f"sha={COMMIT}"]


def settings(**overrides):
    return SimpleNamespace(**{
        "repository": REPOSITORY, "tag": TAG, "commit": COMMIT, "create": True,
        **overrides,
    })


def reference(**overrides):
    return {"ref": REFERENCE, "object": {"type": "commit", "sha": COMMIT}, **overrides}


class ReleaseTagTests(unittest.TestCase):
    def invoke(self, options, api):
        with redirect_stdout(io.StringIO()) as output:
            check_tag(options, api)
        return output.getvalue()

    def test_missing_tag_is_created_for_the_exact_ci_commit(self):
        api = Mock(side_effect=[[], reference()])
        output = self.invoke(settings(), api)
        self.assertEqual(api.call_args_list, [call(READ), call(CREATE)])
        self.assertIn(REFERENCE, output)
        self.assertIn(COMMIT, output)

    def test_existing_matching_tag_is_verified_without_writes(self):
        for create in (False, True):
            with self.subTest(create=create):
                api = Mock(return_value=[reference()])
                self.invoke(settings(create=create), api)
                api.assert_called_once_with(READ)

    def test_wrong_commit_and_annotated_tag_are_rejected_without_writes(self):
        objects = (
            {"type": "commit", "sha": "b" * 40},
            {"type": "tag", "sha": COMMIT},
        )
        for target in objects:
            with self.subTest(target=target):
                api = Mock(return_value=[reference(object=target)])
                with self.assertRaisesRegex(RuntimeError, "expected CI commit"):
                    self.invoke(settings(), api)
                api.assert_called_once_with(READ)

    def test_verify_only_rejects_missing_tag_without_creating_it(self):
        api = Mock(return_value=[])
        with self.assertRaisesRegex(RuntimeError, "Missing build tag"):
            self.invoke(settings(create=False), api)
        api.assert_called_once_with(READ)

    def test_read_api_failure_is_not_treated_as_a_missing_tag(self):
        error = subprocess.CalledProcessError(1, ["gh", "api"], stderr="HTTP 403")
        api = Mock(side_effect=error)
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            self.invoke(settings(), api)
        self.assertIs(caught.exception, error)
        api.assert_called_once_with(READ)

    def test_create_api_failure_is_propagated(self):
        error = subprocess.CalledProcessError(1, ["gh", "api"], stderr="HTTP 422")
        api = Mock(side_effect=[[], error])
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            self.invoke(settings(), api)
        self.assertIs(caught.exception, error)
        self.assertEqual(api.call_args_list, [call(READ), call(CREATE)])

    def test_prefix_match_does_not_satisfy_verify_only(self):
        api = Mock(return_value=[reference(ref=REFERENCE + "0")])
        with self.assertRaisesRegex(RuntimeError, "Missing build tag"):
            self.invoke(settings(create=False), api)
        api.assert_called_once_with(READ)

    def test_prefix_match_does_not_prevent_creating_exact_tag(self):
        api = Mock(side_effect=[[reference(ref=REFERENCE + "-other")], reference()])
        self.invoke(settings(), api)
        self.assertEqual(api.call_args_list, [call(READ), call(CREATE)])

    def test_exact_tag_is_selected_among_prefix_matches(self):
        unrelated = reference(ref=REFERENCE + "0", object={"type": "tag", "sha": "b" * 40})
        api = Mock(return_value=[unrelated, reference()])
        self.invoke(settings(create=False), api)
        api.assert_called_once_with(READ)

    def test_duplicate_exact_references_are_rejected(self):
        api = Mock(return_value=[reference(), reference()])
        with self.assertRaisesRegex(RuntimeError, "Ambiguous build tag"):
            self.invoke(settings(), api)
        api.assert_called_once_with(READ)

    def test_invalid_inputs_fail_before_any_api_request(self):
        cases = (
            {"repository": "owner"}, {"repository": "owner/repo/extra"},
            {"repository": "owner/repo\n"}, {"repository": "owner/repo?query=1"},
            {"tag": "sbe1v1k-wifi-both-12345-1"}, {"tag": TAG + "/other"},
            {"tag": "other-" + TAG}, {"tag": TAG + "\n"},
            {"commit": "a" * 39}, {"commit": "A" * 40},
            {"commit": "z" * 40}, {"commit": COMMIT + "\n"},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                api = Mock()
                with self.assertRaises(ValueError):
                    self.invoke(settings(**overrides), api)
                api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
