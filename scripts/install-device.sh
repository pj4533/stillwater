#!/bin/sh
# Runs ON PUSH as root after copying payload to /data/push-ambient.
# Does not stop an already running stock application.
set -eu
APP=/data/push-ambient
mkdir -p "$APP/recovery" "$APP/sessions"
if [ ! -f "$APP/recovery/push3.stock" ]; then
  cp -p /etc/init.d/push3 "$APP/recovery/push3.stock"
  sha256sum /etc/init.d/push3 > "$APP/recovery/original.sha256"
  ls -l /etc/rc0.d/*push3 /etc/rc1.d/*push3 /etc/rc2.d/*push3 /etc/rc3.d/*push3 /etc/rc5.d/*push3 /etc/rc6.d/*push3 > "$APP/recovery/runlevels.txt"
  cat /proc/sys/kernel/random/boot_id > "$APP/recovery/install-boot-id"
fi
chmod +x "$APP/recovery/push3.stock" "$APP/scripts/"*.sh
cp "$APP/scripts/push3.init" /etc/init.d/push3
chmod 755 /etc/init.d/push3
printf '%s\n' 'Boot selector installed. Enable only after direct app test and recovery test.'
