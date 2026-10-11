#!/usr/bin/env bash
# Removes ONLY comma-wake-reboot files and unit. Sunnypilot untouched.
set -euo pipefail
DIR=/data/comma-wake-reboot; SVC=comma-wake-reboot.service; UNIT=/etc/systemd/system/$SVC
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO=sudo
$SUDO systemctl stop "$SVC" 2>/dev/null || true
RO=0; if ! $SUDO test -w /etc/systemd/system; then RO=1; $SUDO mount -o remount,rw /; fi
$SUDO systemctl disable "$SVC" 2>/dev/null || true
$SUDO rm -f "$UNIT"
if [ "$(readlink /usr/local/bin/cwr 2>/dev/null)" = "$DIR/bin/cwr" ]; then $SUDO rm -f /usr/local/bin/cwr; fi
[ "$RO" = 1 ] && $SUDO mount -o remount,ro / || true
$SUDO systemctl daemon-reload
case "$DIR" in /data/comma-wake-reboot) rm -rf "$DIR";; esac
rm -f /tmp/cwr_*.wav
echo "[cwr] uninstalled. If you applied patches/settings-toggle.patch, revert it (see README)."
