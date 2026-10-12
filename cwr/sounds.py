"""Short feedback tones generated with numpy (if available) and played with aplay."""
import os, subprocess, tempfile, wave

TONES = {"ok": [660, 880, 1320], "refuse": [300, 300, 300]}

def _write(path, freqs, dur=0.15, sr=48000, vol=0.5):
    import math
    frames = bytearray()
    for f in freqs:
        n = int(sr * dur)
        for i in range(n):
            t = i / sr
            env = min(1.0, min(t, dur - t) * 40)
            frames += int(math.sin(2 * math.pi * f * t) * env * vol * 32767).to_bytes(2, "little", signed=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(bytes(frames))

# Spoken clips kept in sounds/ (piper TTS); tones are the fallback.
CLIPS = {"restarting": "ok", "refused": "refuse"}

def path_for(name, sounds_dir=None):
    if name in CLIPS:
        d = sounds_dir or os.path.join(os.environ.get("CWR_DIR", "/data/comma-wake-reboot"), "sounds")
        c = os.path.join(d, f"{name}.wav")
        if os.path.exists(c):
            return c
        name = CLIPS[name]
    p = os.path.join(tempfile.gettempdir(), f"cwr_{name}.wav")
    if not os.path.exists(p):
        _write(p, TONES[name])
    return p

def play(name, device=None):
    """Blocking: returns when playback has finished."""
    cmd = ["aplay", "-q"] + (["-D", device] if device else []) + [path_for(name)]
    try:
        subprocess.run(cmd, timeout=10, check=False)
    except Exception:
        pass
