"""Read-only touchscreen tap detection via Linux evdev. No dependencies, no EVIOCGRAB:
sunnypilot's UI keeps receiving every touch."""
import glob, os, struct

EV_SYN, EV_KEY, EV_ABS = 0x00, 0x01, 0x03
SYN_REPORT = 0
BTN_TOUCH = 0x14a
ABS_X, ABS_Y = 0x00, 0x01
ABS_MT_SLOT, ABS_MT_POSITION_X, ABS_MT_POSITION_Y, ABS_MT_TRACKING_ID = 0x2f, 0x35, 0x36, 0x39

EVENT_FMT = "llHHi"                      # struct input_event: timeval(sec, usec), type, code, value
EVENT_SIZE = struct.calcsize(EVENT_FMT)  # 24 on aarch64

def _has_bit(hexwords, bit):
    """sysfs capability bitmaps: space-separated hex longs, most significant first."""
    words = hexwords.split()[::-1]
    bits = 64 if struct.calcsize("l") == 8 else 32
    i, b = divmod(bit, bits)
    return i < len(words) and (int(words[i], 16) >> b) & 1 == 1

def find_touch_device(sys_root="/sys/class/input"):
    """Return (/dev/input/eventN, name) for the first device with ABS_MT_POSITION_X, else None."""
    for d in sorted(glob.glob(os.path.join(sys_root, "event*"))):
        try:
            with open(os.path.join(d, "device", "capabilities", "abs")) as f:
                abs_caps = f.read()
            with open(os.path.join(d, "device", "name")) as f:
                name = f.read().strip()
        except OSError:
            continue
        if _has_bit(abs_caps, ABS_MT_POSITION_X):
            return "/dev/input/" + os.path.basename(d), name
    return None

class TapDetector:
    """Feed raw events; returns True when `count` qualifying taps happened:
    each tap: finger down->up within max_press_s, moved <= max_move px;
    gap between taps <= max_gap_s; all taps within window_s."""
    def __init__(self, count=5, window_s=2.5, max_gap_s=0.6, max_press_s=0.4, max_move=60):
        self.count, self.window, self.gap = count, window_s, max_gap_s
        self.press, self.move = max_press_s, max_move
        self.taps = []                 # down-times of accepted taps
        self.total_taps = 0            # for heartbeat
        self.slots, self.slot = set(), 0
        self.btn = None                # BTN_TOUCH state if the device reports it
        self.x = self.y = None
        self.down = None               # (t, x, y) of current press
        self.maxd = 0
        self.pending = None            # 'down' | 'up' decided at SYN_REPORT

    def feed(self, t, typ, code, val):
        if typ == EV_ABS:
            if code in (ABS_MT_POSITION_X, ABS_X): self.x = val
            elif code in (ABS_MT_POSITION_Y, ABS_Y): self.y = val
            elif code == ABS_MT_SLOT: self.slot = val
            elif code == ABS_MT_TRACKING_ID and self.btn is None:
                was = bool(self.slots)
                (self.slots.add if val >= 0 else self.slots.discard)(self.slot)
                if not was and self.slots: self.pending = "down"
                elif was and not self.slots: self.pending = "up"
        elif typ == EV_KEY and code == BTN_TOUCH:
            self.btn = val
            self.pending = "down" if val else "up"
        elif typ == EV_SYN and code == SYN_REPORT:
            return self._syn(t)
        return False

    def _syn(self, t):
        p, self.pending = self.pending, None
        if p == "down":
            self.down, self.maxd = (t, self.x, self.y), 0
        elif self.down is not None and None not in (self.x, self.y, self.down[1], self.down[2]):
            self.maxd = max(self.maxd, abs(self.x - self.down[1]) + abs(self.y - self.down[2]))
        if p == "up" and self.down is not None:
            t0 = self.down[0]; self.down = None
            if t - t0 <= self.press and self.maxd <= self.move:
                return self._tap(t0)
            self.taps = []             # drag / long press breaks the sequence
        return False

    def _tap(self, t):
        self.total_taps += 1
        if self.taps and (t - self.taps[-1] > self.gap):
            self.taps = []
        self.taps.append(t)
        self.taps = [x for x in self.taps if t - x <= self.window]
        if len(self.taps) >= self.count:
            self.taps = []
            return True
        return False

