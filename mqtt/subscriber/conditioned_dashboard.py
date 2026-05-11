"""
Conditioned-signal dashboard (4×2 matplotlib figure).

Shows raw vs. conditioned waveforms for key numerical parameters using the
Median → Savitzky-Golay → Kalman pipeline.
"""

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

from subscriber.config import PLOT_INTERVAL_MS
from subscriber.data_store import DataStore
from subscriber.signal_conditioning import (
    condition_signal,
    MEDIAN_KERNEL,
    SAVGOL_WINDOW,
    SAVGOL_POLY,
    KALMAN_Q,
    KALMAN_R,
)

# Parameters displayed in the conditioned dashboard
COND_PARAMS = (
    ("vpt_110_n", "VPT 110 N",   "Volts"),
    ("vpt_110_r", "VPT 110 R",   "Volts"),
    ("vpt_nwkr",  "VPT NWKR",    "Volts"),
    ("vpt_rwkr",  "VPT RWKR",    "Volts"),
    ("ipt_n",     "IPT N",       "Amps"),
    ("ipt_r",     "IPT R",       "Amps"),
    ("vib_x",     "Vibration X", ""),
)


def create_conditioned_dashboard(data_store: DataStore):
    """Build the 4×2 conditioned-signal figure and return (fig, animation).

    The caller must keep a reference to the animation object to prevent GC.
    """
    fig = plt.figure(figsize=(13, 9))
    fig.suptitle("Conditioned Signals — Median → Savitzky-Golay → Kalman")
    gs = fig.add_gridspec(4, 2)

    cond_axes = {}
    cond_lines_raw = {}
    cond_lines_clean = {}

    slots = [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1), (3, 0)]
    for (key, label, unit), (r, c) in zip(COND_PARAMS, slots):
        ax = fig.add_subplot(gs[r, c])
        (l_raw,)   = ax.plot([], [], color="gray",     lw=0.8, alpha=0.5, label="raw")
        (l_clean,) = ax.plot([], [], color="tab:blue",  lw=1.6,           label="conditioned")
        ax.set_title(label)
        if unit:
            ax.set_ylabel(unit)
        ax.grid(True, alpha=0.4)
        ax.legend(loc="upper right", fontsize=8)
        cond_axes[key] = ax
        cond_lines_raw[key] = l_raw
        cond_lines_clean[key] = l_clean

    # Info panel in bottom-right slot
    ax_legend = fig.add_subplot(gs[3, 1])
    ax_legend.axis("off")
    ax_legend.text(
        0.02, 0.95,
        "Pipeline:\n"
        f"  1. Median filter   (kernel={MEDIAN_KERNEL})\n"
        f"  2. Savitzky-Golay  (window={SAVGOL_WINDOW}, poly={SAVGOL_POLY})\n"
        f"  3. Kalman 1-D      (q={KALMAN_Q}, r={KALMAN_R})",
        transform=ax_legend.transAxes, family="monospace",
        fontsize=10, va="top",
    )

    # ---- Animation callback ----
    def update(_frame):
        with data_store.lock:
            if not data_store.times:
                return ()
            x = list(data_store.times)
            snap = {key: list(data_store.buffers[key]) for key, _, _ in COND_PARAMS}

        for key, _, _ in COND_PARAMS:
            raw = snap[key]
            clean = condition_signal(raw)
            cond_lines_raw[key].set_data(x, raw)
            cond_lines_clean[key].set_data(x, clean)
            ax = cond_axes[key]
            ax.relim()
            ax.autoscale_view(scalex=True, scaley=True)

        return ()

    fig.autofmt_xdate()
    ani = FuncAnimation(fig, update, interval=PLOT_INTERVAL_MS,
                        cache_frame_data=False)
    return fig, ani
