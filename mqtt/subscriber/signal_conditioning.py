"""
Signal conditioning pipeline: Median → Savitzky-Golay → Kalman.

Removes spikes, smooths the waveform while preserving shape, and provides
an optimal estimate of the true signal value.
"""

from scipy.signal import medfilt, savgol_filter

# ---- Pipeline parameters ----
MEDIAN_KERNEL = 5
SAVGOL_WINDOW = 11
SAVGOL_POLY = 2
KALMAN_Q = 1e-3   # process noise (small = trust prediction)
KALMAN_R = 0.5    # measurement noise


def kalman_1d(seq: list, q: float = KALMAN_Q, r: float = KALMAN_R) -> list:
    """Constant-value 1-D Kalman estimator."""
    if not seq:
        return []
    x = seq[0]
    p = 1.0
    out = []
    for z in seq:
        p += q
        k = p / (p + r)
        x = x + k * (z - x)
        p = (1.0 - k) * p
        out.append(x)
    return out


def condition_signal(arr) -> list:
    """Apply full pipeline: median → Savitzky-Golay → Kalman.

    Returns a list the same length as *arr*.
    """
    if not arr:
        return []
    n = len(arr)
    a = list(arr)
    if n >= MEDIAN_KERNEL:
        a = list(medfilt(a, kernel_size=MEDIAN_KERNEL))
    if n >= SAVGOL_WINDOW:
        a = list(savgol_filter(a, SAVGOL_WINDOW, SAVGOL_POLY))
    return kalman_1d(a)
