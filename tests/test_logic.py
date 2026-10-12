import unittest
from cwr import config
from cwr.guard import VehicleSnapshot, check
from cwr.statemachine import Machine, S

CFG = dict(config.DEFAULTS); CFG["speed_limit_kph"] = 20.0

def snap(v=0.0, started=False, t=100.0, engaged=False, standstill=True):
    return VehicleSnapshot(v, t, started, t, engaged, standstill)

class Guard(unittest.TestCase):
    def test_parked_ok(self): self.assertTrue(check(snap(), CFG, now=100.2)[0])
    def test_onroad_blocked(self): self.assertFalse(check(snap(started=True), CFG, now=100.2)[0])
    def test_speed_blocked(self): self.assertFalse(check(snap(v=25/3.6), CFG, now=100.2)[0])
    def test_rolling_blocked_by_standstill(self):
        self.assertFalse(check(snap(v=10/3.6, standstill=False), CFG, now=100.2)[0])
    def test_speed_under_without_standstill_rule(self):
        self.assertTrue(check(snap(v=10/3.6, standstill=False), dict(CFG, require_standstill=False), now=100.2)[0])
    def test_no_device_state(self): self.assertFalse(check(VehicleSnapshot(), CFG, now=1)[0])
    def test_stale_onroad_speed(self):
        c = dict(CFG, block_if_onroad=False)
        self.assertFalse(check(snap(started=True), c, now=103)[0])
    def test_engaged(self): self.assertFalse(check(snap(engaged=True), CFG, now=100.1)[0])
    def test_cap(self):
        self.assertEqual(config.clamp_speed(80), 20); self.assertEqual(config.clamp_speed(5), 5)
        self.assertEqual(config.clamp_speed("x"), 20)

class Cfg(unittest.TestCase):
    def _load(self, d):
        import json, tempfile, os
        td = tempfile.mkdtemp(); p = os.path.join(td, "config.json")
        wr(p, json.dumps(d)); return config.load(p)
    def test_defaults(self):
        c = config.load("/nonexistent.json")
        self.assertEqual((c["tap_count"], c["tap_window_s"]), (5, 2.5)); self.assertFalse(c["dry_run"])
    def test_clamps_and_voice_keys_dropped(self):
        c = self._load({"speed_limit_kph": 99, "tap_count": 1, "tap_window_s": 60, "cooldown_s": 0,
                        "mic_gain": 4, "wake_threshold": 0.3, "standstill_max_kph": 50})
        self.assertEqual(c["speed_limit_kph"], 20); self.assertEqual(c["tap_count"], 3)
        self.assertEqual(c["tap_window_s"], 5.0); self.assertEqual(c["cooldown_s"], 5.0)
        self.assertEqual(c["standstill_max_kph"], 20)
        self.assertNotIn("mic_gain", c); self.assertNotIn("wake_threshold", c)
    def test_local_override(self):
        import json, tempfile, os
        td = tempfile.mkdtemp(); p = os.path.join(td, "config.json"); wr(p, "{}")
        wr(os.path.join(td, "config.local.json"), json.dumps({"dry_run": True, "mic_gain": 8}))
        c = config.load(p); self.assertTrue(c["dry_run"]); self.assertNotIn("mic_gain", c)

from cwr import touch as T

def wr(p, v):
    with open(p, "w") as f: f.write(v)

def rd(p):
    with open(p) as f: return f.read()

def tap(t, x=100, y=100, dur=0.08, mt=True, btn=True, slot_id=1, move=0):
    """Synthetic kernel events for one tap (type-B multitouch + BTN_TOUCH)."""
    ev = []
    if mt: ev += [(t, T.EV_ABS, T.ABS_MT_TRACKING_ID, slot_id), (t, T.EV_ABS, T.ABS_MT_POSITION_X, x), (t, T.EV_ABS, T.ABS_MT_POSITION_Y, y)]
    if btn: ev.append((t, T.EV_KEY, T.BTN_TOUCH, 1))
    ev.append((t, T.EV_SYN, T.SYN_REPORT, 0))
    tm = t + dur / 2
    ev += [(tm, T.EV_ABS, T.ABS_MT_POSITION_X, x + move), (tm, T.EV_SYN, T.SYN_REPORT, 0)]
    tu = t + dur
    if mt: ev.append((tu, T.EV_ABS, T.ABS_MT_TRACKING_ID, -1))
    if btn: ev.append((tu, T.EV_KEY, T.BTN_TOUCH, 0))
    ev.append((tu, T.EV_SYN, T.SYN_REPORT, 0))
    return ev

def run(det, evs): return [e[0] for e in evs if det.feed(*e)]

