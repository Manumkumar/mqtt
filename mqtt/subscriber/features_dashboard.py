"""
Time-domain features dashboard (separate matplotlib window).

Plots rolling peak, mean, and RMS values for the motor-current signals
(IPT N and IPT R) using data from the shared DataStore.
"""

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

from subscriber.config import PLOT_INTERVAL_MS
from subscriber.data_store import DataStore
from subscriber.features import compute_features


def create_features_dashboard(data_store: DataStore):

    fig, axes = plt.subplots(3, 2, figsize=(12, 8), sharex=True)
    fig.suptitle("Time-Domain Features — Motor Current (IPT)")

    feature_names = ["peak", "mean", "rms"]
    feature_labels = ["Peak (A)", "Mean (A)", "RMS (A)"]
    sides = [("ipt_n", "IPT N"), ("ipt_r", "IPT R")]
    colors = {"peak": "tab:red", "mean": "tab:blue", "rms": "tab:green"}

    # Create line objects: lines[feat][side_idx]
    lines = {}
    for row, (feat, ylabel) in enumerate(zip(feature_names, feature_labels)):
        lines[feat] = []
        for col, (param, side_label) in enumerate(sides):
            ax = axes[row, col]
            (line,) = ax.plot([], [], color=colors[feat], lw=1.6,
                              label=f"{feat.upper()} {side_label}")
            ax.set_ylabel(ylabel)
            ax.set_title(f"{feat.upper()} — {side_label}")
            ax.grid(True, alpha=0.4)
            ax.legend(loc="upper right", fontsize=8)
            lines[feat].append(line)

    # Bottom row gets x-labels
    for col in range(2):
        axes[2, col].set_xlabel("Time")

    # Rolling feature buffers (populated incrementally in the animation callback)
    from collections import deque
    max_pts = data_store.times.maxlen
    feat_times = deque(maxlen=max_pts)
    feat_bufs = {
        feat: {side: deque(maxlen=max_pts) for side in ("ipt_n", "ipt_r")}
        for feat in feature_names
    }
    prev_len = {"n": 0}  # track how many samples we've already processed

    def update(_frame):
        with data_store.lock:
            if not data_store.times:
                return ()
            x = list(data_store.times)
            ipt_n_all = list(data_store.buffers["ipt_n"])
            ipt_r_all = list(data_store.buffers["ipt_r"])

        cur_len = len(x)

        # Re-compute features over the full rolling window each frame
        # (cheap — MAX_POINTS is only 300)
        feat_times.clear()
        for feat in feature_names:
            for side in ("ipt_n", "ipt_r"):
                feat_bufs[feat][side].clear()

        for i in range(cur_len):
            feat_times.append(x[i])
            # Use all samples up to index i+1 as the running window
            window_n = ipt_n_all[: i + 1]
            window_r = ipt_r_all[: i + 1]

            fn = compute_features(window_n)
            fr = compute_features(window_r)
            for feat in feature_names:
                feat_bufs[feat]["ipt_n"].append(fn[feat])
                feat_bufs[feat]["ipt_r"].append(fr[feat])

        prev_len["n"] = cur_len
        t = list(feat_times)

        for row, feat in enumerate(feature_names):
            for col, side in enumerate(("ipt_n", "ipt_r")):
                lines[feat][col].set_data(t, list(feat_bufs[feat][side]))
                ax = axes[row, col]
                ax.relim()
                ax.autoscale_view(scalex=True, scaley=True)

        return ()

    fig.autofmt_xdate()
    ani = FuncAnimation(fig, update, interval=PLOT_INTERVAL_MS,
                        cache_frame_data=False)
    return fig, ani
