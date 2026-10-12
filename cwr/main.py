import os, select, time
from . import config, sounds, feedback, guard as guardmod
from .statemachine import Machine, S
from .shutdown import do_shutdown
from .touch import SwipeTapDetector, TouchReader, find_touch_device, abs_range, ABS_MT_POSITION_X, ABS_MT_POSITION_Y

def log(m): print(f"[cwr] {m}", flush=True)

class Actions:
    def __init__(self, cfg): self.cfg = cfg
    def _p(self, n):
        if self.cfg["sounds"]: sounds.play(n, self.cfg["playback_device"])
    def ignored(self, why): log(f"taps ignored: {why}")
    def refuse(self, why): log(f"refused: {why}"); self._p("refused")
    def accepted(self):
        log(f"swipe + {self.cfg['tap_count']} taps accepted")
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

def make_detector(cfg, fd):
    smin = cfg["swipe_min_units"]
    axes = {"x": [ABS_MT_POSITION_X], "y": [ABS_MT_POSITION_Y], "any": [ABS_MT_POSITION_X, ABS_MT_POSITION_Y]}
    rs = [abs_range(fd, a) for a in axes[cfg["swipe_axis"]]]
    rs = [r for r in rs if r]
    if rs:
        smin = int(min(r[1] - r[0] for r in rs) * cfg["swipe_min_frac"])
    log(f"touch ranges x={abs_range(fd, ABS_MT_POSITION_X)} y={abs_range(fd, ABS_MT_POSITION_Y)}; swipe min travel={smin}")
    return SwipeTapDetector(cfg["tap_count"], cfg["tap_max_gap_s"], cfg["tap_max_press_s"], cfg["tap_max_move"],
                            cfg["arm_s"], cfg["swipe_axis"], cfg["swipe_direction"], smin, cfg["swipe_max_s"],
                            cfg["swipe_max_off_ratio"])

def main():
    cfg = config.load()
    log(f"trigger: swipe (axis={cfg['swipe_axis']} dir={cfg['swipe_direction']}) then {cfg['tap_count']} taps "
        f"within {cfg['arm_s']}s (gap <= {cfg['tap_max_gap_s']}s); dry_run={cfg['dry_run']}")
    from .vehicle import Vehicle
    veh = Vehicle()
    m = Machine(cfg, lambda: guardmod.check(veh.update(), cfg), Actions(cfg))
    det = None
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
                det = make_detector(cfg, reader.fd)
            except OSError as e:
                log(f"cannot open touchscreen: {e} (see README troubleshooting); retrying in 10 s")
                time.sleep(10); continue
        veh.update()
        if cfg["debug"] and now - hb_t >= 10:
            s = veh.snap
            log(f"hb device={reader.path} taps_total={det.total_taps} armed={det.armed_until is not None} "
                f"started={s.started} vEgo={s.v_ego_ms} state={m.state.name}")
            hb_t = now
        r, _, _ = select.select([reader.fd], [], [], 0.5)
        ev = det.expire(time.time())
        if ev: log(f"disarmed: {ev[1]}")
        if not r:
            continue
        try:
            evs = reader.events()
        except OSError as e:
            log(f"touch read error: {e}; reopening"); reader.close(); reader = None; continue
        for ev in evs:
            g = det.feed(*ev)
            if not g: continue
            if g[0] == "swipe": log(f"swipe detected dx={g[1]} dy={g[2]} dur={g[3]}s -> armed {cfg['arm_s']}s, tap {cfg['tap_count']}x")
            elif g[0] == "swipe_rejected": log(f"drag dx={g[1]} dy={g[2]} dur={g[3]}s not a swipe: {g[4]}")
            elif g[0] == "tap": log(f"tap {g[1]}/{cfg['tap_count']}")
            elif g[0] == "disarmed": log(f"disarmed: {g[1]}")
            if g[0] == "trigger":
                log("tap sequence complete")
                if m.trigger(time.monotonic()) == S.SHUTDOWN:
                    if cfg["dry_run"]:
                        m.state = S.IDLE
                    else:
                        time.sleep(60)

if __name__ == "__main__":
    main()
