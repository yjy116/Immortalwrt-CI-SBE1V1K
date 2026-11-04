#!/bin/bash
set -eu
SOURCE_DIR=${1:?pass the prepared openwrt-daede directory}
HONK_DIR=${2:?pass the prepared openwrt-honk directory}
TEST_DIR=$(mktemp -d)
EFFECTS=$TEST_DIR/effects
ERRORS=$TEST_DIR/errors
trap 'command rm -f "$EFFECTS" "$ERRORS"; rmdir "$TEST_DIR"' EXIT

# Only router I/O is replaced; init, cleanup and lifecycle decisions are real.
extra_command() { :; }
config_load() { :; }
config_get_bool() { printf -v "$1" '%s' "${ENABLED:-1}"; }
config_get() { printf -v "$1" '%s' "$4"; }
uci() { printf '%s\n' "$BACKEND"; }
logger() { printf '%s\n' "$*" >&2; }
procd_open_instance() { printf 'procd-open\n' >> "$EFFECTS"; }
procd_set_param() { :; }
procd_append_param() { :; }
procd_close_instance() { return "${INSTANCE_CLOSE_STATUS:-0}"; }
procd_open_service() { [ "$1" = "$BACKEND" ] && [ "$2" = "$initscript" ]; }
procd_close_service() { SERVICE_CLOSED=1; [ "$1" = set ] || [ "$1" = add ]; }
sleep() { :; }
kill() { printf 'kill %s\n' "$*" >> "$EFFECTS"; }
umount() { printf 'umount %s\n' "$*" >> "$EFFECTS"; }
rm() { printf 'rm %s\n' "$*" >> "$EFFECTS"; }

pidof() {
  if [ "$1" = honk-core ]; then
    [ "$HONK_STATUS" != 0 ] || printf '4242\n'
    return "$HONK_STATUS"
  fi
  [ "$1" = "${PEER:-none}" ] || return 1
  printf '4243\n'
}

pgrep() {
  [ "${PEER:-none}" = daed ] || return 1
  printf '4243\n'
}

ip() {
  case "$*" in
    'netns pids daens')
      [ "$HONK_STATUS" != 0 ] || printf '4242\n'
      [ "${PEER:-none}" = none ] || printf '4243\n'
      return 0 ;;
    'netns list') [ "$NETNS" = 0 ] || printf 'daens\n'; return 0 ;;
    'link show dae0'|'link show dae0peer') [ "$LINK" = 1 ] ;;
    'netns del daens') NETNS=0; printf 'delete-netns\n' >> "$EFFECTS" ;;
    'link del dae0') LINK=0; printf 'delete-link\n' >> "$EFFECTS" ;;
    *) echo "unexpected ip call: $*" >&2; return 99 ;;
  esac
}

reset_io() {
  : > "$EFFECTS"
  : > "$ERRORS"
  NETNS=1
  LINK=1
}

load_init() {
  source "$SOURCE_DIR/daed/files/daed-cleanup.sh"
  source <(sed '\|^\. /usr/share/daed/cleanup.sh$|d' \
    "$SOURCE_DIR/$BACKEND/files/$BACKEND.init")
  PROG=true
}

assert_refused() {
  [ "$1" -ne 0 ] || { echo 'operation incorrectly succeeded'; return 1; }
  [ ! -s "$EFFECTS" ] || {
    echo 'refused operation changed router state:'; cat "$EFFECTS"; return 1;
  }
  grep -Eqi 'honk|probe|process|datapath' "$ERRORS" || {
    echo 'missing explicit refusal diagnostic'; cat "$ERRORS"; return 1;
  }
}

check_start() (
  BACKEND=$1 HONK_STATUS=$2 PEER=none
  reset_io
  load_init
  result=0
  start_service 2> "$ERRORS" || result=$?
  if [ "$HONK_STATUS" = 1 ]; then
    [ "$result" = 0 ] && grep -qx procd-open "$EFFECTS"
  else
    assert_refused "$result"
  fi
)

router_rc_procd() {
  local method=set
  [ -n "${2:-}" ] && method=add
  procd_open_service "$BACKEND" "$initscript"
  "$@"
  procd_close_service "$method"
}

router_start() {
  # Same-process rc.common dispatch: close_service masks the method status.
  router_rc_procd start_service "$@"
  if eval 'type service_started' >/dev/null 2>&1; then service_started; fi
}

check_start_dispatch() (
  BACKEND=$1 HONK_STATUS=$2 PEER=none
  initscript=$SOURCE_DIR/$BACKEND/files/$BACKEND.init
  SERVICE_CLOSED=0
  reset_io
  load_init
  result=0
  router_start 2> "$ERRORS" || result=$?
  [ "$SERVICE_CLOSED" = 1 ] || { echo 'wrapper did not close service'; return 1; }
  if [ "$HONK_STATUS" = 1 ]; then
    [ "$result" = 0 ] && grep -qx procd-open "$EFFECTS"
  else
    assert_refused "$result"
  fi
)

