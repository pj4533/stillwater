#!/bin/sh
# Exec preserves the PID recorded by the init selector. No automatic stock path.
unset PYTHONHOME PYTHONPATH
exec /usr/bin/python3 /data/push-ambient/scripts/supervisor.py --home /data/push-ambient
