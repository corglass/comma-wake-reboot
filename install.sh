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

# Run on openpilot's own interpreter (/usr/local/venv on AGNOS) so cereal's deps
# (capnp, zmq, numpy) are available. Our extra packages go into $DIR/pylib via
# pip --target, so openpilot's environment is never modified.
PY=python3; [ -x /usr/local/venv/bin/python ] && PY=/usr/local/venv/bin/python
LIB="$DIR/pylib"
rm -rf "$DIR/venv"
mkdir -p "$LIB"
"$PY" -m pip --version >/dev/null 2>&1 || { echo "[cwr] ERROR: $PY has no pip"; exit 1; }
# Skip packages openpilot already provides (e.g. numpy) so we never shadow its versions.
REQS="$DIR/.reqs.txt"; : > "$REQS"
while read -r req; do
  name="${req%%[<>=!~ ]*}"; [ -z "$name" ] && continue; case "$name" in \#*) continue;; esac
  "$PY" -c "import importlib.util,sys;sys.exit(0 if importlib.util.find_spec('${name//-/_}') else 1)" 2>/dev/null || echo "$req" >> "$REQS"
done < "$DIR/requirements.txt"
[ -s "$REQS" ] && "$PY" -m pip install -q --target "$LIB" --upgrade -r "$REQS"
rm -f "$REQS"
"$PY" -m pip install -q --target "$LIB" --upgrade --no-deps openwakeword==0.6.0
PYPATH="$DIR:$LIB:/data/openpilot"

# Stand-in models (openWakeWord v0.5.1 release assets). Feature models are fetched too.
OWW=https://github.com/dscripka/openWakeWord/releases/download/v0.5.1
mkdir -p "$DIR/models"
for m in alexa_v0.1.onnx hey_jarvis_v0.1.onnx; do
  [ -s "$DIR/models/$m" ] || curl -fsSL -o "$DIR/models/$m" "$OWW/$m"
done
PYTHONPATH="$PYPATH" "$PY" -c "import cereal.messaging" \
  && echo "[cwr] openpilot messaging OK" || echo "[cwr] WARN: cannot import cereal.messaging; see README troubleshooting"
PYTHONPATH="$PYPATH" "$PY" -c "import openwakeword.utils as u; u.download_models(model_names=['alexa','hey_jarvis'])" \
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
# The service always starts at boot; the $DIR/enabled file decides whether it listens.
$SUDO systemctl daemon-reload
$SUDO systemctl enable "$SVC"
[ "$RO" = 1 ] && $SUDO mount -o remount,ro / || true

if [ "$(cat "$DIR/enabled")" = 0 ]; then echo "[cwr] Wake Reboot is OFF (cwr on to enable)"; $SUDO systemctl stop "$SVC" || true
else $SUDO systemctl restart "$SVC"; fi
echo "[cwr] done. Status: systemctl status $SVC ; logs: journalctl -u $SVC -f"
