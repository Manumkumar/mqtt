"""
Subscriber-specific configuration constants.

Controls buffer sizes, refresh rates, logging cadence, and the parameter
lists used by the dashboard and signal-conditioning pipeline.
"""

# ---- Data files ----
DATA_FILE = "received_data.jsonl"      # raw records (JSONL: one per line)
FILTERED_FILE = "filtered_value.json"  # conditioned-signal log (JSONL)

# ---- Buffer / display ----
MAX_POINTS = 300         # last ~60 s at 5 Hz
PLOT_INTERVAL_MS = 250   # GUI refresh period
LOG_EVERY = 10           # print 1 in N messages to stdout

# ---- Parameters ----
PARAMS = (
    "vpt_nwkr", "vpt_rwkr",
    "nwkr", "rwkr", "nwcr", "rwcr",
    "vpt_110_n", "vpt_110_r",
    "ipt_n", "ipt_r",
    "vpt_24_n", "vpt_24_r",
    "vib_x",
    "tpt_n", "tpt_r",
)

# Numerical params that go through the conditioning pipeline.
# Digital relays (nwkr/rwkr/nwcr/rwcr) are skipped — filtering
# would distort step transitions.
FILTERED_PARAMS = (
    "vpt_nwkr", "vpt_rwkr",
    "vpt_110_n", "vpt_110_r",
    "ipt_n", "ipt_r",
    "vpt_24_n", "vpt_24_r",
    "vib_x",
    "tpt_n", "tpt_r",
)

# ---- Time-features ----
EVENT_FILE = "time_features.jsonl"   # per-stroke event log
MAX_EVENTS = 200                     # rolling event buffer for dashboard

MAX_SAFE_TPT = 8.0                   # seconds; stroke slip threshold

# rail name → min_safe voltage (drop below this counts as a drop)
VDROP_THRESHOLDS = {
    "vpt_110_n": 90.0,
    "vpt_110_r": 90.0,
    "vpt_nwkr":  21.0,
    "vpt_rwkr":  21.0,
    "vpt_24_n":  21.0,
    "vpt_24_r":  21.0,
}
VDROP_RAILS = tuple(VDROP_THRESHOLDS.keys())
