"""
Live point-machine telemetry subscriber + dashboard.

Decrypts the 15-parameter envelope produced by pub.py and renders a 3x3
matplotlib dashboard with FRS-defined safety thresholds drawn as horizontal
lines (orange = min_safe, red = min_fail; for TPT the line is max_safe).
"""

from subscriber.main import run

if __name__ == "__main__":
    run()
