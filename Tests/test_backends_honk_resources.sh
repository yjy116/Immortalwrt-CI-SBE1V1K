#!/bin/bash
set -eu
HONK_DIR=${1:?pass Honk source}
TEST_DIR=$(mktemp -d)
trap 'command rm -rf "$TEST_DIR"' EXIT
EFFECTS=$TEST_DIR/effects
ERRORS=$TEST_DIR/errors

check_reclaim() (
  PROBE=$1 PROBE_STATUS=$2 EXPECT_STATUS=$3
  # rc.common has no errexit: the library deliberately probes timeout (exit 124).
  source "$HONK_DIR/honk/files/lifecycle.sh" || return 1
  LINK=1 NETNS=1
  : > "$EFFECTS"
  : > "$ERRORS"
  pidof() {
    [ "$1" = "$PROBE" ] || return 1
    [ "$PROBE_STATUS" != 0 ] || echo 4243
    return "$PROBE_STATUS"
  }
  ip() {
    case "$*" in
      'link show dae0'|'link show dae0peer') [ "$LINK" = 1 ] ;;
      'link del dae0') LINK=0; echo delete-link >> "$EFFECTS" ;;
      'netns list') [ "$NETNS" = 0 ] || echo daens; return 0 ;;
      'netns del daens') NETNS=0; echo delete-netns >> "$EFFECTS" ;;
      *) echo "unexpected ip operation: $*" >&2; return 99 ;;
    esac
  }
  result=0
  honk_lifecycle_reclaim_resources 2> "$ERRORS" || result=$?
  [ "$result" = "$EXPECT_STATUS" ] || { echo 'unexpected reclaim status'; return 1; }
  if [ "$EXPECT_STATUS" = 0 ]; then
    [ "$LINK:$NETNS" = 0:0 ] || return 1
    printf 'delete-link\ndelete-netns\n' > "$TEST_DIR/expected"
    cmp "$TEST_DIR/expected" "$EFFECTS" || return 1
  else
    [ "$LINK:$NETNS" = 1:1 ] && [ ! -s "$EFFECTS" ] || return 1
    if [ "$PROBE" != honk-core ]; then
      grep -q 'refusing shared resource cleanup' "$ERRORS" || return 1
    fi
  fi
)

check_reclaim none 1 0
for peer in dae daed; do
  for status in 0 2 127; do check_reclaim "$peer" "$status" 1; done
done
check_reclaim honk-core 0 1
echo 'PASS: 8 resource-reclaim cases; free leftovers cleaned; live peers and probe errors preserve resources'
