"""Safety guard. Fails SAFE: any missing/stale data => refuse."""
import time
from dataclasses import dataclass

@dataclass
class VehicleSnapshot:
    v_ego_ms: float | None = None      # carState.vEgo
    speed_ts: float | None = None      # monotonic time of last carState
    started: bool | None = None        # deviceState.started (onroad)
    started_ts: float | None = None
    engaged: bool | None = None        # selfdriveState.enabled

def check(snap, cfg, now=None):
    """Return (ok, reason)."""
    now = time.monotonic() if now is None else now
    limit = cfg["speed_limit_kph"]
    stale = cfg["speed_stale_s"]
    if snap.engaged:
        return False, "openpilot engaged"
    if snap.started is None or snap.started_ts is None or now - snap.started_ts > 5.0:
        return False, "deviceState unavailable/stale"
    if snap.started and cfg.get("block_if_onroad", True):
        return False, "device is onroad (deviceState.started)"
    if snap.started:
        if snap.v_ego_ms is None or snap.speed_ts is None or now - snap.speed_ts > stale:
            return False, "speed unavailable/stale while onroad"
    if snap.v_ego_ms is not None and snap.speed_ts is not None and now - snap.speed_ts <= stale:
        kph = snap.v_ego_ms * 3.6
        if kph > limit:
            return False, f"speed {kph:.1f} km/h > {limit:.0f} km/h"
    return True, "ok"
