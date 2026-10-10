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
    for k in ("wake_model", "confirm_model"):
        if not os.path.exists(cfg[k]):
            log(f"missing model {cfg[k]} - see training/README.md. Exiting."); sys.exit(2)
    from openwakeword.model import Model
    oww = Model(wakeword_models=[cfg["wake_model"], cfg["confirm_model"]], inference_framework="onnx")
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
        if m.step(time.monotonic(), sc.get(wk, 0), sc.get(ck, 0)) == S.SHUTDOWN:
            time.sleep(60)

if __name__ == "__main__":
    main()
