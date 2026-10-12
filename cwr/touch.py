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
