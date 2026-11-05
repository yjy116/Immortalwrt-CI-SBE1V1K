#!/bin/bash
# Normal package progress; retain both attempts if a diagnostic retry is needed.
set -euo pipefail

disk_usage() {
    printf '\nBuild storage: %s\n' "$1"
    df -hP . || return
    df -iP .
}

finish() {
    local result=$?
    trap - EXIT
    if ! disk_usage after-compile >> ci-disk.log 2>&1; then
        echo '::error::Could not record final build storage usage.' >&2
        if (( result == 0 )); then result=1; fi
    fi
    exit "$result"
}

disk_usage before-compile > ci-disk.log 2>&1
trap finish EXIT

if make -j"$(nproc)" 2>&1 | tee ci-compile.log; then
    exit 0
fi

echo '::warning::Parallel build failed; retrying with one job and verbose output.'
make -j1 V=s 2>&1 | tee ci-compile-retry.log
