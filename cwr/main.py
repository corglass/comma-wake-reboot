import os, sys, time
from . import config, sounds, guard as guardmod
from .statemachine import Machine, S
from .shutdown import do_shutdown

def log(m): print(f"[cwr] {m}", flush=True)

class Actions:
    def __init__(self, cfg): self.cfg = cfg
    def _p(self, clip, tone):
        sounds.play(clip if self.cfg["speak"] else tone, self.cfg["playback_device"])
    def prompt(self):
        if self.cfg["confirm_mode"] == "repeat":
            log("wake detected; prompting: say the wake word again"); self._p("prompt_repeat", "chime")
        else:
            log("wake detected; say the confirm word"); self._p("chime", "chime")
    def cancel(self, why): log(f"cancelled: {why}"); self._p("cancelled", "cancel")
    def refuse(self, why): log(f"refused: {why}"); self._p("refused", "refuse")
    def shutdown(self):
        if self.cfg["dry_run"]:
            log("DRY RUN: would power off"); self._p("dryrun", "ok")
        else:
            self._p("restarting", "ok")
        do_shutdown(log, self.cfg["dry_run"])

def main():
    cfg = config.load()
    # thresholds are applied by Patience (1.0/0.0 output), so the machine sees binary scores
    need = ["wake_model"] + (["confirm_model"] if cfg["confirm_mode"] == "wakeword" else [])
    for k in need:
        if not os.path.exists(cfg[k]):
            log(f"missing model {cfg[k]} - see training/README.md. Exiting."); sys.exit(2)
    from openwakeword.model import Model
    kw = dict(wakeword_models=[cfg[k] for k in need], inference_framework="onnx",
              vad_threshold=cfg["vad_threshold"])
    if cfg["noise_suppression"]:
        kw["enable_speex_noise_suppression"] = True
    oww = Model(**kw)
    from .detector import Patience
    pw = Patience(cfg["wake_threshold"], cfg["wake_patience"])
    pc = Patience(cfg["confirm_threshold"], cfg["confirm_patience"])
    if cfg["dry_run"]:
        log("DRY RUN is ON: detections are logged and prompts play, but the device will NOT power off")
    log(f"confirm_mode={cfg['confirm_mode']} timeout={cfg['confirm_timeout_s']}s echo_guard={cfg['echo_guard_s']}s")
    wk = os.path.splitext(os.path.basename(cfg["wake_model"]))[0]
    ck = os.path.splitext(os.path.basename(cfg["confirm_model"]))[0]
    from .vehicle import Vehicle
    veh = Vehicle()
    m = Machine(cfg, lambda: guardmod.check(veh.update(), cfg), Actions(cfg))
    audio = None
    # Heartbeat every 2 s: audio frames, input level, peak scores. Helps diagnose mic/threshold issues.
    hb_t, hb_n, hb_rms, hb_w, hb_c, last_frame = time.monotonic(), 0, 0.0, 0.0, 0.0, time.monotonic()
    debug = cfg.get("debug", True)
    while True:
        if not config.is_enabled():
            audio = None; time.sleep(2); continue
        if audio is None:
            from .audio import open_source
            audio = open_source(cfg, log)
        veh.update()
        frame = audio.read()
        now = time.monotonic()
        if debug and now - hb_t >= 2:
            log(f"hb frames={hb_n} level={hb_rms:.0f} max_{wk}={hb_w:.2f} max_{ck}={hb_c:.2f} state={m.state.name}")
            hb_t, hb_n, hb_rms, hb_w, hb_c = now, 0, 0.0, 0.0, 0.0
        if frame is None:
            if now - last_frame > 10:
                log("no audio frames for 10 s - check audio_source (see README troubleshooting)"); last_frame = now
            continue
        last_frame = now
        if not m.listening(now):
            continue                      # echo guard: drop audio buffered during/just after the prompt
        if m.state.name == "CONFIRMING" and not getattr(m, "_flushed", False):
            oww.reset(); pw.reset(); m._flushed = True
        sc = oww.predict(frame)
        if debug:
            import numpy as _np
            hb_n += 1
            hb_rms = max(hb_rms, float(_np.sqrt(_np.mean(frame.astype(_np.float32) ** 2))))
            hb_w, hb_c = max(hb_w, sc.get(wk, 0)), max(hb_c, sc.get(ck, 0))
        w, c = pw.update(sc.get(wk, 0)), pc.update(sc.get(ck, 0))
        prev = m.state
        st = m.step(time.monotonic(), w, c)
        if st != prev:
            pw.reset(); pc.reset(); oww.reset(); m._flushed = False
        if st == S.SHUTDOWN:
            if cfg["dry_run"]:
                m.state = S.IDLE; m.cooldown_until = time.monotonic() + cfg["cooldown_s"]
            else:
                time.sleep(60)

if __name__ == "__main__":
    main()
