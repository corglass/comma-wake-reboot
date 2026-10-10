"""Config loading. Speed limit is HARD-CAPPED at 20 km/h: config may lower it, never raise it."""
import json, os

HARD_SPEED_CAP_KPH = 20.0
INSTALL_DIR = os.environ.get("CWR_DIR", "/data/comma-wake-reboot")

DEFAULTS = {
    "wake_model": "models/reboot_comma.onnx",
    "confirm_model": "models/confirm.onnx",
    "wake_threshold": 0.6,
    "confirm_threshold": 0.6,
    "speed_limit_kph": 20.0,
    "confirm_timeout_s": 5.0,
    "cooldown_s": 30.0,
    "speed_stale_s": 1.0,
    "block_if_onroad": True,
    "audio_source": "auto",          # auto | cereal | alsa
    "alsa_device": None,             # e.g. "dsnoop:0" ; None = PortAudio default
    "playback_device": None,         # aplay -D value; None = default (same as soundd)
    "dry_run": False,
}

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
    cfg["speed_limit_kph"] = clamp_speed(cfg["speed_limit_kph"])
    for k in ("wake_model", "confirm_model"):
        if cfg[k] and not os.path.isabs(cfg[k]):
            cfg[k] = os.path.join(INSTALL_DIR, cfg[k])
    return cfg

def enabled_path():
    return os.path.join(INSTALL_DIR, "enabled")

def is_enabled():
    try:
        with open(enabled_path()) as f:
            return f.read().strip() not in ("0", "off", "false", "")
    except FileNotFoundError:
        return True
