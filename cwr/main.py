import os, select, time
from . import config, sounds, feedback, guard as guardmod
from .statemachine import Machine, S
from .shutdown import do_shutdown
from .touch import TapDetector, TouchReader, find_touch_device

def log(m): print(f"[cwr] {m}", flush=True)

class Actions:
    def __init__(self, cfg): self.cfg = cfg
    def _p(self, n):
        if self.cfg["sounds"]: sounds.play(n, self.cfg["playback_device"])
    def ignored(self, why): log(f"taps ignored: {why}")
    def refuse(self, why): log(f"refused: {why}"); self._p("refused")
    def accepted(self):
        log(f"{self.cfg['tap_count']} taps accepted")
        if self.cfg["haptic"]:
            n = feedback.haptic()
            if n: log(f"haptic via {n}")
        self._p("ok")
        if self.cfg["screen_pulse"] and not feedback.pulse():
            log("screen pulse unavailable (backlight not writable)")
    def restarting(self): log("restarting"); self._p("restarting")
    def shutdown(self):
        if self.cfg["dry_run"]:
            log("DRY RUN: would power off")
        do_shutdown(log, self.cfg["dry_run"])

def open_touch(cfg):
    if cfg["touch_device"]:
        return cfg["touch_device"], "configured"
    return find_touch_device() or (None, None)

def main():
    cfg = config.load()
    log(f"tap trigger: {cfg['tap_count']} taps within {cfg['tap_window_s']}s (gap <= {cfg['tap_max_gap_s']}s); "
        f"dry_run={cfg['dry_run']}")
    from .vehicle import Vehicle
    veh = Vehicle()
    m = Machine(cfg, lambda: guardmod.check(veh.update(), cfg), Actions(cfg))
    det = TapDetector(cfg["tap_count"], cfg["tap_window_s"], cfg["tap_max_gap_s"],
                      cfg["tap_max_press_s"], cfg["tap_max_move"])
    reader, hb_t = None, 0.0
    while True:
        now = time.monotonic()
        if not config.is_enabled():
            if reader: reader.close(); reader = None
            time.sleep(2); continue
        if reader is None:
            path, name = open_touch(cfg)
            try:
                if not path: raise OSError("no device with ABS_MT_POSITION_X found")
                reader = TouchReader(path); log(f"touch device: {path} ({name}), read-only, not grabbed")
            except OSError as e:
                log(f"cannot open touchscreen: {e} (see README troubleshooting); retrying in 10 s")
                time.sleep(10); continue
        veh.update()
        if cfg["debug"] and now - hb_t >= 10:
            s = veh.snap
            log(f"hb device={reader.path} taps_total={det.total_taps} in_sequence={len(det.taps)} "
                f"started={s.started} vEgo={s.v_ego_ms} state={m.state.name}")
            hb_t = now
        r, _, _ = select.select([reader.fd], [], [], 0.5)
        if not r:
            continue
        try:
            evs = reader.events()
        except OSError as e:
            log(f"touch read error: {e}; reopening"); reader.close(); reader = None; continue
        for ev in evs:
            if det.feed(*ev):
                log("tap sequence complete")
                if m.trigger(time.monotonic()) == S.SHUTDOWN:
                    if cfg["dry_run"]:
                        m.state = S.IDLE
                    else:
                        time.sleep(60)

if __name__ == "__main__":
    main()
