# comma-wake-reboot

**Swipe across the comma 4 screen (to the alerts pane), then tap 3 times, to cleanly power it off** while parked — the same power-off as
*Settings > Device > Power Off*. When the car next powers the device, it boots back up.
Runs as its own service alongside sunnypilot and never modifies sunnypilot.

> **DISCLAIMER:** the touch reader, feedback and guard are unit-tested on a PC with synthetic kernel events;
> the swipe + tap trigger has not yet been verified on comma 4 hardware. Install leaves it LIVE; use `cwr dry` if you want to test without powering off. Not affiliated with
> comma.ai or sunnypilot.

## How it works
1. Finds the touchscreen under `/sys/class/input/event*` (the first device whose ABS capability bitmap has
   `ABS_MT_POSITION_X`) and opens `/dev/input/eventN` **read-only, without EVIOCGRAB**, so the sunnypilot UI
   still receives every touch. `struct input_event` is parsed with Python's `struct` — no extra packages.
2. **Gesture: one swipe, then 3 taps within 5 s.**
   - *Swipe* = one finger stroke that travels ≥ 25 % of the touch axis range (read via `EVIOCGABS`; fallback
     150 units), finishes within 0.8 s, and is mostly straight (sideways travel ≤ 0.5 × main travel). Logged
     as `swipe detected dx=… dy=…` with raw touch-unit deltas. A valid swipe **arms** for `arm_s` (5 s).
   - *Tap* = finger down→up within 0.4 s, moved ≤ 60 units, ≤ 0.6 s after the previous tap. Taps while not
     armed are ignored, so stray taps can never trigger. A non-qualifying drag disarms.
   - Default direction/axis is **any horizontal-or-vertical** stroke (`swipe_axis: any`,
     `swipe_direction: any`) because the panel's touch axes may be rotated relative to the display. Tune
     after reading `dx/dy` in `cwr log` (see Tuning).
3. Flow: **3rd tap → immediate confirmation** (chime + brief screen-brightness flash) → **guard** → spoken **"Restarting"** (played to the end) → **guard re-check** → Params
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

## Why swipe first (sunnypilot UI interaction)
The service only listens; the UI still gets every touch. Checked in commaai/openpilot master
(`selfdrive/ui/mici/layouts/main.py`, which sunnypilot's comma 4 UI is based on): the main screen is a
horizontal snapping `Scroller` with pages in this order: **alerts | home | onroad**. The alerts pane
(`MiciOffroadAlerts`) sits to the *left* of home, so a horizontal swipe on home (finger moving toward the
right edge, i.e. "going left" a page) brings up the alerts pane. A tap on home opens Settings
(`home.py`), which is why plain taps landed in menus.
On the alerts pane, taps on blank space do nothing. **Avoid tapping the alert cards:** the "Update
available" card reboots to install the update (`HARDWARE.reboot()`) and the pairing card opens pairing;
other cards have no action. Tap empty space (e.g. below the cards or the screen edge). With no alerts the
pane is empty, so any spot is fine. The guard blocks everything while onroad.

## Tuning the swipe
`cwr log` prints, for every stroke: `swipe detected dx=… dy=… dur=…s -> armed`, or
`drag dx=… dy=… not a swipe: <reason>`, then `tap 1/3`, `tap 2/3`, `tap sequence complete`, or
`disarmed: timeout`. At start it prints the touch ranges and the computed minimum swipe travel.
- To accept only the gesture you use, look at the sign of the big delta and set e.g.
  `"swipe_axis": "x", "swipe_direction": "right"` (or `"y"` / `"up"` etc. if the panel is rotated) in
  `config.local.json`. Directions refer to raw touch coordinates: left/up = negative, right/down = positive.
- "too short": lower `swipe_min_frac`. "too slow": raise `swipe_max_s`. "not straight": raise `swipe_max_off_ratio`.

## Safety
- **Hard cap 20 km/h** on `carState.vEgo` (config may lower, never raise).
- **Standstill required** (vEgo ≤ 1 km/h and `carState.standstill`).
- **Blocked when onroad** (`deviceState.started`) or engaged (`selfdriveState.enabled`).
- **Fails safe** on missing/stale `deviceState` or stale speed.
- **Re-checked** after "Restarting" plays, right before `DoShutdown`.
- 30 s cooldown (min 5 s); tap_count 2–10, taps only count after a swipe; if the Params write fails it does not force a power off.

## Install / update (SSH)
```
curl -fsSL https://raw.githubusercontent.com/corglass/comma-wake-reboot/main/install.sh | bash
```
Installs into `/data/comma-wake-reboot` (git clone), writes `/etc/systemd/system/comma-wake-reboot.service`
(briefly remounting AGNOS's read-only root), enables and starts it. Runs on openpilot's Python
(`/usr/local/venv/bin/python`) for cereal; no pip packages. Idempotent. On upgrade from the voice version it
deletes `pylib/`, `models/`, `.tmp/`, `training/`, cached tones and stale voice keys in `config.local.json`. Every install clears `dry_run` and old
`tap_count`/`tap_window_s` overrides from `config.local.json`, so it always ends in **LIVE** mode.
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
| tap_count | 3 | taps after the swipe (2–10) |
| arm_s | 5.0 | taps must finish this long after the swipe (2–15) |
| swipe_axis | any | `x`, `y` or `any` (raw touch axis) |
| swipe_direction | any | `any`, `left`/`up` (negative), `right`/`down` (positive) |
| swipe_min_frac | 0.25 | min travel, fraction of axis range |
| swipe_min_units | 150 | fallback min travel if range unreadable |
| swipe_max_s | 0.8 | max swipe duration |
| swipe_max_off_ratio | 0.5 | max sideways/main travel |
| tap_max_gap_s | 0.6 | max gap between taps (0.2–1.5) |
| tap_max_press_s | 0.4 | longer presses don't count |
| tap_max_move | 60 | touch units; more = a drag/swipe, not a tap |
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
- **Nothing happens:** `cwr log`. At start it logs `touch device: /dev/input/eventN (name)`. No `swipe
  detected` line → read the `drag … not a swipe: reason` line and tune (above). Swipe detected but taps not
  counted → tap faster/shorter, or raise `tap_max_press_s` / `tap_max_move`; `disarmed: timeout` → tap within 5 s.
  Heartbeat shows `taps_total` and `armed`. If `cannot open touchscreen` appears: check
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
