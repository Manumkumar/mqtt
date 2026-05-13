"""Time-features dashboard — 4th matplotlib window.

Shows per-stroke operation time, cumulative voltage-drop seconds per rail,
stroke vs slip count, and a status text panel.
"""

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

from subscriber.config import PLOT_INTERVAL_MS, MAX_SAFE_TPT, VDROP_RAILS
from subscriber.data_store import DataStore


def create_time_features_dashboard(data_store: DataStore):
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle("System-Level Time Features")
    fig.canvas.manager.set_window_title("Time Features")

    ax_scatter, ax_vdrop = axes[0, 0], axes[0, 1]
    ax_counts,  ax_text  = axes[1, 0], axes[1, 1]

    # (0,0) Per-stroke operation time
    ax_scatter.set_title("Operation time per stroke")
    ax_scatter.set_xlabel("Event #")
    ax_scatter.set_ylabel("op_time (s)")
    ax_scatter.axhline(MAX_SAFE_TPT, color="red", linestyle="--", lw=1,
                       label=f"max_safe = {MAX_SAFE_TPT} s")
    ax_scatter.grid(True, alpha=0.4)
    ax_scatter.legend(loc="upper left", fontsize=8)
    scatter = ax_scatter.scatter([], [], c=[], cmap="coolwarm", vmin=0, vmax=1, s=30)

    # (0,1) Voltage-drop cumulative seconds — 6 bars
    ax_vdrop.set_title("Voltage drop — cumulative seconds")
    ax_vdrop.set_ylabel("seconds below min_safe")
    rail_labels = list(VDROP_RAILS)
    bars_vdrop = ax_vdrop.bar(range(len(rail_labels)), [0.0] * len(rail_labels),
                              color="tab:orange")
    ax_vdrop.set_xticks(range(len(rail_labels)))
    ax_vdrop.set_xticklabels(rail_labels, rotation=30, ha="right", fontsize=8)
    ax_vdrop.grid(True, alpha=0.4, axis="y")

    # (1,0) Stroke vs slip count
    ax_counts.set_title("Stroke count vs slip count")
    bars_counts = ax_counts.bar(["strokes", "slips"], [0, 0],
                                color=["tab:blue", "tab:red"])
    ax_counts.grid(True, alpha=0.4, axis="y")

    # (1,1) Status text panel
    ax_text.set_title("Status")
    ax_text.axis("off")
    status_text = ax_text.text(0.02, 0.95, "", transform=ax_text.transAxes,
                               fontsize=10, family="monospace",
                               va="top", ha="left")

    def update(_frame):
        with data_store.lock:
            events = list(data_store.event_buf)
            counters = {
                "stroke_count": data_store.counters["stroke_count"],
                "slip_count":   data_store.counters["slip_count"],
                "last_op_time": data_store.counters["last_op_time"],
                "vdrop_seconds": dict(data_store.counters["vdrop_seconds"]),
            }

        # Scatter
        if events:
            xs = list(range(1, len(events) + 1))
            ys = [e["op_time"] for e in events]
            colors = [1.0 if e["slipping"] else 0.0 for e in events]
            scatter.set_offsets(list(zip(xs, ys)))
            scatter.set_array(colors)
            ax_scatter.relim()
            ax_scatter.autoscale_view()

        # Vdrop bars
        for bar, rail in zip(bars_vdrop, rail_labels):
            bar.set_height(counters["vdrop_seconds"].get(rail, 0.0))
        ax_vdrop.relim()
        ax_vdrop.autoscale_view(scalex=False, scaley=True)

        # Count bars
        bars_counts[0].set_height(counters["stroke_count"])
        bars_counts[1].set_height(counters["slip_count"])
        ax_counts.relim()
        ax_counts.autoscale_view(scalex=False, scaley=True)

        # Status text
        ratio = (counters["slip_count"] / counters["stroke_count"] * 100.0
                 if counters["stroke_count"] else 0.0)
        last = events[-1] if events else None
        last_side = last["side"] if last else "-"
        last_ts = f"{last['timestamp']:.2f}" if last else "-"
        last_slipped = last["slipping"] if last else False
        lines = [
            f"strokes      : {counters['stroke_count']}",
            f"slips        : {counters['slip_count']}  ({ratio:5.1f}%)",
            f"last op_time : {counters['last_op_time']:.2f} s",
            f"last event   : side={last_side}  ts={last_ts}",
        ]
        status_text.set_text("\n".join(lines))
        status_text.set_color("red" if last_slipped else "black")

        return ()

    ani = FuncAnimation(fig, update, interval=PLOT_INTERVAL_MS,
                        cache_frame_data=False)
    return fig, ani
