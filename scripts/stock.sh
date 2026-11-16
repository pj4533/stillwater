#!/bin/sh
# Safe manual return. Keeps default boot preference unless --disable is given.
set -eu
APP=/data/push-ambient
if [ "${1:-}" = --disable ]; then rm -f "$APP/enabled"; fi
if [ -f /run/stillwater-owned.json ]; then
  # Supervisor shutdown suppresses its fallback; helper confirms both owners dead.
  /usr/bin/python3 "$APP/scripts/process.py" stop-service
elif [ -f "$APP/ready" ]; then
  child=$(cat "$APP/ready")
  if start=$(/usr/bin/python3 "$APP/scripts/process.py" identity "$child"); then
    /usr/bin/python3 "$APP/scripts/process.py" stop "$child" "$start"
  fi
  rm -f "$APP/ready"
fi
"$APP/recovery/push3.stock" start