check_start_status_reset() (
  BACKEND=$1 HONK_STATUS=1 PEER=none ENABLED=1 INSTANCE_CLOSE_STATUS=0
  initscript=$SOURCE_DIR/$BACKEND/files/$BACKEND.init
  reset_io
  load_init
  router_start 2> "$ERRORS" || { echo 'initial start failed'; return 1; }
  grep -qx procd-open "$EFFECTS" || { echo 'initial start skipped instance'; return 1; }
  reset_io
  case "$2" in
    honk) HONK_STATUS=0 ;;
    disabled) ENABLED=0 ;;
    instance-error) INSTANCE_CLOSE_STATUS=1 ;;
    *) echo "unknown scenario: $2"; return 1 ;;
  esac
  result=0
  router_start 2> "$ERRORS" || result=$?
  [ "$result" -ne 0 ] || { echo 'previous success leaked into rejected start'; return 1; }
  if [ "$2" = honk ]; then assert_refused "$result" || return 1; fi
  if [ "$2" = disabled ]; then [ ! -s "$EFFECTS" ]; fi
)

check_cleanup() (
  BACKEND=${1%%:*} HONK_STATUS=$2 PEER=none
  DAED_GUARD_CLEANUP=${1#*:}
  reset_io
  load_init
  result=0
  if [ "$BACKEND" = dae ]; then
    stop_service 2> "$ERRORS" || result=$?
  else
    daed_cleanup_runtime 2> "$ERRORS" || result=$?
  fi
  if [ "$HONK_STATUS" = 1 ]; then
    [ "$result" = 0 ] || { cat "$ERRORS"; return 1; }
    grep -qx delete-netns "$EFFECTS" && grep -qx delete-link "$EFFECTS"
  else
    assert_refused "$result"
  fi
)

check_peer_cleanup() (
  BACKEND=$1 HONK_STATUS=1 PEER=$2 DAED_GUARD_CLEANUP=post-exit
  reset_io
  load_init
  result=0
  if [ "$BACKEND" = dae ]; then
    stop_service 2> "$ERRORS" || result=$?
  else
    daed_cleanup_runtime 2> "$ERRORS" || result=$?
  fi
  assert_refused "$result"
)

router_stop() {
  # rc.common ignores stop_service's status, then returns service_stopped's.
  stop_service
  procd_kill "$BACKEND"
  if declare -F service_stopped >/dev/null; then service_stopped; fi
}

check_stop_dispatch() (
  BACKEND=$1 HONK_STATUS=$2 PEER=none
  reset_io
  load_init
  procd_kill() { [ "$1" = "$BACKEND" ]; }
  result=0
  router_stop 2> "$ERRORS" || result=$?
  if [ "$HONK_STATUS" = 1 ]; then
    [ "$result" = 0 ] || { cat "$ERRORS"; return 1; }
  else
    assert_refused "$result"
  fi
)

check_honk_stop() (
  HONK_STATUS=1 PEER=$1
  reset_io
  source "$HONK_DIR/honk/files/lifecycle.sh"
  ubus() { printf '{}\n'; }
  jsonfilter() { cat >/dev/null; }
  sed() {
    if [ "${!#}" = /etc/honk/system.dae ]; then
      printf "127.0.0.1:9527\n"
    else
      command sed "$@"
    fi
  }
  result=0
  honk_lifecycle_stop 1 2> "$ERRORS" || result=$?
  assert_refused "$result" || return 1
  grep -q 'resources did not drain' "$ERRORS"
)

passed=0
failed=0
run_case() {
  if ( "$@" ); then
    printf 'PASS %s\n' "$*"
    passed=$((passed + 1))
  else
    printf 'FAIL %s\n' "$*"
    failed=$((failed + 1))
  fi
}

for backend in dae daed; do
  for probe_status in 0 1 2 127; do
    run_case check_start "$backend" "$probe_status"
    run_case check_start_dispatch "$backend" "$probe_status"
    run_case check_stop_dispatch "$backend" "$probe_status"
  done
  for scenario in honk disabled instance-error; do
    run_case check_start_status_reset "$backend" "$scenario"
  done
done
for cleanup in dae:stop daed:start daed:post-exit; do
  for probe_status in 0 1 2 127; do
    run_case check_cleanup "$cleanup" "$probe_status"
  done
done
run_case check_peer_cleanup dae daed
run_case check_peer_cleanup daed dae
run_case check_honk_stop dae
run_case check_honk_stop daed
printf '%s passed; %s failed\n' "$passed" "$failed"
[ "$failed" = 0 ]