class TouchReader:
    def __init__(self, path):
        self.path = path
        self.fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)   # read-only, never grabbed
        self.buf = b""

    def events(self):
        try:
            self.buf += os.read(self.fd, EVENT_SIZE * 64)
        except BlockingIOError:
            return []
        n = len(self.buf) // EVENT_SIZE
        out = []
        for i in range(n):
            s, us, typ, code, val = struct.unpack_from(EVENT_FMT, self.buf, i * EVENT_SIZE)
            out.append((s + us / 1e6, typ, code, val))
        self.buf = self.buf[n * EVENT_SIZE:]
        return out

    def close(self):
        os.close(self.fd)

def abs_range(fd, code):
    """(min, max) of an ABS axis via EVIOCGABS, or None."""
    try:
        import fcntl
        req = (2 << 30) | (24 << 16) | (ord("E") << 8) | (0x40 + code)   # _IOR('E', 0x40+code, input_absinfo)
        buf = fcntl.ioctl(fd, req, bytes(24))
        _, mn, mx = struct.unpack("6i", buf)[:3]
        return (mn, mx) if mx > mn else None
    except (OSError, ImportError, struct.error):
        return None

class SwipeTapDetector(TapDetector):
    """Swipe, then `count` taps within arm_s. feed() returns None or one of:
    ('swipe', dx, dy, dur) -> armed;  ('swipe_rejected', dx, dy, dur, why);  ('tap', n);
    ('trigger',);  ('disarmed', why). dx/dy are raw touch units (end - start)."""
    def __init__(self, count=3, max_gap_s=0.6, max_press_s=0.4, max_move=60, arm_s=5.0,
                 swipe_axis="any", swipe_direction="any", swipe_min=150, swipe_max_s=0.8,
                 swipe_max_off_ratio=0.5):
        super().__init__(count, arm_s, max_gap_s, max_press_s, max_move)
        self.arm_s, self.axis, self.dirn = arm_s, swipe_axis, swipe_direction
        self.smin, self.smax_s, self.off = swipe_min, swipe_max_s, swipe_max_off_ratio
        self.armed_until = None

    def _swipe_check(self, dx, dy, dur):
        if dur > self.smax_s: return "too slow"
        ax = self.axis
        if ax == "any": ax = "x" if abs(dx) >= abs(dy) else "y"
        main, off = (dx, dy) if ax == "x" else (dy, dx)
        if abs(main) < self.smin: return f"too short ({abs(main)} < {self.smin})"
        if abs(off) > self.off * abs(main): return "not straight"
        if self.dirn in ("left", "up") and main > 0: return "wrong direction"
        if self.dirn in ("right", "down") and main < 0: return "wrong direction"
        return None

    def expire(self, t):
        if self.armed_until is not None and t > self.armed_until:
            self.armed_until, self.taps = None, []
            return ("disarmed", "timeout")
        return None

    def _syn(self, t):
        p, self.pending = self.pending, None
        if p == "down":
            self.down, self.maxd = (t, self.x, self.y), 0
            return self.expire(t)
        if self.down is not None and None not in (self.x, self.y, self.down[1], self.down[2]):
            self.maxd = max(self.maxd, abs(self.x - self.down[1]) + abs(self.y - self.down[2]))
        if p != "up" or self.down is None:
            return None
        t0, x0, y0 = self.down; self.down = None
        dur = t - t0
        if self.armed_until is not None and t0 > self.armed_until:
            self.armed_until, self.taps = None, []
        if dur <= self.press and self.maxd <= self.move:
            if self.armed_until is None:
                return None                      # taps without a swipe first are ignored
            if self.taps and t0 - self.taps[-1] > self.gap:
                self.taps = []
            self.taps.append(t0); self.total_taps += 1
            if len(self.taps) >= self.count:
                self.taps, self.armed_until = [], None
                return ("trigger",)
            return ("tap", len(self.taps))
        if None in (x0, y0, self.x, self.y):
            return None
        dx, dy = self.x - x0, self.y - y0
        why = self._swipe_check(dx, dy, dur)
        if why is None:
            self.armed_until, self.taps = t + self.arm_s, []
            return ("swipe", dx, dy, round(dur, 2))
        was = self.armed_until is not None
        self.armed_until, self.taps = None, []
        return ("swipe_rejected", dx, dy, round(dur, 2), why + ("; disarmed" if was else ""))
