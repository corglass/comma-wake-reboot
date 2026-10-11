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
    """Mock actions; prompt() advances the fake clock by the prompt length (playback blocks)."""
    def __init__(self, clock, prompt_len=1.7): self.log, self.clock, self.plen = [], clock, prompt_len
    def prompt(self): self.log.append("prompt"); self.clock.t += self.plen
    def cancel(self, w): self.log.append("cancel")
    def refuse(self, w): self.log.append("refuse")
    def shutdown(self): self.log.append("shutdown")

class Clock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t

class SM(unittest.TestCase):
    """Default confirm_mode 'repeat': wake word twice. Prompt ends at t=1.7, echo guard 0.5 -> armed at 2.2."""
    def mk(self, ok=True, **over):
        self.c = Clock(); self.a = Act(self.c); self.ok = ok
        return Machine(dict(CFG, **over), lambda: (self.ok, "x"), self.a, clock=self.c)
    def test_defaults_repeat(self):
        self.assertEqual(CFG["confirm_mode"], "repeat"); self.assertEqual(CFG["confirm_timeout_s"], 8.0)
    def test_repeat_full(self):
        m = self.mk(); m.step(0, .9, 0); self.assertEqual(m.state, S.CONFIRMING)
        self.assertAlmostEqual(m.arm_at, 2.2)
        m.step(3, .9, 0); self.assertEqual(self.a.log, ["prompt", "shutdown"])
    def test_echo_guard_ignores_prompt_audio(self):
        m = self.mk(); m.step(0, .9, 0)
        for t in (1.8, 2.0, 2.19):
            m.step(t, .99, 0); self.assertFalse(m.listening(t) and t < 2.2)
        self.assertEqual(m.state, S.CONFIRMING); self.assertEqual(self.a.log, ["prompt"])
        self.assertTrue(m.listening(2.3))
    def test_repeat_ignores_confirm_model(self):
        m = self.mk(); m.step(0, .9, 0); m.step(3, 0, .99); self.assertEqual(m.state, S.CONFIRMING)
    def test_timeout_8s_after_prompt(self):
        m = self.mk(); m.step(0, .9, 0)
        m.step(10.1, 0, 0); self.assertEqual(m.state, S.CONFIRMING)   # deadline 2.2 + 8 = 10.2
        m.step(10.3, 0, 0); self.assertEqual(self.a.log, ["prompt", "cancel"]); self.assertEqual(m.state, S.IDLE)
    def test_late_wake_after_timeout_does_nothing(self):
        m = self.mk(); m.step(0, .9, 0); m.step(10.3, .9, 0); m.step(11, .9, 0)
        self.assertEqual(self.a.log, ["prompt", "cancel"])   # cooldown blocks re-trigger
    def test_wakeword_mode(self):
        m = self.mk(confirm_mode="wakeword"); m.step(0, .9, 0)
        m.step(3, .9, 0); self.assertEqual(m.state, S.CONFIRMING)     # wake again != confirm here
        m.step(3.1, 0, .9); self.assertEqual(self.a.log, ["prompt", "shutdown"])
    def test_confirm_without_wake(self):
        m = self.mk(); m.step(0, 0, .99); self.assertEqual(self.a.log, [])
    def test_guard_refuse(self):
        m = self.mk(ok=False); m.step(0, .9, 0); self.assertEqual(self.a.log, ["refuse"])
    def test_guard_recheck(self):
        m = self.mk(); m.step(0, .9, 0); self.ok = False; m.step(3, .9, 0)
        self.assertEqual(self.a.log, ["prompt", "refuse"]); self.assertEqual(m.state, S.IDLE)

class Sounds(unittest.TestCase):
    def test_clips_exist_and_format(self):
        import os, wave
        d = os.path.join(os.path.dirname(__file__), "..", "sounds")
        for n in ("prompt_repeat", "cancelled", "refused", "restarting", "dryrun"):
            with wave.open(os.path.join(d, n + ".wav")) as w:
                self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate()), (1, 2, 48000))
    def test_fallback_tone(self):
        import tempfile, os
        from cwr import sounds
        p = sounds.resolve("prompt_repeat", tempfile.mkdtemp())
        self.assertTrue(p.endswith("cwr_chime.wav") and os.path.exists(p))
    def test_config_clamps_mode(self):
        import json, tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"confirm_mode": "bogus", "echo_guard_s": 0}, f)
        c = config.load(f.name); self.assertEqual(c["confirm_mode"], "repeat"); self.assertEqual(c["echo_guard_s"], 0.3)

if __name__ == "__main__": unittest.main()
