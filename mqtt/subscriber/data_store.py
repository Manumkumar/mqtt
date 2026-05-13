"""
Thread-safe data store for the subscriber.

Holds the rolling deques shared between the MQTT callback thread and the
matplotlib animation callbacks.
"""

import threading
from collections import deque

from subscriber.config import PARAMS, MAX_POINTS, MAX_EVENTS, VDROP_RAILS


class DataStore:
    """Thread-safe rolling buffer for telemetry data."""

    def __init__(self):
        self.times = deque(maxlen=MAX_POINTS)
        self.buffers = {p: deque(maxlen=MAX_POINTS) for p in PARAMS}
        self.fault_buf = deque(maxlen=MAX_POINTS)
        self.label_buf = deque(maxlen=MAX_POINTS)
        self.event_buf = deque(maxlen=MAX_EVENTS)
        self.counters = {
            "stroke_count": 0,
            "slip_count":   0,
            "vdrop_seconds": {r: 0.0 for r in VDROP_RAILS},
            "last_op_time": 0.0,
        }
        self.lock = threading.Lock()
        self.data_dirty = threading.Event()
