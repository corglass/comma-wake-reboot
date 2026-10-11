# comma-wake-reboot

Voice-confirmed **clean power off** for a comma 4 running sunnypilot. Target phrases are **"reboot comma"**
then **"confirm"**. **Until those custom models are trained, the defaults are openWakeWord's built-in
stand-ins: say "alexa" (wake), hear a chime, then say "hey jarvis" (confirm) within 5 s.**
Then and the device powers off exactly like *Settings > Device > Power Off*.
When the car next powers the device, it boots back up.

> **DISCLAIMER: untested on real hardware.** Logic is unit-tested on a PC; audio, cereal and shutdown
> paths have not been run on a comma 4. Use at your own risk.

## Why dry_run is ON by default
`"dry_run": true` ships enabled: detections, chimes and guard decisions are logged (`journalctl -u
comma-wake-reboot -f`) but **the device never powers off**. Reasons: (1) the stand-in words "alexa"/"hey jarvis"
are common in speech, podcasts and other assistants, so false activations are expected; (2) nothing here has been
validated on comma 4 hardware (mic path, speaker, cereal, Params). Watch the log for a few drives/days, tune
thresholds, then set `"dry_run": false` and `sudo systemctl restart comma-wake-reboot`.
> Not affiliated with comma.ai or sunnypilot.

## What it does / how it works
1. Reads mic audio from cereal `rawAudioData` (16 kHz int16, published by `micd`) — no second mic
   open, no contention. Fallback: shared ALSA capture via PortAudio (`alsa_device`, e.g. a `dsnoop` PCM).
