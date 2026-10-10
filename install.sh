#!/usr/bin/env bash
# comma-wake-reboot installer. Idempotent. Never touches /data/openpilot.
set -euo pipefail
REPO_URL="${CWR_REPO_URL:-https://github.com/OWNER/comma-wake-reboot.git}"
DIR=/data/comma-wake-reboot
SVC=comma-wake-reboot.service
UNIT=/etc/systemd/system/$SVC
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO=sudo

echo "[cwr] installing to $DIR"
if [ -d "$DIR/.git" ]; then git -C "$DIR" pull --ff-only
else git clone --depth 1 "$REPO_URL" "$DIR"; fi
[ -f "$DIR/enabled" ] || echo 1 > "$DIR/enabled"

if [ ! -x "$DIR/venv/bin/python" ]; then
  # --system-site-packages so numpy/capnp/zmq from AGNOS are reused (read-only)
  python3 -m venv --system-site-packages "$DIR/venv"
fi
"$DIR/venv/bin/pip" install -q --upgrade pip
"$DIR/venv/bin/pip" install -q -r "$DIR/requirements.txt"

# AGNOS rootfs is read-only: remount briefly to write our unit only.
RO=0; if ! $SUDO test -w /etc/systemd/system; then RO=1; $SUDO mount -o remount,rw /; fi
$SUDO tee "$UNIT" >/dev/null <<UNIT
[Unit]
Description=comma-wake-reboot (voice-confirmed clean power off)
After=network.target

[Service]
Type=simple
User=comma
WorkingDirectory=$DIR
Environment=PYTHONPATH=$DIR:/data/openpilot
Environment=CWR_DIR=$DIR
ExecStart=$DIR/venv/bin/python -m cwr.main
Restart=on-failure
RestartSec=10
Nice=10

[Install]
WantedBy=multi-user.target
UNIT
$SUDO ln -sf "$DIR/bin/cwr" /usr/local/bin/cwr 2>/dev/null || true
[ "$RO" = 1 ] && $SUDO mount -o remount,ro / || true

$SUDO systemctl daemon-reload
if [ "$(cat "$DIR/enabled")" = 0 ]; then echo "[cwr] Wake Reboot is OFF; not starting (cwr on to enable)"
else $SUDO systemctl enable --now "$SVC"; $SUDO systemctl restart "$SVC"; fi
echo "[cwr] done. Status: systemctl status $SVC ; logs: journalctl -u $SVC -f"
