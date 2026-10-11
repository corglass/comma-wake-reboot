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

# Base on openpilot's own Python env (/usr/local/venv on AGNOS) so cereal's deps
# (capnp, zmq, numpy) are visible read-only through --system-site-packages.
BASEPY=python3; [ -x /usr/local/venv/bin/python ] && BASEPY=/usr/local/venv/bin/python
if [ -x "$DIR/venv/bin/python" ] && ! "$DIR/venv/bin/python" -c "import capnp" 2>/dev/null \
   && "$BASEPY" -c "import capnp" 2>/dev/null; then rm -rf "$DIR/venv"; fi
# A venv made from another venv doesn't inherit its packages, so also expose
# openpilot's site-packages explicitly on PYTHONPATH (read-only, appended last).
OP_SITE="$("$BASEPY" -c 'import sysconfig;print(sysconfig.get_paths()["purelib"])' 2>/dev/null || true)"
if [ ! -x "$DIR/venv/bin/pip" ]; then
  # AGNOS lacks ensurepip (python3-venv), so build the venv without pip and bootstrap it.
  # --system-site-packages reuses numpy/capnp/zmq from AGNOS (read-only).
  rm -rf "$DIR/venv"
  "$BASEPY" -m venv --system-site-packages --without-pip "$DIR/venv"
  curl -fsSL https://bootstrap.pypa.io/get-pip.py -o "$DIR/get-pip.py"
  "$DIR/venv/bin/python" "$DIR/get-pip.py" -q
  rm -f "$DIR/get-pip.py"
fi
"$DIR/venv/bin/pip" install -q --upgrade pip
"$DIR/venv/bin/pip" install -q -r "$DIR/requirements.txt"
"$DIR/venv/bin/pip" install -q --no-deps openwakeword==0.6.0

# Stand-in models (openWakeWord v0.5.1 release assets). Feature models are fetched too.
OWW=https://github.com/dscripka/openWakeWord/releases/download/v0.5.1
mkdir -p "$DIR/models"
for m in alexa_v0.1.onnx hey_jarvis_v0.1.onnx; do
  [ -s "$DIR/models/$m" ] || curl -fsSL -o "$DIR/models/$m" "$OWW/$m"
done
PYTHONPATH="/data/openpilot:$OP_SITE" "$DIR/venv/bin/python" -c "import cereal.messaging" \
  && echo "[cwr] openpilot messaging OK" || echo "[cwr] WARN: cannot import cereal.messaging; see README troubleshooting"
"$DIR/venv/bin/python" -c "import openwakeword.utils as u; u.download_models(model_names=['alexa','hey_jarvis'])" \
  || echo "[cwr] WARN: could not fetch openWakeWord feature/VAD models; service will retry at start"

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
Environment=PYTHONPATH=$DIR:/data/openpilot:$OP_SITE
Environment=CWR_DIR=$DIR
ExecStart=$DIR/venv/bin/python -m cwr.main
Restart=on-failure
RestartSec=10
Nice=10

[Install]
WantedBy=multi-user.target
UNIT
$SUDO ln -sf "$DIR/bin/cwr" /usr/local/bin/cwr 2>/dev/null || true
# Enable at boot while / is still writable (AGNOS root is read-only).
# The service always starts at boot; the $DIR/enabled file decides whether it listens.
$SUDO systemctl daemon-reload
$SUDO systemctl enable "$SVC"
[ "$RO" = 1 ] && $SUDO mount -o remount,ro / || true

if [ "$(cat "$DIR/enabled")" = 0 ]; then echo "[cwr] Wake Reboot is OFF (cwr on to enable)"; $SUDO systemctl stop "$SVC" || true
else $SUDO systemctl restart "$SVC"; fi
echo "[cwr] done. Status: systemctl status $SVC ; logs: journalctl -u $SVC -f"
