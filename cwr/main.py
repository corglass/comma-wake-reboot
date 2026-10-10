import os, sys, time
from . import config, sounds, guard as guardmod
from .statemachine import Machine, S
from .shutdown import do_shutdown

def log(m): print(f"[cwr] {m}", flush=True)

class Actions:
    def __init__(self, cfg): self.cfg = cfg
    def chime(self): log("wake detected; say 'confirm'"); sounds.play("chime", self.cfg["playback_device"])
    def cancel(self, why): log(f"cancelled: {why}"); sounds.play("cancel", self.cfg["playback_device"])
    def refuse(self, why): log(f"refused: {why}"); sounds.play("refuse", self.cfg["playback_device"])
    def shutdown(self): sounds.play("ok", self.cfg["playback_device"]); do_shutdown(log, self.cfg["dry_run"])

def main():
    cfg = config.load()
    # thresholds are applied by Patience (1.0/0.0 output), so the machine sees binary scores
    for k in ("wake_model", "confirm_model"):
        if not os.path.exists(cfg[k]):
            log(f"missing model {cfg[k]} - see training/README.md. Exiting."); sys.exit(2)
    from openwakeword.model import Model
    kw = dict(wakeword_models=[cfg["wake_model"], cfg["confirm_model"]], inference_framework="onnx",
              vad_threshold=cfg["vad_threshold"])
    if cfg["noise_suppression"]:
        kw["enable_speex_noise_suppression"] = True
    oww = Model(**kw)
    from .detector import Patience
    pw = Patience(cfg["wake_threshold"], cfg["wake_patience"])
    pc = Patience(cfg["confirm_threshold"], cfg["confirm_patience"])
    if cfg["dry_run"]:
        log("DRY RUN is ON: detections are logged and chimes play, but the device will NOT power off")
    wk = os.path.splitext(os.path.basename(cfg["wake_model"]))[0]
    ck = os.path.splitext(os.path.basename(cfg["confirm_model"]))[0]
    from .vehicle import Vehicle
    veh = Vehicle()
    m = Machine(cfg, lambda: guardmod.check(veh.update(), cfg), Actions(cfg))
    audio = None
    while True:
        if not config.is_enabled():
            audio = None; time.sleep(2); continue
        if audio is None:
            from .audio import open_source
            audio = open_source(cfg, log)
        veh.update()
        frame = audio.read()
        if frame is None:
            continue
        sc = oww.predict(frame)
        w, c = pw.update(sc.get(wk, 0)), pc.update(sc.get(ck, 0))
        prev = m.state
        st = m.step(time.monotonic(), w, c)
        if st != prev:
            pw.reset(); pc.reset(); oww.reset()
        if st == S.SHUTDOWN:
            if cfg["dry_run"]:
                m.state = S.IDLE; m.cooldown_until = time.monotonic() + cfg["cooldown_s"]
            else:
                time.sleep(60)

if __name__ == "__main__":
    main()
