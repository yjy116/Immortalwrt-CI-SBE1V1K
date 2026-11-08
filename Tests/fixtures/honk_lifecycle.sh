# Sourced after the real lifecycle library. Only router I/O and clock boundaries
# are fixtures; restart, stop, drain, start and readiness validation stay upstream.
OLD_PID=4242
NEW_PID=4243
UNMANAGED_PID=4244

router_pid() {
  case "$ROUTER_STATE" in
    old) echo "$OLD_PID" ;;
    new) echo "$NEW_PID" ;;
    *) return 0 ;;
  esac
}

honk_lifecycle_managed_pid() { router_pid; }
honk_lifecycle_procd_pid() { router_pid; }
honk_lifecycle_procd_running() {
  case "$ROUTER_STATE" in old|new) echo true ;; *) echo false ;; esac
}
honk_lifecycle_starttime() {
  [ "$1" = "$(router_pid)" ] || return 1
  echo "$1"
}
honk_lifecycle_port_open() { return 1; }
honk_lifecycle_pause() { :; }
pidof() {
  case "$1" in
    dae|daed) return 1 ;;
    honk-core) ;;
    *) return 99 ;;
  esac
  case "$ROUTER_STATE" in
    old|new) router_pid ;;
    unmanaged) echo "$UNMANAGED_PID" ;;
    *) return 1 ;;
  esac
}
ip() {
  case "$*" in
    'link show dae0') [ "$LINK_DAE0" = 1 ] ;;
    'link show dae0peer') [ "$LINK_DAE0PEER" = 1 ] ;;
    'link del dae0') LINK_DAE0=0; echo 'delete-link dae0' >> "$TEST_DIR/effects" ;;
    'link del dae0peer') LINK_DAE0PEER=0; echo 'delete-link dae0peer' >> "$TEST_DIR/effects" ;;
    'netns list') [ "$NETNS_STATE" = 0 ] || echo daens; return 0 ;;
    'netns del daens') NETNS_STATE=0; echo 'delete-netns daens' >> "$TEST_DIR/effects" ;;
    *) echo "unexpected ip operation: $*" >&2; return 99 ;;
  esac
}
sleep() {
  [ "$1" = 1 ] || return 99
}

honk_core_ready_fixture() {
  local token hash
  read -r token hash < "$TEST_DIR/runtime/readiness"
  printf 'pid=%s\ntoken=%s\nconfig_hash=%s\napi_enabled=true\nclash_api_secret_set=false\n' \
    "$NEW_PID" "$token" "$hash" > "$TEST_DIR/runtime/core-ready-$token"
}

honk_init_fixture() {
  case "$1" in
    stop)
      echo stop >> "$TEST_DIR/effects"
      ROUTER_STATE=clear
      if [ "$scenario" = stop_failure ]; then ROUTER_STATE=unmanaged; fi ;;
    start)
      [ "$ROUTER_STATE:$LINK_DAE0:$LINK_DAE0PEER:$NETNS_STATE" = clear:0:0:0 ] || return 99
      [ "$scenario" != start_failure ] || return 1
      start
      grep -qx launch "$TEST_DIR/effects" || return 0
      ROUTER_STATE=new
      honk_core_ready_fixture ;;
    *) echo "unexpected init operation: $*" >&2; return 99 ;;
  esac
}
