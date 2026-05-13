"""Stateful detector for stroke operation-time, slipping, and voltage drop.

Called once per telemetry record from the MQTT on_message callback.
Single-owner: lives in the MQTT thread; no internal locking.
"""

import copy

from subscriber.config import MAX_SAFE_TPT, VDROP_THRESHOLDS, VDROP_RAILS


class TimeFeatureDetector:
    """Detect stroke events and accumulate voltage-drop seconds."""

    def __init__(self) -> None:
        self.prev_nwcr = 0
        self.prev_rwcr = 0
        self.prev_nwkr = 0
        self.prev_rwkr = 0
        self.prev_tpt_n = 0.0
        self.prev_tpt_r = 0.0
        self.stroke_start_ts: float | None = None
        self.stroke_side: str | None = None
        self.vdrop_start: dict[str, float | None] = {r: None for r in VDROP_RAILS}
        self.counters = {
            "stroke_count": 0,
            "slip_count":   0,
            "vdrop_seconds": {r: 0.0 for r in VDROP_RAILS},
            "last_op_time": 0.0,
        }

    def update(self, record: dict) -> dict | None:
        ts = record.get("timestamp", 0) or 0
        if ts == 0:
            return None

        # ---- vdrop accumulation per rail ----
        for rail, threshold in VDROP_THRESHOLDS.items():
            value = record.get(rail, 0) or 0
            below = value < threshold
            start = self.vdrop_start[rail]
            if below and start is None:
                self.vdrop_start[rail] = ts
            elif not below and start is not None:
                self.counters["vdrop_seconds"][rail] += ts - start
                self.vdrop_start[rail] = None

        # ---- tpt-based stroke detection ----
        tpt_n = record.get("tpt_n", 0) or 0
        tpt_r = record.get("tpt_r", 0) or 0
        event = None
        if tpt_n > 0 and tpt_n != self.prev_tpt_n:
            event = self._build_event(ts, "N", float(tpt_n))
        elif tpt_r > 0 and tpt_r != self.prev_tpt_r:
            event = self._build_event(ts, "R", float(tpt_r))
        self.prev_tpt_n = tpt_n
        self.prev_tpt_r = tpt_r

        # ---- relay-edge fallback (only if no tpt event this sample) ----
        nwcr = int(record.get("nwcr", 0) or 0)
        rwcr = int(record.get("rwcr", 0) or 0)
        nwkr = int(record.get("nwkr", 0) or 0)
        rwkr = int(record.get("rwkr", 0) or 0)

        if event is None:
            # Rising contactor → mark stroke start. If both nwcr and rwcr
            # rise on the same sample, N takes priority (firmware emits one
            # contactor at a time in normal operation).
            if nwcr == 1 and self.prev_nwcr == 0:
                self.stroke_start_ts = ts
                self.stroke_side = "N"
            elif rwcr == 1 and self.prev_rwcr == 0:
                self.stroke_start_ts = ts
                self.stroke_side = "R"

            # Rising position relay → close stroke (matching side) or discard (opposite)
            if self.stroke_start_ts is not None:
                if self.stroke_side == "N":
                    if nwkr == 1 and self.prev_nwkr == 0:
                        op_time = ts - self.stroke_start_ts
                        event = self._build_event(ts, "N", op_time)
                        self.stroke_start_ts = None
                        self.stroke_side = None
                    elif rwkr == 1 and self.prev_rwkr == 0:
                        # Wrong side — discard
                        self.stroke_start_ts = None
                        self.stroke_side = None
                elif self.stroke_side == "R":
                    if rwkr == 1 and self.prev_rwkr == 0:
                        op_time = ts - self.stroke_start_ts
                        event = self._build_event(ts, "R", op_time)
                        self.stroke_start_ts = None
                        self.stroke_side = None
                    elif nwkr == 1 and self.prev_nwkr == 0:
                        self.stroke_start_ts = None
                        self.stroke_side = None

        self.prev_nwcr = nwcr
        self.prev_rwcr = rwcr
        self.prev_nwkr = nwkr
        self.prev_rwkr = rwkr

        return event

    def _build_event(self, ts: float, side: str, op_time: float) -> dict:
        slipping = op_time > MAX_SAFE_TPT
        self.counters["stroke_count"] += 1
        if slipping:
            self.counters["slip_count"] += 1
        self.counters["last_op_time"] = op_time
        return {
            "timestamp": ts,
            "side": side,
            "op_time": op_time,
            "slipping": slipping,
            "vdrop_seconds_snapshot": dict(self.counters["vdrop_seconds"]),
            "stroke_count": self.counters["stroke_count"],
            "slip_count":   self.counters["slip_count"],
        }

    def snapshot_counters(self) -> dict:
        return copy.deepcopy(self.counters)
