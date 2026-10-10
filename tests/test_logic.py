import unittest
from cwr import config
from cwr.guard import VehicleSnapshot, check
from cwr.statemachine import Machine, S

CFG = dict(config.DEFAULTS); CFG["speed_limit_kph"] = 20.0

def snap(v=0.0, started=False, t=100.0, engaged=False):
    return VehicleSnapshot(v, t, started, t, engaged)

class Guard(unittest.TestCase):
    def test_parked_ok(self): self.assertTrue(check(snap(), CFG, now=100.2)[0])
    def test_onroad_blocked(self): self.assertFalse(check(snap(started=True), CFG, now=100.2)[0])
    def test_speed_blocked(self): self.assertFalse(check(snap(v=25/3.6), CFG, now=100.2)[0])
    def test_speed_under(self): self.assertTrue(check(snap(v=10/3.6), CFG, now=100.2)[0])
    def test_no_device_state(self): self.assertFalse(check(VehicleSnapshot(), CFG, now=1)[0])
    def test_stale_onroad_speed(self):
        c = dict(CFG, block_if_onroad=False)
        self.assertFalse(check(snap(started=True), c, now=103)[0])
    def test_engaged(self): self.assertFalse(check(snap(engaged=True), CFG, now=100.1)[0])
    def test_cap(self):
        self.assertEqual(config.clamp_speed(80), 20); self.assertEqual(config.clamp_speed(5), 5)
        self.assertEqual(config.clamp_speed("x"), 20)

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
        m.step(1, 0, .9); self.assertEqual(self.a.log, ["chime", "shutdown"])
    def test_timeout(self):
        m = self.mk(); m.step(0, .9, 0); m.step(6, 0, .9)
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
