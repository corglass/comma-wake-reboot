"""swipe + 3 taps -> confirmation (chime + screen pulse) -> guard -> "Restarting" (played fully) ->
guard re-check -> shutdown. Cooldown after any trigger."""
import enum

class S(enum.Enum):
    IDLE = "idle"
    SHUTDOWN = "shutdown"

class Machine:
    def __init__(self, cfg, guard_fn, actions):
        self.cfg, self.guard, self.a = cfg, guard_fn, actions
        self.state = S.IDLE
        self.cooldown_until = 0.0

    def trigger(self, now):
        if self.state != S.IDLE:
            return self.state
        if now < self.cooldown_until:
            self.a.ignored("cooldown"); return self.state
        self.cooldown_until = now + self.cfg["cooldown_s"]
        self.a.accepted()                # immediate confirmation: chime + screen flash
        ok, why = self.guard()
        if not ok:
            self.a.refuse(why); return self.state
        self.a.restarting()              # spoken "Restarting", blocks until finished
        ok, why = self.guard()           # re-check right before acting
        if not ok:
            self.a.refuse(why); return self.state
        self.state = S.SHUTDOWN
        self.a.shutdown()
        return self.state