2. openWakeWord (ONNX backend) scores every 80 ms frame with two models (default stand-ins `alexa_v0.1`,
   `hey_jarvis_v0.1`, downloaded by the installer). Detection hardening:
   Silero **VAD gate** (`vad_threshold` 0.5: no score unless speech is present), **per-model thresholds**
   (0.6 wake / 0.7 confirm, clamped to 0.3–0.99), **patience** = 3 consecutive frames above threshold
   (~240 ms), model/buffer **reset** on every state change, **confirm arm delay** 0.8 s (chime/echo and the
   same utterance can't confirm), optional **Speex noise suppression**, and openWakeWord **custom verifier
   models** are supported upstream for speaker-specific filtering (documented, not wired in by default).
3. State machine: IDLE → wake ≥ threshold + guard OK → chime → CONFIRMING (5 s) → `confirm` ≥ threshold
   + guard re-check → shutdown. Timeout → cancel tone; refusal → low triple tone. 30 s cooldown after any trigger.
4. Shutdown writes Params `DoShutdown=True` — the same thing the Power Off button does:
   `openpilot/selfdrive/ui/layouts/settings/device.py` (`self._params.put_bool("DoShutdown", True)`),
   acted on by `openpilot/system/manager/manager.py` (`elif params.get_bool("DoShutdown"): HARDWARE.shutdown()`),
   verified at commaai/openpilot `b9c815d`. No power yank. Sunnypilot inherits this from upstream (verify on your branch).

## Safety features
- **Hard cap 20 km/h** on `carState.vEgo`: config may lower it, values above 20 are clamped to 20.
- **Blocks when onroad** (`deviceState.started`) and when openpilot is engaged (`selfdriveState.enabled`).
- **Standstill required** (default): fresh `carState` must show vEgo ≤ 1 km/h and `standstill` true.
- **Fails safe**: missing/stale `deviceState`, or stale speed while onroad ⇒ refuse.
- Two-step voice confirmation, 5 s timeout, guard re-checked right before shutdown, cooldown.
- If the Params write fails it does **not** force a power off.

## Requirements
comma 4 (AGNOS) with sunnypilot at `/data/openpilot`, SSH access, internet for install.
Stand-in models download automatically. For the real phrases, train `models/reboot_comma.onnx` and
`models/confirm.onnx` (openWakeWord ships none) — see [training/README.md](training/README.md).

## Install (one line over SSH)
```
curl -fsSL https://raw.githubusercontent.com/corglass/comma-wake-reboot/main/install.sh | bash
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
  and starts / stops the service. The unit stays enabled at boot (AGNOS root is read-only), and the daemon idles when the file is `0`. **This is the supported approach.**
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
curl -fsSL https://raw.githubusercontent.com/corglass/comma-wake-reboot/main/uninstall.sh | bash
```
Removes only the service, the `cwr` symlink, and `/data/comma-wake-reboot`. Sunnypilot is untouched
(revert the optional patch yourself if you applied it).

## Configuration (`/data/comma-wake-reboot/config.json`)
| key | default | meaning |
|---|---|---|
| wake_model / confirm_model | models/alexa_v0.1.onnx / models/hey_jarvis_v0.1.onnx | stand-ins; set to models/reboot_comma.onnx / models/confirm.onnx once trained |
| wake_threshold / confirm_threshold | 0.6 / 0.7 | per-model score cutoff (clamped 0.3–0.99) |
| wake_patience / confirm_patience | 3 / 3 | consecutive 80 ms frames required |
| vad_threshold | 0.5 | Silero VAD gate, 0 disables |
| noise_suppression | false | Speex NS (needs `speexdsp-ns`, may not exist for aarch64) |
| confirm_arm_delay_s | 0.8 | ignore confirm right after the chime |
| require_standstill / standstill_max_kph | true / 1.0 | require stopped car |
| speed_limit_kph | 20 | max speed; clamped to ≤ 20 |
| confirm_timeout_s | 5 | window to say "confirm" |
| cooldown_s | 30 | ignore wake after a trigger |
| speed_stale_s | 1.0 | carState age considered stale |
| block_if_onroad | true | refuse whenever onroad |
| audio_source | auto | auto / cereal / alsa |
| alsa_device / playback_device | null | PortAudio input / `aplay -D` output (null = default, same speaker soundd uses) |
| dry_run | **true** | log instead of shutting down (see above) |

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

## Research & sources
- openWakeWord README (VAD, Speex NS, verifier models, training): https://github.com/dscripka/openWakeWord
- `Model` args `vad_threshold`, `enable_speex_noise_suppression`, `custom_verifier_models`; `predict(patience=, threshold=, debounce_time=)`: https://github.com/dscripka/openWakeWord/blob/main/openwakeword/model.py
- Custom verifier models: https://github.com/dscripka/openWakeWord/blob/main/docs/custom_verifier_models.md
- Pre-trained model list (no reboot/confirm): https://github.com/dscripka/openWakeWord/releases/tag/v0.5.1
- Training notebook: https://github.com/dscripka/openWakeWord/blob/main/notebooks/automatic_model_training.ipynb
- comma's voice-entry bounty (local, fast wake word; must work onroad without lagging openpilot): https://github.com/commaai/openpilot/issues/30884 ; Porcupine demo on comma 3: https://github.com/commaai/openpilot/pull/31010
- microWakeWord / ESPHome (probability cutoff + sliding-window averaging, VAD gate) — the inspiration for patience frames: https://esphome.io/components/micro_wake_word/ , https://github.com/kahrendt/microWakeWord
- openpilot sources verified at `b9c815d`: `openpilot/system/micd.py` (rawAudioData 16 kHz int16),
  `openpilot/cereal/services.py`, `openpilot/selfdrive/ui/layouts/settings/device.py`, `openpilot/system/manager/manager.py`.

Not chosen: Porcupine (needs per-user AccessKey, proprietary models), microWakeWord (targets ESP32 TFLite-micro),
Snowboy (discontinued).

## Documented decisions
openWakeWord only (Porcupine dropped per spec), installed `--no-deps` with the ONNX backend because its
Linux `tflite-runtime` pin has no wheels for current Python (verified on the box; ONNX + VAD load and predict fine); cereal audio preferred over opening ALSA; Params
`DoShutdown` over `halt`; venv with `--system-site-packages`; service runs as user `comma`
(Params dir is writable by it); manual fallback if Params fails: `sudo systemctl poweroff` (not automatic).

## Development
`python3 -m unittest discover -s tests -t .` · `shellcheck *.sh bin/cwr training/*.sh`

MIT licensed. See CONTRIBUTING.md.

### Audio while parked (offroad)
sunnypilot only runs `micd` while the car is on. In `audio_source: "auto"` the service uses micd's stream when micd is running, and otherwise captures the mic directly with `arecord -D plughw:0,0` (comma 4: card 0 `sdm845-tavil-snd-card`, device 0). It checks every 0.5 s and releases the mic as soon as micd starts, so micd can take it when you start the car. Override the device with `alsa_device`.
