# comma-wake-reboot

Voice-confirmed **clean power off** for a comma 4 running sunnypilot. Say **"reboot comma"**, hear a chime,
say **"confirm"** within 5 s, and the device powers off exactly like *Settings > Device > Power Off*.
When the car next powers the device, it boots back up.

> **DISCLAIMER: untested on real hardware.** Logic is unit-tested on a PC; audio, cereal and shutdown
> paths have not been run on a comma 4. Use at your own risk, start with `"dry_run": true`.
> Not affiliated with comma.ai or sunnypilot.

## What it does / how it works
1. Reads mic audio from cereal `rawAudioData` (16 kHz int16, published by `micd`) — no second mic
   open, no contention. Fallback: shared ALSA capture via PortAudio (`alsa_device`, e.g. a `dsnoop` PCM).
2. openWakeWord scores every 80 ms frame with two models: `reboot_comma` and `confirm`.
3. State machine: IDLE → wake ≥ threshold + guard OK → chime → CONFIRMING (5 s) → `confirm` ≥ threshold
   + guard re-check → shutdown. Timeout → cancel tone; refusal → low triple tone. 30 s cooldown after any trigger.
4. Shutdown writes Params `DoShutdown=True` — the same thing the Power Off button does:
   `openpilot/selfdrive/ui/layouts/settings/device.py` (`self._params.put_bool("DoShutdown", True)`),
   acted on by `openpilot/system/manager/manager.py` (`elif params.get_bool("DoShutdown"): HARDWARE.shutdown()`),
   verified at commaai/openpilot `b9c815d`. No power yank. Sunnypilot inherits this from upstream (verify on your branch).

## Safety features
- **Hard cap 20 km/h** on `carState.vEgo`: config may lower it, values above 20 are clamped to 20.
- **Blocks when onroad** (`deviceState.started`) and when openpilot is engaged (`selfdriveState.enabled`).
- **Fails safe**: missing/stale `deviceState`, or stale speed while onroad ⇒ refuse.
- Two-step voice confirmation, 5 s timeout, guard re-checked right before shutdown, cooldown.
- If the Params write fails it does **not** force a power off.

## Requirements
comma 4 (AGNOS) with sunnypilot at `/data/openpilot`, SSH access, internet for install.
**Trained models** `models/reboot_comma.onnx` and `models/confirm.onnx` — openWakeWord ships none for these
phrases; see [training/README.md](training/README.md). The service exits with a clear log message until they exist.

## Install (one line over SSH)
```
curl -fsSL https://raw.githubusercontent.com/OWNER/comma-wake-reboot/main/install.sh | bash
```
Installs into `/data/comma-wake-reboot` (git clone + Python venv), writes
`/etc/systemd/system/comma-wake-reboot.service`, enables and starts it. Idempotent: rerun to update.
AGNOS has a read-only rootfs, so the installer briefly remounts `/` rw to write the unit. **AGNOS updates
may wipe the unit — rerun the install line after updating.**

## Check status
```
systemctl status comma-wake-reboot
journalctl -u comma-wake-reboot -f
cwr status
```

## On/off toggle ("Wake Reboot")
- `cwr on` / `cwr off` / `cwr status` — writes `/data/comma-wake-reboot/enabled` (1/0, persists across reboots)
  and enables+starts / disables+stops the service. **This is the supported approach.**
- The daemon also re-reads `enabled` every loop and goes idle (closes mic) when it is `0`.
- **Optional Settings toggle (modifies your fork, not applied by install.sh):** `patches/settings-toggle.patch`
  adds a "Wake Reboot" toggle to Settings > Device that flips the state file (the daemon idles; it does not
  stop the service — UI has no root). Made against commaai/openpilot `b9c815d`; sunnypilot's UI may differ.
  ```
  cd /data/openpilot && git apply --check /data/comma-wake-reboot/patches/settings-toggle.patch && git apply /data/comma-wake-reboot/patches/settings-toggle.patch
  # paths are a/openpilot/selfdrive/...; if your tree is selfdrive/... at the root use: git apply -p2 ...
  # revert:  git apply -R [-p2] /data/comma-wake-reboot/patches/settings-toggle.patch   (or git checkout -- selfdrive/ui)
  ```
  Note: it will block `git pull` updates of sunnypilot until reverted.
- Separate on-screen overlay app: **not included.** The sunnypilot UI renders fullscreen directly via
  raylib/EGL on DRM (no compositor), so a second GUI process would have to fight it for the display and
  touch input — not safe to coexist. Voice on/off toggle: not included (would need another model and adds
  false-trigger surface).

## Uninstall (one line)
```
curl -fsSL https://raw.githubusercontent.com/OWNER/comma-wake-reboot/main/uninstall.sh | bash
```
Removes only the service, the `cwr` symlink, and `/data/comma-wake-reboot`. Sunnypilot is untouched
(revert the optional patch yourself if you applied it).

## Configuration (`/data/comma-wake-reboot/config.json`)
| key | default | meaning |
|---|---|---|
| wake_model / confirm_model | models/reboot_comma.onnx / models/confirm.onnx | openWakeWord ONNX models |
| wake_threshold / confirm_threshold | 0.6 | score 0–1; raise to reduce false triggers |
| speed_limit_kph | 20 | max speed; clamped to ≤ 20 |
| confirm_timeout_s | 5 | window to say "confirm" |
| cooldown_s | 30 | ignore wake after a trigger |
| speed_stale_s | 1.0 | carState age considered stale |
| block_if_onroad | true | refuse whenever onroad |
| audio_source | auto | auto / cereal / alsa |
| alsa_device / playback_device | null | PortAudio input / `aplay -D` output (null = default, same speaker soundd uses) |
| dry_run | false | log instead of shutting down |

Changing the phrase = train a new model and point `wake_model`/`confirm_model` at it. Restart after edits:
`sudo systemctl restart comma-wake-reboot`.

## Troubleshooting
- **False triggers:** raise thresholds (0.7–0.8), retrain with more negative phrases / higher
  `false_activation_penalty`, keep cooldown. Confirmation step + guard prevent a single false wake from acting.
- **No detections:** `journalctl -u comma-wake-reboot -f`; check the log says `audio: cereal rawAudioData`.
  If micd isn't publishing, set `"audio_source": "alsa"`; check `cat /proc/asound/cards`, `arecord -l`,
  `python -c "import sounddevice as s; print(s.query_devices())"`. Prefer a `dsnoop` device so micd keeps the mic.
- **No chime:** `aplay -l`; set `playback_device`; soundd may own the device exclusively — use a `dmix` PCM.
- **"missing model":** see training/README.md.
- **Refused: deviceState unavailable:** openpilot/manager not running; the guard fails safe by design.

## Documented decisions
openWakeWord only (Porcupine dropped per spec); cereal audio preferred over opening ALSA; Params
`DoShutdown` over `halt`; venv with `--system-site-packages`; service runs as user `comma`
(Params dir is writable by it); manual fallback if Params fails: `sudo systemctl poweroff` (not automatic).

## Development
`python3 -m unittest discover -s tests -t .` · `shellcheck *.sh bin/cwr training/*.sh`

MIT licensed. See CONTRIBUTING.md.
