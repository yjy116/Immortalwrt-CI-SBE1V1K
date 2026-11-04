#!/bin/bash
# Shared by the build pipeline and publication-only recovery runs.
set -euo pipefail

tag="sbe1v1k-wifi-${WIFI}-${BUILD_RUN_ID}-${BUILD_ATTEMPT}"
python3 Scripts/release_tag.py --tag "$tag"
gh api "repos/$GH_REPO/actions/runs/$BUILD_RUN_ID" > "$RUNNER_TEMP/build-run.json"
python3 Scripts/release_layout.py --artifacts artifacts --output "$RUNNER_TEMP/release" \
  --run-metadata "$RUNNER_TEMP/build-run.json" --repository "$GH_REPO" \
  --tag "$tag" --ci-commit "$CI_COMMIT" --wifi "$WIFI"
title=$(jq -r .title "$RUNNER_TEMP/release/release-plan.json")
checksum_file=$(jq -r .checksum_file "$RUNNER_TEMP/release/release-plan.json")
notes="$RUNNER_TEMP/release/release-notes.md"
cd "$RUNNER_TEMP/release/assets"
sha256sum -c "$checksum_file"
mapfile -d '' assets < <(find . -maxdepth 1 -type f -print0)
draft=$(gh api --paginate "repos/$GH_REPO/releases" \
  --jq ".[] | select(.tag_name == \"$tag\") | .draft")
case "$draft" in
  '')
    gh release create "$tag" --verify-tag --draft \
      --title "$title" --notes-file "$notes"
    ;;
  true) echo "Resuming uploads to existing draft $tag" ;;
  *) echo "Release $tag is already published; refusing to replace it" >&2; exit 1 ;;
esac
gh release upload "$tag" "${assets[@]}" --clobber
python3 "$GITHUB_WORKSPACE/Scripts/release_assets.py" \
  --plan "$RUNNER_TEMP/release/release-plan.json" \
  --artifacts "$GITHUB_WORKSPACE/artifacts" --tag "$tag"
gh release edit "$tag" --draft=false --title "$title" --notes-file "$notes"
