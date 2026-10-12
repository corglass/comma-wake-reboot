# comma-wake-reboot

**Tap the comma 4 screen 5 times quickly to cleanly power it off** while parked — the same power-off as
*Settings > Device > Power Off*. When the car next powers the device, it boots back up.
Runs as its own service alongside sunnypilot and never modifies sunnypilot.

> **DISCLAIMER:** the touch reader, feedback and guard are unit-tested on a PC with synthetic kernel events;
> the tap trigger has not yet been verified on comma 4 hardware. Use `cwr dry` first. Not affiliated with
> comma.ai or sunnypilot.

## How it works
1. Finds the touchscreen under `/sys/class/input/event*` (the first device whose ABS capability bitmap has
   `ABS_MT_POSITION_X`) and opens `/dev/input/eventN` **read-only, without EVIOCGRAB**, so the sunnypilot UI
   still receives every touch. `struct input_event` is parsed with Python's `struct` — no extra packages.
2. A *tap* = finger down→up within 0.4 s and moved ≤ 60 touch units. Touch-down is `BTN_TOUCH 1` (or a new
   `ABS_MT_TRACKING_ID ≥ 0` if the panel has no BTN_TOUCH). Long presses and swipes don't count and reset
   the sequence. **5 taps, ≤ 0.6 s apart, within 2.5 s** trigger. Kernel event timestamps are used.
3. Flow: **5th tap → immediate confirmation** (chime + brief screen-brightness flash) → **guard** → spoken **"Restarting"** (played to the end) → **guard re-check** → Params
   `DoShutdown=True` → clean power off. Refused → spoken "Can't restart while driving" (tone fallback).
   30 s cooldown after any trigger.
4. Power off path (verified in commaai/openpilot `b9c815d`): `openpilot/selfdrive/ui/layouts/settings/device.py`
   sets `DoShutdown`; `openpilot/system/manager/manager.py` sees it, stops processes and calls
   `HARDWARE.shutdown()`. No power yank. Sunnypilot inherits this from upstream (verify on your branch).

### Feedback choices
- **No haptics** (not used).
- **Visual:** two quick pulses (~0.5 s total) of `/sys/class/backlight/panel0-backlight/brightness` — the
  node openpilot's `HARDWARE.set_screen_brightness` writes — then the previous value is restored. It is too
  short to fight the UI's brightness control. Skipped silently if not writable (`screen_pulse: false` disables).
- **Audio:** chime (generated tone), `sounds/restarting.wav` and `sounds/refused.wav` (piper TTS
  en_US-lessac-medium, 48 kHz mono), played with `aplay`.

