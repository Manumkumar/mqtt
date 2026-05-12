"""
Correlation dashboard — cross-parameter scatter plots.

Plots live relationships between:
  - Voltage vs Current   (V110 N/R vs IPT N/R)
  - Voltage vs Vibration (V110 N/R & VPT 24 N/R vs VIB X)
  - Current vs Vibration (IPT N/R vs VIB X)

Helps identify coupled degradation modes that single-parameter
monitoring might miss (e.g., simultaneous voltage sag + current rise
indicates supply-side issues rather than mechanical faults).
"""

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

from subscriber.config import PLOT_INTERVAL_MS
from subscriber.data_store import DataStore


def create_correlation_dashboard(data_store: DataStore):
    """Build the 3×3 correlation figure and return (fig, animation).

    Layout
    ------
    Row 0 — Voltage vs Current   : V110_N vs IPT_N  |  V110_R vs IPT_R  |  VPT_24_N vs IPT_N
    Row 1 — Voltage vs Vibration : V110_N vs VIB_X   |  V110_R vs VIB_X   |  VPT_24_N vs VIB_X
    Row 2 — Current vs Vibration : IPT_N vs VIB_X    |  IPT_R vs VIB_X    |  VPT_24_R vs VIB_X
    """
    fig, axes = plt.subplots(3, 3, figsize=(14, 10))
    fig.canvas.manager.set_window_title("Correlation Dashboard")
    fig.suptitle("Cross-Parameter Correlations — Voltage · Current · Vibration",
                 fontsize=13, fontweight="bold")

    # ---- Plot definitions: (x_param, y_param, xlabel, ylabel, color) ----
    plot_defs = [
        # Row 0 — Voltage vs Current
        ("vpt_110_n", "ipt_n", "V110 N (V)",   "IPT N (A)",  "tab:blue"),
        ("vpt_110_r", "ipt_r", "V110 R (V)",   "IPT R (A)",  "tab:cyan"),
        ("vpt_24_n",  "ipt_n", "VPT 24 N (V)", "IPT N (A)",  "tab:purple"),

        # Row 1 — Voltage vs Vibration
        ("vpt_110_n", "vib_x", "V110 N (V)",   "VIB X",      "tab:orange"),
        ("vpt_110_r", "vib_x", "V110 R (V)",   "VIB X",      "tab:red"),
        ("vpt_24_n",  "vib_x", "VPT 24 N (V)", "VIB X",      "tab:olive"),

        # Row 2 — Current vs Vibration
        ("ipt_n",     "vib_x", "IPT N (A)",    "VIB X",      "tab:green"),
        ("ipt_r",     "vib_x", "IPT R (A)",    "VIB X",      "tab:brown"),
        ("vpt_24_r",  "vib_x", "VPT 24 R (V)", "VIB X",      "tab:pink"),
    ]

    row_titles = [
        "Voltage vs Current",
        "Voltage vs Vibration",
        "Current vs Vibration",
    ]

    scatters = []     # trail scatter artists
    latest_dots = []  # latest-point marker artists

    for idx, (x_param, y_param, xlabel, ylabel, color) in enumerate(plot_defs):
        row, col = divmod(idx, 3)
        ax = axes[row, col]

        # Trail: semi-transparent scatter
        sc = ax.scatter([], [], s=8, alpha=0.35, color=color, edgecolors="none")
        # Latest point: larger, fully opaque, with border
        dot = ax.scatter([], [], s=60, color=color, edgecolors="black",
                         linewidths=0.8, zorder=5)

        ax.set_xlabel(xlabel, fontsize=9)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.set_title(f"{xlabel.split('(')[0].strip()} vs {ylabel.split('(')[0].strip()}",
                     fontsize=10)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=8)

        scatters.append(sc)
        latest_dots.append(dot)

    # Row annotations (left side)
    for row, title in enumerate(row_titles):
        axes[row, 0].annotate(
            title, xy=(-0.35, 0.5), xycoords="axes fraction",
            fontsize=11, fontweight="bold", rotation=90,
            ha="center", va="center", color="grey",
        )

    def update(_frame):
        with data_store.lock:
            if not data_store.times:
                return ()
            snap = {p: list(data_store.buffers[p]) for p in data_store.buffers}

        for idx, (x_param, y_param, *_rest) in enumerate(plot_defs):
            x_data = snap.get(x_param, [])
            y_data = snap.get(y_param, [])

            if not x_data or not y_data:
                continue

            n = min(len(x_data), len(y_data))
            xv = x_data[:n]
            yv = y_data[:n]

            # Update trail scatter (all points)
            import numpy as np
            offsets = np.column_stack([xv, yv])
            scatters[idx].set_offsets(offsets)

            # Update latest-point marker
            latest_dots[idx].set_offsets([[xv[-1], yv[-1]]])

            # Re-fit axes with a small margin
            row, col = divmod(idx, 3)
            ax = axes[row, col]
            x_min, x_max = min(xv), max(xv)
            y_min, y_max = min(yv), max(yv)
            x_margin = max((x_max - x_min) * 0.08, 0.5)
            y_margin = max((y_max - y_min) * 0.08, 0.05)
            ax.set_xlim(x_min - x_margin, x_max + x_margin)
            ax.set_ylim(y_min - y_margin, y_max + y_margin)

        return ()

    fig.tight_layout(rect=[0.04, 0.0, 1.0, 0.95])
    ani = FuncAnimation(fig, update, interval=PLOT_INTERVAL_MS,
                        cache_frame_data=False)
    return fig, ani
