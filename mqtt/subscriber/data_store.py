"""
Thread-safe data store for the subscriber.

Holds the rolling deques shared between the MQTT callback thread and the
matplotlib animation callbacks.
"""

import threading
from collections import deque

from subscriber.config import PARAMS, MAX_POINTS


class DataStore:
    """Thread-safe rolling buffer for telemetry data."""

    def __init__(self):
        self.times = deque(maxlen=MAX_POINTS)
        self.buffers = {p: deque(maxlen=MAX_POINTS) for p in PARAMS}
        self.fault_buf = deque(maxlen=MAX_POINTS)
        self.label_buf = deque(maxlen=MAX_POINTS)
        self.lock = threading.Lock()
        self.data_dirty = threading.Event()
