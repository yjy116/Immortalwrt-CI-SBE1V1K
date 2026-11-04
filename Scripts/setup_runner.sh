#!/bin/bash
set -euo pipefail

# Only used on the disposable GitHub-hosted Ubuntu runner.
if [[ "${CONFIG_ONLY:-false}" != true ]]; then
    sudo rm -rf /usr/share/dotnet /usr/local/lib/android /opt/ghc
fi
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
    build-essential clang-18 llvm-18 libclang-18-dev lld-18 \
    flex bison g++ gawk gcc-multilib g++-multilib \
    gettext git libncurses-dev libssl-dev python3 python3-setuptools \
    python3-packaging python3-pyelftools rsync swig unzip zlib1g-dev \
    file wget curl ccache jq bc cmake cpio libelf-dev device-tree-compiler \
    patch perl pkgconf qemu-utils zstd libdw-dev libbpf-dev
df -h
