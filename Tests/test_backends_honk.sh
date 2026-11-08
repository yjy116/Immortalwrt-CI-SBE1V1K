#!/bin/bash
set -eu
HONK_DIR=${1:?pass the prepared openwrt-honk directory}
TEST_DIR=$(mktemp -d)
trap 'rm -rf "$TEST_DIR"' EXIT
export TEST_DIR
INIT="$HONK_DIR/honk/files/honk.init"
RPC="$HONK_DIR/luci-app-honk/root/usr/libexec/rpcd/honk"
FIXTURES=$(cd "$(dirname "$0")/fixtures" && pwd)
# Keep upstream lifecycle decisions; map only router paths and I/O into fixtures.
sed -e "s|/var/run/honk|$TEST_DIR/runtime|g" \
  -e 's|/etc/init.d/honk|honk_init_fixture|g' \
  "$HONK_DIR/honk/files/lifecycle.sh" > "$TEST_DIR/lifecycle.sh"
printf '\nsource "%s/honk_lifecycle.sh"\n' "$FIXTURES" >> "$TEST_DIR/lifecycle.sh"
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
    -e "s|/usr/share/honk/lifecycle.sh|$TEST_DIR/lifecycle.sh|g" \
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

for action in start boot; do
  check_service 0 0 "$action"
  check_service 0 1 "$action"
  check_service 1 0 "$action"
  check_service 1 1 "$action"
done

check_restart() (
  EXPECT_ENABLED=1 EXPECT_INITIALIZED=1 action=$1 scenario=$2
  ROUTER_STATE=old
  : > "$TEST_DIR/effects"
  load_init
  result=0
  "$action" 2> "$TEST_DIR/errors" || result=$?
  case "$scenario" in
    normal)
      [ "$result" = 0 ]
      printf 'stop\ndrain\nlaunch\n' > "$TEST_DIR/expected"
      cmp "$TEST_DIR/expected" "$TEST_DIR/effects" ;;
    stop_failure)
      [ "$result" != 0 ]
      ! grep -qx launch "$TEST_DIR/effects"
      grep -q 'unmanaged honk-core process remains' "$TEST_DIR/errors" ;;
    start_failure)
      [ "$result" != 0 ]
      ! grep -qx launch "$TEST_DIR/effects"
      grep -q 'init start failed' "$TEST_DIR/errors" ;;
    *) echo "unknown restart scenario: $scenario" >&2; return 99 ;;
  esac
  [ "$EXPECT_ENABLED" = 1 ]
  cmp "$TEST_DIR/config.dae" "$TEST_DIR/original.dae"
)

for action in restart reload_service; do
  for scenario in normal stop_failure start_failure; do
    check_restart "$action" "$scenario"
  done
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
  emit_result() { printf '%s %s\n' "$1" "$2" >> "$TEST_DIR/rpc-effects"; }
  honk_lifecycle_managed_pid() { :; }
  honk_lifecycle_start() { echo launch >> "$TEST_DIR/rpc-effects"; return "${start_status:-0}"; }
  honk_lifecycle_stop() { echo stop >> "$TEST_DIR/rpc-effects"; return "${stop_status:-0}"; }
  honk_lifecycle_restart() { echo restart >> "$TEST_DIR/rpc-effects"; return "${restart_status:-0}"; }
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
if start_status=1 check_rpc 0 start; then echo 'failed start unexpectedly succeeded'; exit 1; fi
[ "$(command cat "$TEST_DIR/enabled")" = 0 ]
if restart_status=1 check_rpc 0 restart; then echo 'failed restart unexpectedly succeeded'; exit 1; fi
[ "$(command cat "$TEST_DIR/enabled")" = 0 ]

load_rpc_lifecycle() {
  load_init
  source "$TEST_DIR/rpc-functions"
  source "$TEST_DIR/lifecycle.sh"
  config_get_bool() {
    case "$3" in
      enabled) printf -v "$1" '%s' "$(command cat "$TEST_DIR/enabled")" ;;
      initialized) printf -v "$1" '%s' "$EXPECT_INITIALIZED" ;;
      *) return 99 ;;
    esac
  }
  begin_mutation() { :; }
  emit_result() { printf '%s %s\n' "$1" "$2" >> "$TEST_DIR/rpc-result"; }
}

check_rpc_lifecycle() (
  scenario=$1 EXPECT_INITIALIZED=1 ROUTER_STATE=old
  printf '0\n' > "$TEST_DIR/enabled"
  : > "$TEST_DIR/effects"
  : > "$TEST_DIR/rpc-effects"
  : > "$TEST_DIR/rpc-result"
  load_rpc_lifecycle
  result=0
  (set -- call restart; source "$TEST_DIR/rpc-dispatch") 2> "$TEST_DIR/errors" || result=$?
  case "$scenario" in
    normal)
      [ "$result" = 0 ] || {
        command cat "$TEST_DIR/errors" >&2
        echo 'RPC lifecycle restart unexpectedly failed' >&2; return 1;
      }
      [ "$(command cat "$TEST_DIR/enabled")" = 1 ]
      printf 'stop\ndrain\nlaunch\n' > "$TEST_DIR/expected"
      printf 'true restarted\n' > "$TEST_DIR/expected-result"
      printf 'commit\n' > "$TEST_DIR/expected-commits" ;;
    stop_failure)
      [ "$result" != 0 ]
      [ "$(command cat "$TEST_DIR/enabled")" = 0 ]
      printf 'stop\ndrain\n' > "$TEST_DIR/expected"
      printf 'false restart_failed\n' > "$TEST_DIR/expected-result"
      printf 'commit\ncommit\n' > "$TEST_DIR/expected-commits"
      grep -q 'unmanaged honk-core process remains' "$TEST_DIR/errors" ;;
    *) echo "unknown RPC lifecycle scenario: $scenario" >&2; return 99 ;;
  esac
  cmp "$TEST_DIR/expected" "$TEST_DIR/effects"
  cmp "$TEST_DIR/expected-result" "$TEST_DIR/rpc-result"
  cmp "$TEST_DIR/expected-commits" "$TEST_DIR/rpc-effects"
  cmp "$TEST_DIR/config.dae" "$TEST_DIR/original.dae"
)

check_rpc_lifecycle normal
check_rpc_lifecycle stop_failure
cmp "$TEST_DIR/config.dae" "$TEST_DIR/original.dae"
echo 'PASS: native Honk restart drains before start; failures propagate; RPC intent rolls back; boot follows enabled'
