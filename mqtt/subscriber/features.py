"""
Time-domain feature extraction for motor-current signals.

Computes rolling statistics from the IPT (motor current) buffers:
  - **Peak** — maximum absolute current in the window
  - **Mean** — arithmetic mean current
  - **RMS**  — root-mean-square current (proportional to power dissipation)

These features are computed separately for Normal-side (IPT N) and
Reverse-side (IPT R) currents.
"""

import math


def compute_features(values: list) -> dict:
    """Compute peak, mean, and RMS for a list of numeric samples.

    Parameters
    ----------
    values : list[float]
        Rolling buffer snapshot (may be empty).

    Returns
    -------
    dict
        ``{"peak": float, "mean": float, "rms": float}``
        All zero if *values* is empty.
    """
    if not values:
        return {"peak": 0.0, "mean": 0.0, "rms": 0.0}

    peak = max(abs(v) for v in values)
    mean = sum(values) / len(values)
    rms = math.sqrt(sum(v * v for v in values) / len(values))

    return {"peak": round(peak, 4), "mean": round(mean, 4), "rms": round(rms, 4)}
