"""Config loading. Speed limit is HARD-CAPPED at 20 km/h: config may lower it, never raise it."""
import json, os

HARD_SPEED_CAP_KPH = 20.0
INSTALL_DIR = os.environ.get("CWR_DIR", "/data/comma-wake-reboot")

DEFAULTS = {
    "tap_count": 3,              # taps needed after the swipe (2-10)
    "arm_s": 5.0,                # after a valid swipe, taps must finish within this (2-15)
    "swipe_axis": "any",         # "x", "y" or "any" (dominant axis); touch axes may be rotated vs display
    "swipe_direction": "any",    # "any", "left"/"up" (negative), "right"/"down" (positive), raw touch coords
    "swipe_min_frac": 0.25,      # min travel as fraction of the touch axis range (EVIOCGABS)
    "swipe_min_units": 150,      # fallback min travel if the axis range can't be read
    "swipe_max_s": 0.8,          # swipe must finish within this
    "swipe_max_off_ratio": 0.5,  # sideways travel <= this * main travel
    "tap_max_gap_s": 0.6,        # max gap between consecutive taps
    "tap_max_press_s": 0.4,      # longer presses don't count (and reset the sequence)
    "tap_max_move": 60,          # touch units; drags/swipes don't count
    "touch_device": None,        # e.g. "/dev/input/event2"; None = auto-detect
    "require_standstill": True,
    "standstill_max_kph": 1.0,
    "speed_limit_kph": 20.0,
    "cooldown_s": 30.0,
    "speed_stale_s": 1.0,
    "block_if_onroad": True,
    "sounds": True,              # chime on accept, spoken "Restarting", refuse clip/tone
    "screen_pulse": True,        # brief backlight pulse on accept (restored immediately)
    "playback_device": None,     # aplay -D value; None = default
    "dry_run": False,
    "debug": True,               # heartbeat log every 10 s (touch device, tap counts)
}

VOICE_KEYS = ("wake_model", "confirm_model", "wake_threshold", "confirm_threshold", "wake_patience",
              "confirm_patience", "vad_threshold", "noise_suppression", "confirm_mode", "echo_guard_s",
              "speak", "confirm_timeout_s", "audio_source", "alsa_device", "mic_gain", "confirm_arm_delay_s")

def clamp_speed(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return HARD_SPEED_CAP_KPH
    if v != v or v < 0:
        return 0.0
    return min(v, HARD_SPEED_CAP_KPH)

def load(path=None):
    path = path or os.path.join(INSTALL_DIR, "config.json")
    cfg = dict(DEFAULTS)
    if os.path.exists(path):
        with open(path) as f:
            cfg.update(json.load(f))
    # Local overrides (untracked, survive git pull): config.local.json, written by `cwr live|dry`.
    local = os.path.join(os.path.dirname(path), "config.local.json")
    if os.path.exists(local):
        try:
            with open(local) as f:
                cfg.update(json.load(f))
        except (OSError, ValueError):
            pass
    cfg["speed_limit_kph"] = clamp_speed(cfg["speed_limit_kph"])
    cfg["standstill_max_kph"] = min(float(cfg["standstill_max_kph"]), cfg["speed_limit_kph"])
    for k in VOICE_KEYS:
        cfg.pop(k, None)
    cfg.pop("tap_window_s", None)
    cfg["tap_count"] = min(max(2, int(cfg["tap_count"])), 10)
    cfg["arm_s"] = min(max(float(cfg["arm_s"]), 2.0), 15.0)
    cfg["swipe_min_frac"] = min(max(float(cfg["swipe_min_frac"]), 0.05), 0.9)
    cfg["swipe_max_s"] = min(max(float(cfg["swipe_max_s"]), 0.2), 2.0)
    if cfg["swipe_axis"] not in ("x", "y", "any"): cfg["swipe_axis"] = "any"
    if cfg["swipe_direction"] not in ("any", "left", "right", "up", "down"): cfg["swipe_direction"] = "any"
    cfg["tap_max_gap_s"] = min(max(float(cfg["tap_max_gap_s"]), 0.2), 1.5)
    cfg["tap_max_press_s"] = min(max(float(cfg["tap_max_press_s"]), 0.1), 1.0)
    cfg["cooldown_s"] = max(5.0, float(cfg["cooldown_s"]))
    return cfg

def enabled_path():
    return os.path.join(INSTALL_DIR, "enabled")

def is_enabled():
    try:
        with open(enabled_path()) as f:
            return f.read().strip() not in ("0", "off", "false", "")
    except FileNotFoundError:
        return True