## ⚠ Your taps also reach the sunnypilot UI
The service only listens; it cannot stop the UI from handling the same taps. In openpilot's comma 4 ("mici")
UI (`openpilot/selfdrive/ui/mici/layouts/home.py`, `_handle_mouse_release`), **a tap on the offroad home
screen opens Settings** (or the alerts list when tapping the right edge while alerts exist), and a **long
press toggles Experimental Mode** (long presses don't count as taps here, but avoid them). So the first tap
opens Settings and the next four land on whatever is under your finger there. Advice:
- Run `cwr dry` and try it once to see where your taps land on *your* sunnypilot version.
- Tap one spot that is not a button/toggle in the screen you end up on (e.g. a title/blank area).
- The guard blocks all of this while onroad, so the driving UI is never involved in a real power-off.

## Safety
- **Hard cap 20 km/h** on `carState.vEgo` (config may lower, never raise).
- **Standstill required** (vEgo ≤ 1 km/h and `carState.standstill`).
- **Blocked when onroad** (`deviceState.started`) or engaged (`selfdriveState.enabled`).
- **Fails safe** on missing/stale `deviceState` or stale speed.
- **Re-checked** after "Restarting" plays, right before `DoShutdown`.
- 30 s cooldown (min 5 s); tap_count min 3; if the Params write fails it does not force a power off.

## Install / update (SSH)
```
curl -fsSL https://raw.githubusercontent.com/corglass/comma-wake-reboot/main/install.sh | bash
```
Installs into `/data/comma-wake-reboot` (git clone), writes `/etc/systemd/system/comma-wake-reboot.service`
(briefly remounting AGNOS's read-only root), enables and starts it. Runs on openpilot's Python
(`/usr/local/venv/bin/python`) for cereal; no pip packages. Idempotent. On upgrade from the voice version it
deletes `pylib/`, `models/`, `.tmp/`, `training/`, cached tones and stale voice keys in `config.local.json`.
**AGNOS updates may wipe the unit — rerun the installer.**

Touch permissions: `/dev/input/event*` is normally `root:input 0660`; the unit adds
`SupplementaryGroups=input` and runs as `comma`. If the installer finds the touchscreen isn't readable that
way it writes `User=root` instead and says so.

## Status, control
```
systemctl status comma-wake-reboot
cwr status
cwr log
cwr on | cwr off
cwr live | cwr dry
```
`on/off` writes `/data/comma-wake-reboot/enabled` (persists; daemon idles when `0`). `live/dry` sets
`dry_run` in untracked `config.local.json` (survives updates). Default is **live**.

Optional Settings toggle (modifies your fork; not applied by install.sh): `patches/settings-toggle.patch` adds
"Tap Reboot" to Settings > Device, flipping the state file. Made against commaai/openpilot `b9c815d` (old
tici layout); sunnypilot's UI may differ.
```
cd /data/openpilot && git apply --check /data/comma-wake-reboot/patches/settings-toggle.patch && git apply /data/comma-wake-reboot/patches/settings-toggle.patch
# tree with selfdrive/ at the root: add -p2.  Revert: git apply -R [-p2] <patch>
```
A separate on-screen overlay app is not included: the UI renders fullscreen via raylib/EGL on DRM with no
compositor, so a second GUI process can't safely coexist.

## Uninstall
```
curl -fsSL https://raw.githubusercontent.com/corglass/comma-wake-reboot/main/uninstall.sh | bash
```
Removes only the service, the `cwr` symlink and `/data/comma-wake-reboot`.

## Configuration (`config.json`; personal overrides in `config.local.json`)
| key | default | meaning |
|---|---|---|
| tap_count | 5 | taps needed (min 3) |
| tap_window_s | 2.5 | all taps within this (1–5) |
| tap_max_gap_s | 0.6 | max gap between taps (0.2–1.5) |
| tap_max_press_s | 0.4 | longer presses don't count |
| tap_max_move | 60 | touch units; more = swipe, doesn't count |
| touch_device | null | force e.g. `/dev/input/event2`; null = auto-detect |
| speed_limit_kph | 20 | clamped ≤ 20 |
| require_standstill / standstill_max_kph | true / 1.0 | |
| block_if_onroad | true | |
| speed_stale_s | 1.0 | |
| cooldown_s | 30 | |
| sounds / screen_pulse | true | feedback toggles |
| playback_device | null | `aplay -D` value |
| dry_run | false | `cwr dry` / `cwr live` |
| debug | true | heartbeat every 10 s |

Restart after edits: `sudo systemctl restart comma-wake-reboot`.

## Troubleshooting
- **Taps not detected:** `cwr log`. At start it logs `touch device: /dev/input/eventN (name)`; the heartbeat
  shows `taps_total` (every qualifying tap) and `in_sequence`. If `taps_total` doesn't grow, tap faster/shorter,
  or raise `tap_max_press_s` / `tap_max_move`. If `cannot open touchscreen` appears: check
  `ls -l /dev/input/` and `cat /sys/class/input/event*/device/name`, set `touch_device`, and rerun the
  installer (it switches to root if the device isn't group `input`).
- **Wrong device picked:** set `touch_device` explicitly.
- **Refused:** the log says why (onroad, speed, stale data, not at standstill). Fails safe by design.
- **No sound / no pulse:** `aplay /data/comma-wake-reboot/sounds/restarting.wav`; backlight pulse needs write
  access to `/sys/class/backlight/panel0-backlight/brightness`.

## Decisions
Voice trigger removed (unreliable in-car, heavy deps). evdev read without grab so the UI is unaffected; no
patch to sunnypilot required. Params `DoShutdown` rather than `halt`. Manual fallback if Params fails:
`sudo systemctl poweroff` (never automatic).

## Development
`python3 -m unittest discover -s tests -t .` · `shellcheck *.sh bin/cwr`

MIT licensed. See CONTRIBUTING.md.
