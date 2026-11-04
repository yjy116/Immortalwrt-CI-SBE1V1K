#!/bin/bash
set -eu
HONK_DIR=${1:?pass the prepared openwrt-honk directory}
TEST_DIR=$(mktemp -d)
trap 'rm -rf "$TEST_DIR"' EXIT
export TEST_DIR
INIT="$HONK_DIR/honk/files/honk.init"
RPC="$HONK_DIR/luci-app-honk/root/usr/libexec/rpcd/honk"
printf 'configuration sentinel\n' > "$TEST_DIR/config.dae"
cp "$TEST_DIR/config.dae" "$TEST_DIR/original.dae"

# Real service/dispatch code; only OpenWrt filesystem, UCI and procd I/O are fixtures.
config_load() { :; }
config_get_bool() {
  case "$3" in
    enabled) printf -v "$1" '%s' "$EXPECT_ENABLED" ;;
    initialized) printf -v "$1" '%s' "$EXPECT_INITIALIZED" ;;
    *) return 99 ;;
  esac
}
config_get() { printf -v "$1" '%s' "$4"; }
logger() { :; }
procd_open_instance() { echo launch >> "$TEST_DIR/effects"; }
procd_set_param() { :; }
procd_close_instance() { return "${close_status:-0}"; }
control_fixture() { :; }
honk_core_fixture() { echo '{}'; }
jsonfilter() {
  case "$*" in
    *native_api_enabled) echo true ;;
    *clash_api_secret_set) echo false ;;
    *native_api_listen) echo 192.168.70.1:9527 ;;
    *clash_api_listen) echo '' ;;
    *) return 99 ;;
  esac
}
cat() {
  if [ "$1" = /proc/sys/kernel/random/uuid ]; then
    echo 00000000-0000-0000-0000-000000000001
  else command cat "$@"; fi
}

load_init() {
  source <(sed -e '\|^\. /lib/functions.sh$|d' \
    -e 's|/usr/bin/honk-core|honk_core_fixture|g' \
    -e "s|/var/run/honk|$TEST_DIR/runtime|g" "$INIT")
  HONK_CONFIG="$TEST_DIR/config.dae"
  HONK_CONTROL=control_fixture
}

# Preserve native rc.common dispatch; verify launch/intent, not a custom status hook.
start() {
  start_service
  :
  if type service_started >/dev/null 2>&1; then service_started; fi
}
restart() { start; }

check_service() (
  EXPECT_ENABLED=$1 EXPECT_INITIALIZED=$2 action=$3
  : > "$TEST_DIR/effects"
  load_init
  result=0
  "$action" || result=$?
  if [ "$EXPECT_ENABLED:$EXPECT_INITIALIZED" = 1:1 ]; then
    { [ "$result" = 0 ] && grep -qx launch "$TEST_DIR/effects"; } || {
      echo "enabled service failed to launch: $action"; return 1;
    }
  else
    [ ! -s "$TEST_DIR/effects" ] || {
      echo "disabled/uninitialized service launched: $action"; return 1;
    }
  fi
  [ "$EXPECT_ENABLED" = "$1" ]
  cmp "$TEST_DIR/config.dae" "$TEST_DIR/original.dae"
)

for action in start boot restart reload_service; do
  check_service 0 0 "$action"
  check_service 0 1 "$action"
  check_service 1 0 "$action"
  check_service 1 1 "$action"
done

# Exercise actual RPC case arms, not rewritten enable/disable logic.
sed '/^case "\$1" in$/,$d' "$RPC" | sed '\|^\. /|d' > "$TEST_DIR/rpc-functions"
sed -n '/^case "\$1" in$/,$p' "$RPC" > "$TEST_DIR/rpc-dispatch"
uci() {
  case "$*" in
    '-q get honk.main.enabled') command cat "$TEST_DIR/enabled" ;;
    set\ honk.main.enabled=*) printf '%s\n' "${2#*=}" > "$TEST_DIR/enabled" ;;
    'commit honk') echo commit >> "$TEST_DIR/rpc-effects" ;;
    *) echo "unexpected UCI operation: $*" >&2; return 99 ;;
  esac
}
pidof() { return 1; }

check_rpc() (
  printf '%s\n' "$1" > "$TEST_DIR/enabled"
  : > "$TEST_DIR/rpc-effects"
  source "$TEST_DIR/rpc-functions"
  begin_mutation() { :; }
  service_ready_config() { return 0; }
  emit_result() { printf '%s %s\n' "$*" >> "$TEST_DIR/rpc-effects"; }
  honk_lifecycle_managed_pid() { :; }
  honk_lifecycle_start() { echo launch >> "$TEST_DIR/rpc-effects"; }
  honk_lifecycle_stop() { echo stop >> "$TEST_DIR/rpc-effects"; return "${stop_status:-0}"; }
  honk_lifecycle_restart() { echo restart >> "$TEST_DIR/rpc-effects"; }
  set -- call "$2"
  source "$TEST_DIR/rpc-dispatch"
)

check_rpc 0 restart
[ "$(command cat "$TEST_DIR/enabled")" = 1 ]
grep -qx restart "$TEST_DIR/rpc-effects"
grep -qx commit "$TEST_DIR/rpc-effects"
check_rpc 0 start
[ "$(command cat "$TEST_DIR/enabled")" = 1 ]
grep -qx launch "$TEST_DIR/rpc-effects"
check_rpc 1 restart
[ "$(command cat "$TEST_DIR/enabled")" = 1 ]
grep -qx restart "$TEST_DIR/rpc-effects"
check_rpc 1 stop
[ "$(command cat "$TEST_DIR/enabled")" = 0 ]
grep -qx stop "$TEST_DIR/rpc-effects"
if stop_status=1 check_rpc 1 stop; then echo 'failed stop unexpectedly succeeded'; exit 1; fi
[ "$(command cat "$TEST_DIR/enabled")" = 1 ]
cmp "$TEST_DIR/config.dae" "$TEST_DIR/original.dae"
echo 'PASS: native Honk start/restart enable, successful stop disables, boot follows enabled'
