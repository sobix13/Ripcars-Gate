#!/usr/bin/env bash
set -Eeuo pipefail
if [ "$(id -u)" -ne 0 ]; then echo "Run with sudo." >&2; exit 1; fi
APP_ROOT=/opt/ripcars-gate
TARGET="$(cat "$APP_ROOT/previous-release")"
case "$TARGET" in /opt/ripcars-gate/releases/*) ;; *) echo "Invalid rollback path." >&2; exit 1;; esac
if [ ! -f "$TARGET/main.py" ]; then echo "Previous release not found." >&2; exit 1; fi
systemctl stop ripcars-gate
ln -s "$TARGET" "$APP_ROOT/current.rollback"
mv -Tf "$APP_ROOT/current.rollback" "$APP_ROOT/current"
install -m 644 "$TARGET/ripcars-gate.service" /etc/systemd/system/ripcars-gate.service
systemctl daemon-reload
systemctl start ripcars-gate
systemctl status ripcars-gate --no-pager
