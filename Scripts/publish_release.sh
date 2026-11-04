#!/bin/bash
# Shared by the build pipeline and publication-only recovery runs.
set -euo pipefail

tag="sbe1v1k-wifi-${WIFI}-${BUILD_RUN_ID}-${BUILD_ATTEMPT}"
python3 Scripts/release_tag.py --tag "$tag"
cd artifacts
sha256sum -c SHA256SUMS-CI
source_commit=$(jq -r .commit ci-source.json)
source_repo=$(jq -r .repository ci-source.json)
source_branch=$(jq -r .branch ci-source.json)
cat > "$RUNNER_TEMP/release-notes.md" <<EOF
SBE1V1K / qualcommbe / ipq95xx / WiFi-${WIFI}

管理地址：192.168.70.1；首次登录请设置 root 密码。
源码：${source_repo}（${source_branch}）。
源码提交：${source_commit}；CI 提交：${CI_COMMIT}。
构建：https://github.com/${GH_REPO}/actions/runs/${BUILD_RUN_ID}
无线版本初始不启用广播，启用前请设置实际国家和加密口令。
factory.bin 不是原厂 Web 直刷包；请阅读仓库 docs/DEVICE.md。
本发布证明编译和产物校验通过，不代表实机验证。
EOF
mapfile -d '' assets < <(find . -maxdepth 1 -type f -print0)
draft=$(gh api --paginate "repos/$GH_REPO/releases" \
  --jq ".[] | select(.tag_name == \"$tag\") | .draft")
case "$draft" in
  '')
    gh release create "$tag" --verify-tag --draft \
      --title "SBE1V1K WiFi-${WIFI} ${BUILD_RUN_ID}" \
      --notes-file "$RUNNER_TEMP/release-notes.md"
    ;;
  true) echo "Resuming uploads to existing draft $tag" ;;
  *) echo "Release $tag is already published; refusing to replace it" >&2; exit 1 ;;
esac
gh release upload "$tag" "${assets[@]}" --clobber
gh release edit "$tag" --draft=false
