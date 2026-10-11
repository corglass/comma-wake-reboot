"""IDLE -(wake + guard ok)-> prompt -> CONFIRMING -(confirm + guard re-check)-> SHUTDOWN
CONFIRMING -(timeout)-> cancel -> IDLE. Cooldown after any trigger.

confirm_mode:
  repeat   (default) the confirmation is a SECOND wake-word detection ("alexa" twice)
  wakeword the confirmation is the separate confirm_model (e.g. "hey jarvis")
Echo guard: confirmation is ignored until the prompt has finished playing + echo_guard_s
(actions block while playing, so the clock is read again after the prompt)."""
import enum, time

class S(enum.Enum):
    IDLE = "idle"
    CONFIRMING = "confirming"
    SHUTDOWN = "shutdown"

class Machine:
    def __init__(self, cfg, guard_fn, actions, clock=time.monotonic):
        self.cfg, self.guard, self.a, self.clock = cfg, guard_fn, actions, clock
        self.state = S.IDLE
        self.arm_at = self.deadline = self.cooldown_until = 0.0

    def _idle(self, now):
        self.state, self.cooldown_until = S.IDLE, now + self.cfg["cooldown_s"]

    def step(self, now, wake_score, confirm_score):
        c = self.cfg
        if self.state == S.IDLE:
            if now < self.cooldown_until or wake_score < c["wake_threshold"]:
                return self.state
            ok, why = self.guard()
            if not ok:
                self.a.refuse(why); self._idle(now); return self.state
            self.a.prompt()                       # blocks until the prompt finished playing
            self.arm_at = self.clock() + c["echo_guard_s"]
            self.deadline = self.arm_at + c["confirm_timeout_s"]
            self.state = S.CONFIRMING
        elif self.state == S.CONFIRMING:
            if now > self.deadline:
                self.a.cancel("timeout"); self._idle(now); return self.state
            if now < self.arm_at:
                return self.state                 # echo guard
            if c["confirm_mode"] == "repeat":
                hit = wake_score >= c["wake_threshold"]
            else:
                hit = confirm_score >= c["confirm_threshold"]
            if hit:
                ok, why = self.guard()            # re-check at the last moment
                if not ok:
                    self.a.refuse(why); self._idle(now)
                else:
                    self.state = S.SHUTDOWN
                    self.a.shutdown()
        return self.state

    def listening(self, now):
        """False while the echo guard is active (main loop discards audio then)."""
        return not (self.state == S.CONFIRMING and now < self.arm_at)
