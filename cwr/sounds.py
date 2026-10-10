import os, subprocess, tempfile, wave
import numpy as np

def tone(freqs, dur=0.18, sr=48000, vol=0.5):
    out = []
    for f in freqs:
        t = np.arange(int(sr * dur)) / sr
        env = np.minimum(1, np.minimum(t, dur - t) * 40)
        out.append(np.sin(2 * np.pi * f * t) * env * vol)
    return (np.concatenate(out) * 32767).astype(np.int16), sr

def write_wav(path, data, sr):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(data.tobytes())

SOUNDS = {"chime": [660, 880, 1320], "cancel": [880, 440], "refuse": [300, 300, 300], "ok": [1320]}

def play(name, device=None, cache=None):
    cache = cache or tempfile.gettempdir()
    path = os.path.join(cache, f"cwr_{name}.wav")
    if not os.path.exists(path):
        write_wav(path, *tone(SOUNDS[name]))
    cmd = ["aplay", "-q"] + (["-D", device] if device else []) + [path]
    try:
        subprocess.run(cmd, timeout=5, check=False)
    except Exception:
        try:
            import sounddevice as sd, soundfile  # noqa
        except Exception:
            pass
