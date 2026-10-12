#!/usr/bin/env bash
# comma-wake-reboot installer. Idempotent. Never touches /data/openpilot.
set -euo pipefail
REPO_URL="${CWR_REPO_URL:-https://github.com/corglass/comma-wake-reboot.git}"
DIR=/data/comma-wake-reboot
SVC=comma-wake-reboot.service
UNIT=/etc/systemd/system/$SVC
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO=sudo

echo "[cwr] installing to $DIR"
if [ -d "$DIR/.git" ]; then git -C "$DIR" pull --ff-only
else git clone --depth 1 "$REPO_URL" "$DIR"; fi
[ -f "$DIR/enabled" ] || echo 1 > "$DIR/enabled"

# Run on openpilot's own interpreter (/usr/local/venv on AGNOS) so cereal (capnp, zmq) imports.
# No extra Python packages are needed any more (touch input is parsed with the stdlib).
PY=python3; [ -x /usr/local/venv/bin/python ] && PY=/usr/local/venv/bin/python
PYPATH="$DIR:/data/openpilot:/data"

# Clean up the old voice version (models, pip deps, temp dirs, stale local settings).
rm -rf "$DIR/venv" "$DIR/pylib" "$DIR/models" "$DIR/.tmp" "$DIR/training" "$DIR/.reqs.txt"
rm -f /tmp/cwr_*.wav
if [ -f "$DIR/config.local.json" ]; then
  "$PY" - "$DIR/config.local.json" <<'PY' || true
import json, sys
p = sys.argv[1]
old = ("wake_model", "confirm_model", "wake_threshold", "confirm_threshold", "wake_patience", "confirm_patience",
       "vad_threshold", "noise_suppression", "confirm_mode", "echo_guard_s", "speak", "confirm_timeout_s",
       "audio_source", "alsa_device", "mic_gain", "confirm_arm_delay_s",
       "dry_run", "tap_count", "tap_window_s")  # install always leaves LIVE mode; old 5-tap count dropped
d = json.load(open(p))
json.dump({k: v for k, v in d.items() if k not in old}, open(p, "w"))
PY
fi
echo "[cwr] mode: LIVE (use 'cwr dry' to test without powering off)"

PYTHONPATH="$PYPATH" "$PY" -c "from openpilot.cereal import messaging" \
  && echo "[cwr] openpilot messaging OK" || echo "[cwr] WARN: cannot import cereal.messaging; see README troubleshooting"

# Touchscreen access: /dev/input/event* is normally root:input 0660. The unit adds the input group.
TOUCH=$(PYTHONPATH="$PYPATH" "$PY" -c "from cwr.touch import find_touch_device as f; r=f(); print(r[0] if r else '')" 2>/dev/null || true)
RUNAS=comma
if [ -n "$TOUCH" ]; then
  echo "[cwr] touchscreen: $TOUCH ($(stat -c '%U:%G %a' "$TOUCH"))"
  if [ "$(stat -c %G "$TOUCH")" != input ] && ! sudo -u comma test -r "$TOUCH" 2>/dev/null; then
    echo "[cwr] WARN: $TOUCH is not group 'input' and not readable by comma; running service as root"
    RUNAS=root
  fi
else
  echo "[cwr] WARN: no touchscreen found yet; service will keep retrying (see cwr log)"
fi

# AGNOS rootfs is read-only: remount briefly to write our unit only.
RO=0; if ! $SUDO test -w /etc/systemd/system; then RO=1; $SUDO mount -o remount,rw /; fi
$SUDO tee "$UNIT" >/dev/null <<UNIT
[Unit]
Description=comma-wake-reboot (5-tap clean power off)
After=network.target

[Service]
Type=simple
User=$RUNAS
SupplementaryGroups=input
WorkingDirectory=$DIR
Environment=PYTHONPATH=$PYPATH
Environment=CWR_DIR=$DIR
ExecStart=$PY -m cwr.main
Restart=on-failure
RestartSec=10
Nice=10

[Install]
WantedBy=multi-user.target
UNIT
$SUDO ln -sf "$DIR/bin/cwr" /usr/local/bin/cwr 2>/dev/null || true
# Enable at boot while / is still writable (AGNOS root is read-only).
# The service always starts at boot; the $DIR/enabled file decides whether it reacts to taps.
$SUDO systemctl daemon-reload
$SUDO systemctl enable "$SVC"
[ "$RO" = 1 ] && $SUDO mount -o remount,ro / || true

if [ "$(cat "$DIR/enabled")" = 0 ]; then echo "[cwr] Wake Reboot is OFF (cwr on to enable)"; $SUDO systemctl stop "$SVC" || true
else $SUDO systemctl restart "$SVC"; fi
rm -rf "$DIR/.tmp"
echo "[cwr] done. Status: systemctl status $SVC ; logs: journalctl -u $SVC -f"
