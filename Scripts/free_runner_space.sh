#!/bin/bash
# Reclaim unused SDKs on the disposable build VM, before restoring OpenWrt caches.
set -euo pipefail

if [[ "${GITHUB_ACTIONS:-}" != true || "${RUNNER_ENVIRONMENT:-}" != github-hosted || "${RUNNER_OS:-}" != Linux ]]; then
    echo 'SDK cleanup requires a disposable GitHub-hosted Linux runner.' >&2
    exit 1
fi

readonly -a UNUSED_SDKS=(
    /usr/share/swift
    /usr/share/miniconda
    /usr/local/.ghcup
    /opt/hostedtoolcache/CodeQL
    /usr/local/share/chromium
    /usr/local/share/chromedriver-linux64
    /usr/local/share/edge_driver
    /usr/local/share/gecko_driver
    /usr/local/share/powershell
    /usr/local/share/vcpkg
)

disk_usage() {
    printf '\nRunner storage: %s\n' "$1"
    df -hP /
    df -iP /
}

existing_sdks=()
for path in "${UNUSED_SDKS[@]}" /usr/local/julia[0-9]*; do
    if [[ -e "$path" || -L "$path" ]]; then
        existing_sdks+=("$path")
    fi
done

disk_usage before-sdk-cleanup
if (( ${#existing_sdks[@]} )); then
    sudo du -sh -- "${existing_sdks[@]}"
    sudo rm -rf -- "${existing_sdks[@]}"
fi
sudo apt-get clean
disk_usage after-sdk-cleanup
