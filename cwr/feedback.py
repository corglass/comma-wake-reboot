"""Best-effort non-audio confirmation, without touching sunnypilot.
- Haptic: only if a vibrator sysfs node exists and is writable (comma devices are not known to have one).
- Visual: brief backlight pulse on /sys/class/backlight/panel0-backlight (the node openpilot's
  HARDWARE.set_screen_brightness writes), then restore the previous value. ~0.5 s total, so it doesn't
  fight the UI's brightness control; the UI re-applies its own value on its next change anyway."""
import os, time

BL = "/sys/class/backlight/panel0-backlight"
VIBRATORS = ("/sys/class/leds/vibrator/activate", "/sys/class/timed_output/vibrator/enable")

def _read(p):
    with open(p) as f: return f.read().strip()

def _write(p, v):
    with open(p, "w") as f: f.write(str(v))

def haptic(ms=150, nodes=VIBRATORS):
    for n in nodes:
        if os.path.exists(n) and os.access(n, os.W_OK):
            try:
                if n.endswith("activate"):
                    d = os.path.dirname(n)
                    if os.path.exists(os.path.join(d, "duration")): _write(os.path.join(d, "duration"), ms)
                    _write(n, 1)
                else:
                    _write(n, ms)
                return n
            except OSError:
                pass
    return None

def pulse(bl=BL, times=2, on_s=0.12):
    try:
        cur, mx = int(_read(os.path.join(bl, "brightness"))), int(_read(os.path.join(bl, "max_brightness")))
    except (OSError, ValueError):
        return False
    hi, lo = mx, max(1, mx // 20)
    alt = lo if cur > mx // 2 else hi           # contrast against the current level
    try:
        for _ in range(times):
            _write(os.path.join(bl, "brightness"), alt); time.sleep(on_s)
            _write(os.path.join(bl, "brightness"), cur); time.sleep(on_s)
        return True
    except OSError:
        return False
    finally:
        try: _write(os.path.join(bl, "brightness"), cur)
        except OSError: pass
