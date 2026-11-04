#!/bin/bash
# Normal package progress; retain both attempts if a diagnostic retry is needed.
set -euo pipefail

if make -j"$(nproc)" 2>&1 | tee ci-compile.log; then
    exit 0
fi

echo '::warning::Parallel build failed; retrying with one job and verbose output.'
make -j1 V=s 2>&1 | tee ci-compile-retry.log
