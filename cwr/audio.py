"""Audio input. Preferred: cereal 'rawAudioData' published by micd (16 kHz int16) - zero contention.
Fallback: shared ALSA capture via PortAudio (use a dsnoop device so micd keeps the mic)."""
import queue
import numpy as np

CHUNK = 1280  # 80 ms @16 kHz, openWakeWord frame size

class CerealAudio:
    def __init__(self):
        try:
            from cereal import messaging
        except ImportError:
            from openpilot.cereal import messaging
        self.sock = messaging.sub_sock("rawAudioData", conflate=False, timeout=200)
        self.messaging = messaging
        self.buf = np.zeros(0, dtype=np.int16)

    def read(self):
        while len(self.buf) < CHUNK:
            msgs = self.messaging.drain_sock(self.sock, wait_for_one=True)
            if not msgs:
                return None
            for m in msgs:
                self.buf = np.concatenate((self.buf, np.frombuffer(m.rawAudioData.data, dtype=np.int16)))
        out, self.buf = self.buf[:CHUNK], self.buf[CHUNK:]
        return out

class AlsaAudio:
    def __init__(self, device=None):
        import sounddevice as sd
        self.q = queue.Queue(maxsize=50)
        self.stream = sd.InputStream(device=device, channels=1, samplerate=16000, dtype="int16",
                                     blocksize=CHUNK, callback=lambda d, *_: self.q.put_nowait(d[:, 0].copy()))
        self.stream.start()

    def read(self):
        try:
            return self.q.get(timeout=1)
        except queue.Empty:
            return None

class ArecordAudio:
    """Direct capture with arecord (plughw resamples to 16 kHz mono). Only used while micd is NOT
    running (offroad), and released immediately when micd appears so it can take the mic."""
    def __init__(self, device="plughw:0,0"):
        import subprocess
        self.p = subprocess.Popen(["arecord", "-q", "-D", device, "-f", "S16_LE", "-r", "16000", "-c", "1",
                                   "-t", "raw"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def read(self):
        b = self.p.stdout.read(CHUNK * 2)
        if not b or len(b) < CHUNK * 2:
            return None
        return np.frombuffer(b, dtype=np.int16)

    def close(self):
        try:
            self.p.terminate(); self.p.wait(timeout=2)
        except Exception:
            try: self.p.kill()
            except Exception: pass

def micd_running():
    import subprocess
    return subprocess.run(["pgrep", "-f", "micd"], stdout=subprocess.DEVNULL).returncode == 0

class HybridAudio:
    """Prefer micd's cereal stream; when micd is not running (offroad), capture directly and hand the
    mic back the moment micd starts."""
    def __init__(self, cfg, log):
        self.log, self.dev = log, cfg.get("alsa_device") or "plughw:0,0"
        self.cereal = CerealAudio()
        self.direct, self.mode, self.check_t = None, None, 0.0

    def _set(self, mode):
        if mode == self.mode:
            return
        if self.direct is not None:
            self.direct.close(); self.direct = None
        if mode == "direct":
            self.direct = ArecordAudio(self.dev)
        self.mode = mode
        self.log(f"audio: {'micd stream' if mode == 'cereal' else 'direct ' + self.dev + ' (micd not running)'}")

    def read(self):
        import time
        now = time.monotonic()
        if now - self.check_t > 0.5:
            self.check_t = now
            self._set("cereal" if micd_running() else "direct")
        if self.mode == "direct":
            f = self.direct.read()
            if f is None:
                self.direct.close(); self.direct = None; self.mode = None  # reopen next loop
            return f
        return self.cereal.read()

def open_source(cfg, log):
    if cfg["audio_source"] == "auto":
        return HybridAudio(cfg, log)
    src = cfg["audio_source"]
    if src in ("auto", "cereal"):
        try:
            a = CerealAudio()
            log("audio: cereal rawAudioData (micd)")
            return a
        except Exception as e:
            if src == "cereal":
                raise
            log(f"audio: cereal unavailable ({e}); falling back to ALSA")
    a = AlsaAudio(cfg["alsa_device"])
    log(f"audio: ALSA device={cfg['alsa_device'] or 'default'}")
    return a
