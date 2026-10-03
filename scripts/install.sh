#!/usr/bin/env bash
# Installs Gate only. Does not install companion bots or touch another service.
set -Eeuo pipefail
if [ "$(id -u)" -ne 0 ]; then echo "Run with sudo." >&2; exit 1; fi
SOURCE_DIR="$(realpath "${1:-$(dirname "$0")/..}")"
if [ ! -f "$SOURCE_DIR/main.py" ] || [ ! -f "$SOURCE_DIR/VERSION" ]; then echo "Invalid release directory." >&2; exit 1; fi
APP_ROOT=/opt/ripcars-gate
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE_DIR="$APP_ROOT/releases/$(cat "$SOURCE_DIR/VERSION")-$STAMP"
if [ -e "$RELEASE_DIR" ]; then echo "Release directory already exists." >&2; exit 1; fi
command -v python3 >/dev/null
getent group ripcars-bots >/dev/null || groupadd --system ripcars-bots
id ripcarsgate >/dev/null 2>&1 || useradd --system --user-group --home-dir /var/lib/ripcars-gate --shell /usr/sbin/nologin ripcarsgate
usermod -aG ripcars-bots ripcarsgate
install -d -m 700 -o ripcarsgate -g ripcarsgate /var/lib/ripcars-gate
install -d -m 2770 -o root -g ripcars-bots /var/lib/ripcars-bots
install -d -m 755 "$RELEASE_DIR"
tar -C "$SOURCE_DIR" --exclude=.git --exclude=releases --exclude=.venv --exclude=.env --exclude=__pycache__ --exclude=.pytest_cache --exclude=data --exclude=backups --exclude=logs --exclude='*.sqlite*' --exclude='*.db*' -cf - . | tar -C "$RELEASE_DIR" -xf -
# No local state, token, or environment is copied into a release.
rm -rf "$RELEASE_DIR/.venv" "$RELEASE_DIR/data" "$RELEASE_DIR/backups"
rm -f "$RELEASE_DIR/.env"
python3 -m venv "$RELEASE_DIR/.venv"
"$RELEASE_DIR/.venv/bin/pip" install -r "$RELEASE_DIR/requirements.txt"
PYTHON_BIN="$RELEASE_DIR/.venv/bin/python" bash "$RELEASE_DIR/run_tests.sh"
chown -R root:root "$RELEASE_DIR"
chmod -R go-w "$RELEASE_DIR"
if [ ! -f /etc/ripcars-gate.env ]; then install -m 600 "$SOURCE_DIR/.env.example" /etc/ripcars-gate.env; fi
PREVIOUS="$(readlink -f "$APP_ROOT/current" 2>/dev/null || true)"
if [ -n "$PREVIOUS" ]; then printf '%s\n' "$PREVIOUS" > "$APP_ROOT/previous-release"; fi
ln -s "$RELEASE_DIR" "$APP_ROOT/current.next"
mv -Tf "$APP_ROOT/current.next" "$APP_ROOT/current"
install -m 644 "$RELEASE_DIR/ripcars-gate.service" /etc/systemd/system/ripcars-gate.service
systemctl daemon-reload
echo "Release installed: $RELEASE_DIR"
echo "Edit /etc/ripcars-gate.env, then start ripcars-gate. No other service was changed."
