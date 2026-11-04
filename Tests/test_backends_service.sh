#!/bin/bash
set -eu
SOURCE_DIR=${1:?pass the prepared openwrt-daede directory}

check_start() (
  local name=$1 active=$2 running=$3
  local opened=0
  # rc.common/procd and UCI are router-only I/O; all start logic is real.
  extra_command() { :; }
  config_load() { :; }
  config_get_bool() { printf -v "$1" '%s' 1; }
  config_get() { printf -v "$1" '%s' "$4"; }
  uci() { printf '%s\n' "$active"; }
  pidof() { [ "$1" = "$running" ]; }
  logger() { :; }
  procd_open_instance() { opened=1; }
  procd_set_param() { :; }
  procd_append_param() { :; }
  procd_close_instance() { :; }
  source "$SOURCE_DIR/daed/files/daed-cleanup.sh"
  source <(sed '\|^\. /usr/share/daed/cleanup.sh$|d' "$SOURCE_DIR/$name/files/$name.init")
  PROG=true
  if start_service; then
    [ "$name" = "$active" ] && [ "$running" = none ] && [ "$opened" = 1 ] || {
      echo "unsafe $name start: selected=$active other=$running"; exit 1;
    }
  else
    [ "$name" != "$active" ] || [ "$running" != none ] || {
      echo "valid $name start rejected"; exit 1;
    }
    [ "$opened" = 0 ] || { echo 'rejected start reached procd'; exit 1; }
  fi
)

for name in dae daed; do
  other=dae
  [ "$name" = dae ] && other=daed
  check_start "$name" "$other" none
  check_start "$name" "$name" "$other"
  check_start "$name" '' none
  check_start "$name" "$name" none
done
echo 'both service starts respect selection and reject a running peer'
