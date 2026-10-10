"""IDLE -> (wake) -> CONFIRMING -> (confirm within timeout + guard ok) -> SHUTDOWN
CONFIRMING -> timeout -> CANCELLED -> IDLE.  Cooldown after any trigger."""
import enum

class S(enum.Enum):
    IDLE = "idle"
    CONFIRMING = "confirming"
    SHUTDOWN = "shutdown"

class Machine:
    def __init__(self, cfg, guard_fn, actions):
        self.cfg, self.guard, self.a = cfg, guard_fn, actions
        self.state = S.IDLE
        self.deadline = 0.0
        self.cooldown_until = 0.0

    def step(self, now, wake_score, confirm_score):
        c = self.cfg
        if self.state == S.IDLE:
            if now < self.cooldown_until or wake_score < c["wake_threshold"]:
                return self.state
            ok, why = self.guard()
            if not ok:
                self.a.refuse(why)
                self.cooldown_until = now + c["cooldown_s"]
                return self.state
            self.a.chime()
            self.state, self.deadline = S.CONFIRMING, now + c["confirm_timeout_s"]
        elif self.state == S.CONFIRMING:
            if now > self.deadline:
                self.a.cancel("timeout")
                self.state, self.cooldown_until = S.IDLE, now + c["cooldown_s"]
            elif now < self.deadline - c["confirm_timeout_s"] + c.get("confirm_arm_delay_s", 0):
                pass
            elif confirm_score >= c["confirm_threshold"]:
                ok, why = self.guard()   # re-check at the last moment
                if not ok:
                    self.a.refuse(why)
                    self.state, self.cooldown_until = S.IDLE, now + c["cooldown_s"]
                else:
                    self.state = S.SHUTDOWN
                    self.a.shutdown()
        return self.state
