#!/bin/bash
set -euo pipefail
PACKAGE_DIR=${1:?pass the prepared v2ray-geodata-updater package directory}
SCRIPT="$PACKAGE_DIR/files/v2ray-geodata-updater"
TEST_DIR=$(mktemp -d)
trap 'rm -rf "$TEST_DIR"' EXIT
export V2RAY_DATA_DIR="$TEST_DIR/data" DAE_INIT_DIR="$TEST_DIR/init"
mkdir -p "$V2RAY_DATA_DIR" "$DAE_INIT_DIR"

# Stub network/log I/O only; hashes and filesystem replacement are real.
curl() {
  local url=${@: -1} output=${3}
  [ "${FAIL_DOWNLOAD:-}" != "$url" ] || return 22
  case "$url" in
    *.sha256sum)
      if [ "${BAD_HASH:-}" = yes ]; then
        printf '%064d  data.dat\n' 0 > "$output"
      else
        printf 'new data\n' | sha256sum > "$output"
      fi ;;
    *) printf 'new data\n' > "$output" ;;
  esac
}
logger() { :; }
export -f curl logger

printf 'old ip\n' > "$V2RAY_DATA_DIR/geoip.dat"
printf 'old site\n' > "$V2RAY_DATA_DIR/geosite.dat"
export BAD_HASH=yes
if bash "$SCRIPT"; then
  echo 'corrupted update reported success'; exit 1
fi
grep -Fxq 'old ip' "$V2RAY_DATA_DIR/geoip.dat"
grep -Fxq 'old site' "$V2RAY_DATA_DIR/geosite.dat"
if compgen -G "$V2RAY_DATA_DIR/.update.*" >/dev/null; then
  echo 'failed update left temporary files'; exit 1
fi
unset BAD_HASH

export FAIL_DOWNLOAD=https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat
if bash "$SCRIPT"; then
  echo 'failed download reported success'; exit 1
fi
grep -Fxq 'old ip' "$V2RAY_DATA_DIR/geoip.dat"
grep -Fxq 'old site' "$V2RAY_DATA_DIR/geosite.dat"
unset FAIL_DOWNLOAD

bash "$SCRIPT"
grep -Fxq 'new data' "$V2RAY_DATA_DIR/geoip.dat"
grep -Fxq 'new data' "$V2RAY_DATA_DIR/geosite.dat"
echo 'geodata verifies both downloads before replacing installed data'
