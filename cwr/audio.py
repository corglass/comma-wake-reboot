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

def open_source(cfg, log):
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