class Taps(unittest.TestCase):
    def d(self): return T.TapDetector(5, 2.5, 0.6, 0.4, 60)
    def seq(self, times, **kw): return [e for t in times for e in tap(t, **kw)]
    def test_five_quick_taps(self):
        self.assertEqual(len(run(self.d(), self.seq([0, .3, .6, .9, 1.2]))), 1)
    def test_four_taps_no(self):
        self.assertEqual(run(self.d(), self.seq([0, .3, .6, .9])), [])
    def test_mt_only_and_btn_only(self):
        self.assertEqual(len(run(self.d(), self.seq([0, .3, .6, .9, 1.2], btn=False))), 1)
        self.assertEqual(len(run(self.d(), self.seq([0, .3, .6, .9, 1.2], mt=False))), 1)
    def test_gap_too_long_resets(self):
        self.assertEqual(run(self.d(), self.seq([0, .3, .6, 1.4, 1.7, 2.0, 2.3])), [])
    def test_window_exceeded(self):
        d = T.TapDetector(5, 1.5, 0.6, 0.4, 60)   # gaps ok (0.5) but 5 taps span 2.0 s > 1.5 s
        self.assertEqual(run(d, self.seq([0, .5, 1.0, 1.5, 2.0])), [])
    def test_slow_but_within_window(self):
        self.assertEqual(len(run(self.d(), self.seq([0, .5, 1.0, 1.5, 2.0]))), 1)
    def test_long_press_not_counted(self):
        ev = self.seq([0, .3, .6]) + tap(.9, dur=.6) + self.seq([1.6, 1.9])
        self.assertEqual(run(self.d(), ev), [])
    def test_swipe_not_counted(self):
        ev = self.seq([0, .3]) + tap(.6, move=300) + self.seq([.9, 1.2])
        self.assertEqual(run(self.d(), ev), [])
    def test_ten_taps_two_triggers_then_reset(self):
        self.assertEqual(len(run(self.d(), self.seq([i * .3 for i in range(10)]))), 2)

class Sysfs(unittest.TestCase):
    def test_find_touch_device(self):
        import tempfile, os
        r = tempfile.mkdtemp()
        for n, caps, name in (("event0", "0", "pmic_pwrkey"), ("event3", "261800000000003", "touchscreen")):
            d = os.path.join(r, n, "device", "capabilities"); os.makedirs(d)
            wr(os.path.join(d, "abs"), caps + "\n")
            wr(os.path.join(r, n, "device", "name"), name + "\n")
        self.assertEqual(T.find_touch_device(r), ("/dev/input/event3", "touchscreen"))
    def test_bitmap(self):
        self.assertTrue(T._has_bit("261800000000003", T.ABS_MT_POSITION_X))
        self.assertFalse(T._has_bit("3", T.ABS_MT_POSITION_X))
    def test_reader_parses_struct(self):
        import os, struct
        rfd, wfd = os.pipe()
        os.write(wfd, struct.pack(T.EVENT_FMT, 10, 500000, T.EV_KEY, T.BTN_TOUCH, 1))
        r = T.TouchReader.__new__(T.TouchReader); r.fd, r.buf, r.path = rfd, b"", "pipe"
        os.set_blocking(rfd, False)
        self.assertEqual(r.events(), [(10.5, T.EV_KEY, T.BTN_TOUCH, 1)])
    def test_pulse_and_restore(self):
        import tempfile, os
        from cwr import feedback
        d = tempfile.mkdtemp()
        wr(os.path.join(d, "brightness"), "40")
        wr(os.path.join(d, "max_brightness"), "255")
        self.assertTrue(feedback.pulse(d, on_s=0))
        self.assertEqual(rd(os.path.join(d, "brightness")), "40")
        self.assertFalse(feedback.pulse("/nonexistent"))
        self.assertIsNone(feedback.haptic(nodes=("/nonexistent/vib",)))

class Act:
    def __init__(self, guard_seq=None): self.log = []
    def ignored(self, w): self.log.append("ignored")
    def refuse(self, w): self.log.append("refuse")
    def accepted(self): self.log.append("accepted")
    def restarting(self): self.log.append("restarting")
    def shutdown(self): self.log.append("shutdown")

class SM(unittest.TestCase):
    def mk(self, results):
        self.a = Act(); it = iter(results)
        return Machine(CFG, lambda: next(it), self.a)
    def test_full_flow(self):
        m = self.mk([(True, ""), (True, "")]); self.assertEqual(m.trigger(0), S.SHUTDOWN)
        self.assertEqual(self.a.log, ["accepted", "restarting", "shutdown"])
    def test_refused(self):
        m = self.mk([(False, "speed")]); m.trigger(0)
        self.assertEqual(self.a.log, ["accepted", "refuse"]); self.assertEqual(m.state, S.IDLE)
    def test_recheck_after_restarting(self):
        m = self.mk([(True, ""), (False, "onroad")]); m.trigger(0)
        self.assertEqual(self.a.log, ["accepted", "restarting", "refuse"]); self.assertEqual(m.state, S.IDLE)
    def test_cooldown(self):
        m = self.mk([(False, "x"), (True, ""), (True, "")]); m.trigger(0); m.trigger(10)
        self.assertEqual(self.a.log, ["accepted", "refuse", "ignored"])
        m.trigger(31); self.assertEqual(m.state, S.SHUTDOWN)

class Sounds(unittest.TestCase):
    def test_clips(self):
        import os, wave
        d = os.path.join(os.path.dirname(__file__), "..", "sounds")
        self.assertEqual(sorted(f for f in os.listdir(d) if f.endswith(".wav")), ["refused.wav", "restarting.wav"])
        for n in ("restarting", "refused"):
            with wave.open(os.path.join(d, n + ".wav")) as w:
                self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate()), (1, 2, 48000))
    def test_fallback_tone(self):
        import tempfile, os
        from cwr import sounds
        self.assertTrue(sounds.path_for("restarting", tempfile.mkdtemp()).endswith("cwr_ok.wav"))

if __name__ == "__main__": unittest.main()
