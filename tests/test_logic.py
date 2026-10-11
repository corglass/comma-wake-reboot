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
    def test_defaults(self):
        c = config.load("/nonexistent.json")
        self.assertTrue(c["dry_run"]); self.assertTrue(c["wake_model"].endswith("alexa_v0.1.onnx"))
        self.assertTrue(c["confirm_model"].endswith("hey_jarvis_v0.1.onnx"))
    def test_clamps(self):
        import json, tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"speed_limit_kph": 99, "wake_threshold": 0.01, "wake_patience": 0, "standstill_max_kph": 50}, f)
        c = config.load(f.name)
        self.assertEqual(c["speed_limit_kph"], 20); self.assertEqual(c["wake_threshold"], 0.3)
        self.assertEqual(c["wake_patience"], 1); self.assertEqual(c["standstill_max_kph"], 20)

class Pat(unittest.TestCase):
    def test_patience(self):
        from cwr.detector import Patience
        p = Patience(0.5, 3)
        self.assertEqual([p.update(x) for x in (.9, .9, .1, .9, .9, .9)], [0, 0, 0, 0, 0, 1.0])

class Act:
    def __init__(self): self.log = []
    def chime(self): self.log.append("chime")
    def cancel(self, w): self.log.append("cancel")
    def refuse(self, w): self.log.append("refuse")
    def shutdown(self): self.log.append("shutdown")

class SM(unittest.TestCase):
    def mk(self, ok=True):
        self.a = Act(); self.ok = ok
        return Machine(CFG, lambda: (self.ok, "x"), self.a)
    def test_full(self):
        m = self.mk(); m.step(0, .9, 0); self.assertEqual(m.state, S.CONFIRMING)
        m.step(0.5, 0, .9); self.assertEqual(m.state, S.CONFIRMING)  # arm delay
        m.step(1, 0, .9); self.assertEqual(self.a.log, ["chime", "shutdown"])
    def test_timeout(self):
        m = self.mk(); m.step(0, .9, 0); m.step(CFG["confirm_timeout_s"] + 1, 0, .9)
        self.assertEqual(self.a.log, ["chime", "cancel"]); self.assertEqual(m.state, S.IDLE)
    def test_confirm_without_wake(self):
        m = self.mk(); m.step(0, 0, .99); self.assertEqual(self.a.log, [])
    def test_guard_refuse(self):
        m = self.mk(ok=False); m.step(0, .9, 0); self.assertEqual(self.a.log, ["refuse"])
    def test_guard_recheck(self):
        m = self.mk(); m.step(0, .9, 0); self.ok = False; m.step(1, 0, .9)
        self.assertEqual(self.a.log, ["chime", "refuse"])
    def test_cooldown(self):
        m = self.mk(); m.step(0, .9, 0); m.step(6, 0, 0); m.step(10, .9, 0)
        self.assertEqual(self.a.log, ["chime", "cancel"])

if __name__ == "__main__": unittest.main()
