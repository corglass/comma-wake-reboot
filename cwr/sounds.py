"""Playback via aplay (same ALSA output soundd uses). Spoken clips live in sounds/*.wav
(48 kHz 16-bit mono, generated offline with piper TTS, see sounds/README.md); tones are the fallback."""
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

TONES = {"chime": [660, 880, 1320], "cancel": [880, 440], "refuse": [300, 300, 300], "ok": [1320]}
# spoken clip -> fallback tone
CLIPS = {"prompt_repeat": "chime", "cancelled": "cancel", "refused": "refuse",
         "restarting": "ok", "dryrun": "ok"}

def resolve(name, sounds_dir):
    if name in CLIPS:
        p = os.path.join(sounds_dir, f"{name}.wav")
        if os.path.exists(p):
            return p
        name = CLIPS[name]
    p = os.path.join(tempfile.gettempdir(), f"cwr_{name}.wav")
    if not os.path.exists(p):
        write_wav(p, *tone(TONES[name]))
    return p

def play(name, device=None, sounds_dir=None):
    """Blocking: returns when playback has finished."""
    sounds_dir = sounds_dir or os.path.join(os.environ.get("CWR_DIR", "/data/comma-wake-reboot"), "sounds")
    path = resolve(name, sounds_dir)
    cmd = ["aplay", "-q"] + (["-D", device] if device else []) + [path]
    try:
        subprocess.run(cmd, timeout=10, check=False)
    except Exception:
        pass
