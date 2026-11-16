#!/bin/sh
# ON DEVICE: ask Live to quit via its own official updater quit path. This
# creates .reboot (not .shutdown), and does not itself reboot the machine.
set -eu
APP=/data/push-ambient
if [ -f /var/lib/push3.pid ] && kill -0 "$(cat /var/lib/push3.pid)" 2>/dev/null; then
  /opt/push3/reboot.sh
  count=0
  while pidof Live >/dev/null 2>&1 && [ "$count" -lt 20 ]; do sleep 1;count=$((count+1));done
  if pidof Live >/dev/null 2>&1; then
    echo 'Live did not quit gracefully; refusing takeover.' >&2
    exit 1
  fi
  # Launcher/Push UI have no musical state after Live has quit. SIGTERM first.
  kill -TERM "$(cat /var/lib/push3.pid)" 2>/dev/null || true
  killall -TERM Push3 2>/dev/null || true
  sleep 2
fi
if pidof Push3 >/dev/null 2>&1; then
  echo 'Push surface still owned; refusing takeover.' >&2
  exit 1
fi
# Remove the one-time updater quit marker before any later stock start.
rm -f /data/settings/.reboot
touch "$APP/enabled"
/etc/init.d/push3 start
