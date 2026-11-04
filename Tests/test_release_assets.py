"""Verify publication only removes known legacy assets after new uploads pass."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Scripts"))
from release_assets import finalize_draft

REPOSITORY = "yjy116/Immortalwrt-CI-SBE1V1K"
TAG = "sbe1v1k-wifi-yes-123-1"
RELEASE_ID = 42
ASSET_COUNT = 7
LEGACY_COUNT = 19


def publication_plan():
    assets = [{"name": f"new-{index}.bin", "sha256": f"{index:064x}", "size": index}
              for index in range(1, ASSET_COUNT + 1)]
    return {"repository": REPOSITORY, "tag": TAG, "assets": assets}


def uploaded_assets(plan):
    return [{"id": index, "name": entry["name"], "size": entry["size"],
             "digest": f"sha256:{entry['sha256']}", "state": "uploaded"}
            for index, entry in enumerate(plan["assets"], start=1)]


class GitHubApi:
    def __init__(self, assets, draft=True):
        self.assets = deepcopy(assets)
        self.release = {"id": RELEASE_ID, "tag_name": TAG, "draft": draft}
        self.calls = []
        self.deleted = []
        self.preserve_deleted = False
        self.asset_reads = 0
        self.readback_override = None

    def __call__(self, arguments):
        self.calls.append(list(arguments))
        endpoint = arguments[-1]
        prefix = f"repos/{REPOSITORY}/releases"
        if arguments[:2] == ["--method", "DELETE"]:
            asset_id = int(endpoint.rsplit("/", 1)[1])
            self.deleted.append(asset_id)
            if not self.preserve_deleted:
                self.assets = [asset for asset in self.assets if asset["id"] != asset_id]
            return None
        if endpoint == f"{prefix}?per_page=100":
            return [[{"id": 1, "tag_name": "unrelated", "draft": False}],
                    [deepcopy(self.release)]]
        if endpoint == f"{prefix}/{RELEASE_ID}/assets?per_page=100":
            self.asset_reads += 1
            if self.asset_reads > 1 and self.readback_override is not None:
                return [deepcopy(self.readback_override)]
            return [deepcopy(self.assets[:3]), deepcopy(self.assets[3:])]
        raise AssertionError(f"Unexpected API request: {arguments}")


class ReleaseAssetTests(unittest.TestCase):
    def setUp(self):
        self.plan = publication_plan()
        self.current = uploaded_assets(self.plan)
        self.legacy = [{"id": 100 + index, "name": f"original-{index}.json"}
                       for index in range(LEGACY_COUNT)]
        self.original_names = {asset["name"] for asset in self.legacy}

    def test_complete_new_layout_requires_no_deletion_and_is_read_back(self):
        api = GitHubApi(self.current)
        before = deepcopy(self.plan)
        finalize_draft(self.plan, self.original_names, api)
        self.assertEqual(api.deleted, [])
        asset_reads = [call for call in api.calls if "/assets?" in call[-1]]
        self.assertEqual(len(asset_reads), 2)
        self.assertTrue(all(call[:2] == ["--paginate", "--slurp"] for call in asset_reads))
        self.assertEqual(self.plan, before)

    def test_known_legacy_layout_is_deleted_only_after_new_assets_verify(self):
        api = GitHubApi([*self.legacy, *self.current])
        finalize_draft(self.plan, self.original_names, api)
        self.assertEqual(set(api.deleted), {asset["id"] for asset in self.legacy})
        self.assertEqual({asset["name"] for asset in api.assets},
                         {asset["name"] for asset in self.current})
        self.assertEqual(api.calls[0][:2], ["--paginate", "--slurp"])
        self.assertIn("/assets?", api.calls[1][-1])
        self.assertEqual(api.calls[2][:2], ["--method", "DELETE"])

    def test_missing_new_asset_rejects_before_deleting_legacy_assets(self):
        api = GitHubApi([*self.legacy, *self.current[:-1]])
        with self.assertRaisesRegex(ValueError, "Missing"):
            finalize_draft(self.plan, self.original_names, api)
        self.assertEqual(api.deleted, [])

    def test_incorrect_hash_size_or_upload_state_rejects_before_deletion(self):
        for field, value in (("digest", "sha256:" + "f" * 64), ("digest", None),
                             ("size", 999), ("state", "starter")):
            with self.subTest(field=field, value=value):
                current = deepcopy(self.current)
                current[0][field] = value
                api = GitHubApi([*self.legacy, *current])
                with self.assertRaisesRegex(ValueError, "mismatch|uploaded"):
                    finalize_draft(self.plan, self.original_names, api)
                self.assertEqual(api.deleted, [])

    def test_unknown_extra_prevents_all_deletions(self):
        unknown = {"id": 900, "name": "unrelated-user-upload.txt"}
        api = GitHubApi([*self.legacy, *self.current, unknown])
        with self.assertRaisesRegex(ValueError, "Unknown"):
            finalize_draft(self.plan, self.original_names, api)
        self.assertEqual(api.deleted, [])

    def test_public_release_is_never_modified(self):
        api = GitHubApi([*self.current, *self.legacy], draft=False)
        with self.assertRaisesRegex(ValueError, "draft"):
            finalize_draft(self.plan, self.original_names, api)
        self.assertEqual(api.deleted, [])

    def test_duplicate_remote_names_or_ids_are_rejected(self):
        for extra in (self.current[0], {**self.legacy[0], "id": self.current[0]["id"]}):
            with self.subTest(extra=extra):
                api = GitHubApi([*self.current, extra])
                with self.assertRaisesRegex(ValueError, "Duplicate"):
                    finalize_draft(self.plan, self.original_names, api)
                self.assertEqual(api.deleted, [])

    def test_failed_remote_cleanup_is_exposed_by_final_readback(self):
        api = GitHubApi([*self.current, self.legacy[0]])
        api.preserve_deleted = True
        with self.assertRaisesRegex(ValueError, "exact"):
            finalize_draft(self.plan, self.original_names, api)
        self.assertEqual(api.deleted, [self.legacy[0]["id"]])

    def test_hash_change_on_final_readback_is_rejected(self):
        api = GitHubApi(self.current)
        api.readback_override = deepcopy(self.current)
        api.readback_override[0]["digest"] = "sha256:" + "f" * 64
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            finalize_draft(self.plan, self.original_names, api)
        self.assertEqual(api.deleted, [])

    def test_invalid_remote_asset_id_is_rejected_without_deletion(self):
        for identifier in (None, "1", True, -1):
            with self.subTest(identifier=identifier):
                api = GitHubApi([*self.current, {**self.legacy[0], "id": identifier}])
                with self.assertRaisesRegex(ValueError, "object ID"):
                    finalize_draft(self.plan, self.original_names, api)
                self.assertEqual(api.deleted, [])

    def test_duplicate_plan_names_fail_before_any_api_call(self):
        plan = {**self.plan, "assets": [*self.plan["assets"][:-1], self.plan["assets"][0]]}
        api = GitHubApi(self.current)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            finalize_draft(plan, self.original_names, api)
        self.assertEqual(api.calls, [])

    def test_non_seven_asset_plan_is_rejected(self):
        plan = {**self.plan, "assets": self.plan["assets"][:-1]}
        api = GitHubApi(self.current)
        with self.assertRaisesRegex(ValueError, "seven"):
            finalize_draft(plan, self.original_names, api)
        self.assertEqual(api.calls, [])


if __name__ == "__main__":
    unittest.main()
