"""
Telemetry record generation.

Builds one 15-parameter telemetry record per call by composing:
  - base parameter values from stroke state
  - precursor drift from the fault engine
  - active-fault overrides
"""

import time
import random

from publisher.fault_engine import FaultEngine
from publisher.stroke import StrokeManager
from publisher.labeling import derive_label


def generate_record(fault_engine: FaultEngine, stroke_mgr: StrokeManager) -> dict:
    """Produce one complete telemetry sample.

    Parameters
    ----------
    fault_engine : FaultEngine
        Current fault-injection state (precursor / active / clear).
    stroke_mgr : StrokeManager
        Current stroke state (position, stroking, motor current).

    Returns
    -------
    dict
        Record with 15 FRS parameters + ``fault`` + ``label`` fields.
    """
    # Advance state machines
    fault_engine.clear_fault_if_expired()
    fault_engine.promote_scheduled_to_active(stroke_mgr)
    fault_engine.maybe_schedule_fault()

    if not stroke_mgr.stroking:
        stroke_mgr.maybe_start_stroke()

    ipt_active, tpt_value = stroke_mgr.update(fault_engine.active_fault)

    now = time.time()
    stroking = stroke_mgr.stroking
    position = stroke_mgr.position
    stroke_target = stroke_mgr.stroke_target

    # ---- Base parameter values ----
    nwkr = 1 if (not stroking and position == "N") else 0
    rwkr = 1 if (not stroking and position == "R") else 0
    nwcr = 1 if (stroking and stroke_target == "N") else 0
    rwcr = 1 if (stroking and stroke_target == "R") else 0

    vpt_nwkr = (24.0 + random.uniform(-0.2, 0.2)) if nwkr else random.uniform(0, 0.5)
    vpt_rwkr = (24.0 + random.uniform(-0.2, 0.2)) if rwkr else random.uniform(0, 0.5)

    load_drop = 4.0 if stroking else 0.0
    base_n = 110.0 - (load_drop if stroke_target == "N" else 0.0)
    base_r = 110.0 - (load_drop if stroke_target == "R" else 0.0)
    vpt_110_n = base_n + random.uniform(-0.5, 0.5)
    vpt_110_r = base_r + random.uniform(-0.5, 0.5)

    ipt_n = ipt_active if stroke_target == "N" else random.uniform(0.0, 0.05)
    ipt_r = ipt_active if stroke_target == "R" else random.uniform(0.0, 0.05)

    vpt_24_n = (24.0 + random.uniform(-0.2, 0.2)) if nwkr else random.uniform(0, 0.3)
    vpt_24_r = (24.0 + random.uniform(-0.2, 0.2)) if rwkr else random.uniform(0, 0.3)

    vib_base = 0.5 if stroking else 0.05
    vib_x = vib_base + random.uniform(-0.03, 0.03)

    tpt_n = tpt_value if stroke_target == "N" else 0.0
    tpt_r = tpt_value if stroke_target == "R" else 0.0

    # ---- Precursor drift (slow movement into warning band) ----
    p = fault_engine.precursor_progress()
    scheduled = fault_engine.scheduled_fault
    if p is not None:
        if scheduled == "LOW_VPT_NWKR":
            if nwkr:
                vpt_nwkr -= 4.0 * p
                vpt_24_n -= 4.0 * p
            if rwkr:
                vpt_rwkr -= 4.0 * p
                vpt_24_r -= 4.0 * p
        elif scheduled == "LOW_VPT_110":
            vpt_110_n -= 21.0 * p
            vpt_110_r -= 21.0 * p
        elif scheduled == "VIB_SPIKE":
            vib_x += 0.65 * p
        elif scheduled == "PHANTOM_CURRENT" and not stroking:
            ipt_n += 0.15 * p
        elif scheduled == "STUCK_NWKR_DROP" and nwkr:
            vpt_nwkr -= 4.0 * p
            vpt_24_n -= 4.0 * p
        elif scheduled == "OVER_CURRENT":
            vib_x += 0.3 * p
            if not stroking:
                ipt_n += 0.05 * p
                ipt_r += 0.05 * p
        elif scheduled == "OBSTRUCTION":
            vib_x += 0.4 * p
            if not stroking:
                ipt_n += 0.08 * p

    # ---- Active-fault overrides (push past min_fail) ----
    active = fault_engine.active_fault
    if active == "LOW_VPT_NWKR":
        if nwkr:
            vpt_nwkr = 15.5 + random.uniform(-0.6, 0.6)
            vpt_24_n = 15.0 + random.uniform(-0.6, 0.6)
        if rwkr:
            vpt_rwkr = 15.5 + random.uniform(-0.6, 0.6)
            vpt_24_r = 15.0 + random.uniform(-0.6, 0.6)
    if active == "LOW_VPT_110":
        vpt_110_n = 78.0 + random.uniform(-1.5, 1.5)
        vpt_110_r = 78.0 + random.uniform(-1.5, 1.5)
    if active == "VIB_SPIKE":
        vib_x = 0.85 + random.uniform(-0.1, 0.1)
    if active == "PHANTOM_CURRENT" and not stroking:
        ipt_n = 0.4 + random.uniform(-0.05, 0.05)
    if active == "STUCK_NWKR_DROP":
        nwkr = 0
        vpt_nwkr = random.uniform(0.0, 0.5)
        vpt_24_n = random.uniform(0.0, 0.3)

    record = {
        "timestamp": now,
        "vpt_nwkr":  round(vpt_nwkr, 2),
        "vpt_rwkr":  round(vpt_rwkr, 2),
        "nwkr":      nwkr,
        "rwkr":      rwkr,
        "nwcr":      nwcr,
        "rwcr":      rwcr,
        "vpt_110_n": round(vpt_110_n, 2),
        "vpt_110_r": round(vpt_110_r, 2),
        "ipt_n":     round(ipt_n, 3),
        "ipt_r":     round(ipt_r, 3),
        "vpt_24_n":  round(vpt_24_n, 2),
        "vpt_24_r":  round(vpt_24_r, 2),
        "vib_x":     round(vib_x, 3),
        "tpt_n":     round(tpt_n, 2),
        "tpt_r":     round(tpt_r, 2),
        "fault":     fault_engine.active_fault or "",
    }
    record["label"] = derive_label(record, fault_engine)
    return record
