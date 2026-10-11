"""Config loading. Speed limit is HARD-CAPPED at 20 km/h: config may lower it, never raise it."""
import json, os

HARD_SPEED_CAP_KPH = 20.0
INSTALL_DIR = os.environ.get("CWR_DIR", "/data/comma-wake-reboot")

DEFAULTS = {
    # TEMPORARY stand-ins (openWakeWord built-ins) until custom models are trained:
    "wake_model": "models/alexa_v0.1.onnx",          # say "alexa"  (stand-in for "reboot comma")
    "confirm_model": "models/hey_jarvis_v0.1.onnx",  # say "hey jarvis" (stand-in for "confirm")
    "wake_threshold": 0.45,
    "confirm_threshold": 0.3,
    "wake_patience": 2,          # consecutive 80 ms frames above threshold
    "confirm_patience": 1,
    "vad_threshold": 0.2,        # Silero VAD gate (0 disables)
    "noise_suppression": False,  # Speex NS (needs speexdsp-ns wheel)
    "confirm_mode": "repeat",    # repeat: say the wake word again | wakeword: use confirm_model
    "echo_guard_s": 0.5,         # ignore audio until the prompt finished + this
    "speak": True,               # spoken prompts from sounds/*.wav (False = tones only)
    "require_standstill": True,
    "standstill_max_kph": 1.0,
    "speed_limit_kph": 20.0,
    "confirm_timeout_s": 8.0,
    "cooldown_s": 30.0,
    "speed_stale_s": 1.0,
    "block_if_onroad": True,
    "audio_source": "auto",          # auto | cereal | alsa
    "alsa_device": None,             # e.g. "dsnoop:0" ; None = PortAudio default
    "playback_device": None,         # aplay -D value; None = default (same as soundd)
    "dry_run": True,
    "debug": True,               # log a heartbeat (audio level, peak scores) every 2 s
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
    for k in ("wake_threshold", "confirm_threshold"):
        cfg[k] = min(max(float(cfg[k]), 0.3), 0.99)   # never accept absurdly low thresholds
    for k in ("wake_patience", "confirm_patience"):
        cfg[k] = max(1, int(cfg[k]))
    if cfg["confirm_mode"] not in ("repeat", "wakeword"):
        cfg["confirm_mode"] = "repeat"
    cfg["echo_guard_s"] = max(0.3, float(cfg["echo_guard_s"]))
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
