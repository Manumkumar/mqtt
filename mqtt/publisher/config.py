"""
Publisher-specific configuration constants.

Fault types, durations, precursor ranges, and timing are defined here
so they can be tuned independently of the engine logic.
"""

# ---- Sampling ----
SAMPLE_PERIOD = 0.2  # 5 Hz

# ---- Fault catalogue ----
FAULT_TYPES = (
    "LOW_VPT_NWKR",
    "LOW_VPT_110",
    "OBSTRUCTION",
    "OVER_CURRENT",
    "VIB_SPIKE",
    "PHANTOM_CURRENT",
    "STUCK_NWKR_DROP",
)

FAULT_DURATIONS = {
    "LOW_VPT_NWKR":    (8.0, 15.0),
    "LOW_VPT_110":     (8.0, 15.0),
    "OBSTRUCTION":     (10.0, 13.0),
    "OVER_CURRENT":    (5.0, 8.0),
    "VIB_SPIKE":       (3.0, 6.0),
    "PHANTOM_CURRENT": (4.0, 8.0),
    "STUCK_NWKR_DROP": (10.0, 20.0),
}

# ---- Precursor (drift before active fault) ----
PRECURSOR_RANGE = (10.0, 18.0)

# ---- Probability of scheduling a new fault each tick ----
FAULT_TRIGGER_PROB = 0.008  # ~1 event per 25 s at 5 Hz
