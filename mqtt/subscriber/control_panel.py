"""
Control panel — small matplotlib window with toggle buttons to show/hide
each dashboard window.

Works with TkAgg (default on Windows) and Qt backends.
"""

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.widgets import CheckButtons


def _hide_window(fig):
    """Hide the OS window for *fig* (backend-aware)."""
    backend = matplotlib.get_backend().lower()
    win = fig.canvas.manager.window
    if "tkagg" in backend:
        win.withdraw()
    elif "qt" in backend:
        win.hide()
    else:
        # Fallback: try both
        for method in ("withdraw", "hide"):
            if hasattr(win, method):
                getattr(win, method)()
                break


def _show_window(fig):
    """Show / restore the OS window for *fig* (backend-aware)."""
    backend = matplotlib.get_backend().lower()
    win = fig.canvas.manager.window
    if "tkagg" in backend:
        win.deiconify()
    elif "qt" in backend:
        win.show()
    else:
        for method in ("deiconify", "show"):
            if hasattr(win, method):
                getattr(win, method)()
                break


def create_control_panel(dashboards: dict):
    """Build a control panel with checkboxes to toggle dashboard visibility.

    Parameters
    ----------
    dashboards : dict
        ``{label: (fig, animation)}`` for each dashboard window.
        Labels are used as checkbox text.

    Returns
    -------
    (fig, check_buttons)
        Caller must keep references to prevent GC.
    """
    labels = list(dashboards.keys())
    initial_states = [True] * len(labels)

    # Track visibility ourselves (fig.get_visible() doesn't reflect OS state)
    visible_state = {label: True for label in labels}

    fig, ax = plt.subplots(figsize=(4, 2.5))
    fig.canvas.manager.set_window_title("Dashboard Control Panel")
    ax.set_title("Toggle Dashboards", fontsize=12, fontweight="bold", pad=10)

    check = CheckButtons(ax, labels, initial_states)

    # Style the labels
    for lbl in check.labels:
        lbl.set_fontsize(10)

    def toggle(label):
        dash_fig, dash_ani = dashboards[label]
        currently_visible = visible_state[label]

        if currently_visible:
            # Hide the window
            dash_ani.event_source.stop()
            _hide_window(dash_fig)
            visible_state[label] = False
        else:
            # Show the window
            _show_window(dash_fig)
            dash_ani.event_source.start()
            dash_fig.canvas.draw_idle()
            visible_state[label] = True

    check.on_clicked(toggle)

    fig.tight_layout()
    return fig, check
