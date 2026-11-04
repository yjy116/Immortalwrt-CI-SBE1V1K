#!/bin/bash
set -eu
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$ROOT_DIR/files/etc/uci-defaults/89-daede-migrate"
[ -f "$SCRIPT" ] || { echo 'missing legacy daede migration'; exit 1; }
TEST_DIR=$(mktemp -d)
trap 'rm -rf "$TEST_DIR"' EXIT
export IPKG_INSTROOT="$TEST_DIR"
mkdir -p "$TEST_DIR/etc/"{config,crontabs,daed,init.d,hotplug.d/iface}
printf 'database sentinel\n' > "$TEST_DIR/etc/daed/wing.db"
printf 'config sentinel\n' > "$TEST_DIR/etc/config/daed"
printf '19 3 * * 2 /etc/daed/daed_sub.sh >/dev/null 2>&1\n0 0 * * * unrelated\n' \
  > "$TEST_DIR/etc/crontabs/root"
cp "$TEST_DIR/etc/crontabs/root" "$TEST_DIR/original.cron"
touch "$TEST_DIR/etc/init.d/luci_daed" "$TEST_DIR/etc/hotplug.d/iface/98-daed"

# Only UCI/logger are stubbed; file migration operates on the real fixture.
uci() {
  shift 2
  if [ "$1" = -q ]; then shift; fi
  case "$*" in
    'get dae.config.enabled') echo 1 ;;
    'get daed.config.enabled') echo 0 ;;
    set*|commit*) printf '%s\n' "$*" >> "$TEST_DIR/uci.calls" ;;
    *) return 1 ;;
  esac
}
logger() { printf '%s\n' "$*" >> "$TEST_DIR/messages"; }
( source "$SCRIPT" )
grep -Fxq '19 3 * * 2 /usr/share/luci-app-daede/daed-sub-update.sh >/dev/null 2>&1' \
  "$TEST_DIR/etc/crontabs/root"
grep -Fxq '0 0 * * * unrelated' "$TEST_DIR/etc/crontabs/root"
cmp "$TEST_DIR/original.cron" "$TEST_DIR/etc/daede-migration-backup/root.cron"
grep -Fxq 'database sentinel' "$TEST_DIR/etc/daed/wing.db"
grep -Fxq 'config sentinel' "$TEST_DIR/etc/config/daed"
grep -Fxq 'set daede.config.active_backend=dae' "$TEST_DIR/uci.calls"
[ ! -e "$TEST_DIR/etc/init.d/luci_daed" ]
[ ! -e "$TEST_DIR/etc/hotplug.d/iface/98-daed" ]
cp "$TEST_DIR/etc/crontabs/root" "$TEST_DIR/once.cron"
( source "$SCRIPT" )
cmp "$TEST_DIR/once.cron" "$TEST_DIR/etc/crontabs/root"
cmp "$TEST_DIR/original.cron" "$TEST_DIR/etc/daede-migration-backup/root.cron"
echo 'legacy migration preserves schedule/data and is repeatable'
