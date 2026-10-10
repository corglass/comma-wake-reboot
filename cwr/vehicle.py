"""Read-only cereal subscription to carState / deviceState / selfdriveState."""
import time
from .guard import VehicleSnapshot

class Vehicle:
    def __init__(self):
        self.snap = VehicleSnapshot()
        try:
            from cereal import messaging  # via PYTHONPATH=/data/openpilot
        except ImportError:
            from openpilot.cereal import messaging
        self.sm = messaging.SubMaster(["carState", "deviceState", "selfdriveState"])

    def update(self):
        self.sm.update(0)
        now = time.monotonic()
        if self.sm.updated["carState"]:
            self.snap.v_ego_ms, self.snap.speed_ts = float(self.sm["carState"].vEgo), now
        if self.sm.updated["deviceState"]:
            self.snap.started, self.snap.started_ts = bool(self.sm["deviceState"].started), now
        if self.sm.updated["selfdriveState"]:
            self.snap.engaged = bool(self.sm["selfdriveState"].enabled)
        return self.snap
