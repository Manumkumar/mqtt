"""
Three-class labelling logic based on FRS thresholds.

Labels:
  NORMAL              — all parameters within safe operating range.
  MAINTENANCE_ALERT   — precursor drift or parameter in warning band.
  FAULT               — active fault or parameter past failure threshold.
"""


def derive_label(record: dict, fault_engine) -> str:
    """Classify a telemetry record into one of three maintenance labels."""

    # ---- FAULT class — active fault or breach past min_fail ----
    if fault_engine.active_fault is not None:
        return "FAULT"
    if record["vpt_110_n"] < 82 or record["vpt_110_r"] < 82:
        return "FAULT"
    if record["nwkr"] and record["vpt_nwkr"] < 18:
        return "FAULT"
    if record["rwkr"] and record["vpt_rwkr"] < 18:
        return "FAULT"
    if record["tpt_n"] > 8 or record["tpt_r"] > 8:
        return "FAULT"

    # ---- MAINTENANCE_ALERT class — precursor drift or warning band ----
    if fault_engine.scheduled_fault is not None:
        return "MAINTENANCE_ALERT"
    if record["vpt_110_n"] < 90 or record["vpt_110_r"] < 90:
        return "MAINTENANCE_ALERT"
    if record["nwkr"] and record["vpt_nwkr"] < 21:
        return "MAINTENANCE_ALERT"
    if record["rwkr"] and record["vpt_rwkr"] < 21:
        return "MAINTENANCE_ALERT"
    if record["tpt_n"] > 6 or record["tpt_r"] > 6:
        return "MAINTENANCE_ALERT"
    if record["vib_x"] > 0.7:
        return "MAINTENANCE_ALERT"

    return "NORMAL"
