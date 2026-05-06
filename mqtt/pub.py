"""
Point machine telemetry publisher (RDPMS FRS-aligned) with fault injection
and 3-class predictive-maintenance labels.

Published parameters (15 FRS values + 2 ML metadata fields):
  vpt_nwkr, vpt_rwkr           — 24 V detection feeds at relay room
  nwkr, rwkr, nwcr, rwcr       — digital relay states
  vpt_110_n, vpt_110_r         — 110 V supply at location box
  ipt_n, ipt_r                 — motor currents (Normal / Reverse)
  vpt_24_n, vpt_24_r           — 24 V at LOC after detection
  vib_x                        — vibration X
  tpt_n, tpt_r                 — derived stroke times
  fault                        — name of currently active fault, "" if none
  label                        — NORMAL | MAINTENANCE_ALERT | FAULT

Each fault has two phases:
  PRECURSOR (10-18 s)  — slow drift of relevant parameters into the FRS
                         min_safe warning band. Labelled MAINTENANCE_ALERT.
  ACTIVE   (3-20 s)    — parameter pushed past min_fail / abnormal range.
                         Labelled FAULT.

This gives a supervised ML dataset with leading indicators before each fault,
which is what predictive maintenance models need to learn.

Faults injected:
  LOW_VPT_NWKR     — 24 V detection feed sags (battery / wire degradation)
  LOW_VPT_110      — 110 V supply dip
  OBSTRUCTION      — stroke runs longer than max_safe TPT (8 s); current
                     stays elevated until forced clear
  OVER_CURRENT     — abnormally high motor current during stroke
  VIB_SPIKE        — abnormal vibration
  PHANTOM_CURRENT  — small idle current (leakage / hot wire)
  STUCK_NWKR_DROP  — NWKR position relay fails to pick up at Normal
"""

import paho.mqtt.client as mqtt
import time
import json
import os
import random
from cryptography.fernet import Fernet

KEY_FILE = "secret.key"
TOPIC = "rdpms/point-machine"
SAMPLE_PERIOD = 0.2  # 5 Hz

if not os.path.exists(KEY_FILE):
    with open(KEY_FILE, "wb") as f:
        f.write(Fernet.generate_key())

with open(KEY_FILE, "rb") as f:
    cipher = Fernet(f.read())

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect("broker.hivemq.com", 1883, 60)


# ---- Stroke state ----
position = "N"
stroking = False
stroke_target = None
stroke_start = 0.0
stroke_duration = 0.0


# ---- Fault config ----
FAULT_TYPES = (
    "LOW_VPT_NWKR",
    "LOW_VPT_110",
    "OBSTRUCTION",
    "OVER_CURRENT",
    "VIB_SPIKE",
    "PHANTOM_CURRENT",
    "STUCK_NWKR_DROP",
)
FAULT_DURATIONS = {
    "LOW_VPT_NWKR":     (8.0, 15.0),
    "LOW_VPT_110":      (8.0, 15.0),
    "OBSTRUCTION":      (10.0, 13.0),
    "OVER_CURRENT":     (5.0, 8.0),
    "VIB_SPIKE":        (3.0, 6.0),
    "PHANTOM_CURRENT":  (4.0, 8.0),
    "STUCK_NWKR_DROP":  (10.0, 20.0),
}
PRECURSOR_RANGE = (10.0, 18.0)
FAULT_TRIGGER_PROB = 0.008  # ~1 event per 25 s at 5 Hz

# Scheduled-but-not-yet-active fault (precursor phase)
scheduled_fault = None
precursor_start = 0.0
precursor_end = 0.0
precursor_duration = 0.0

# Active fault
active_fault = None
fault_end = 0.0


def maybe_schedule_fault():
    """Decide whether to start a precursor leading to a future fault."""
    global scheduled_fault, precursor_start, precursor_end, precursor_duration
    if scheduled_fault is not None or active_fault is not None:
        return
    if random.random() >= FAULT_TRIGGER_PROB:
        return
    scheduled_fault = random.choice(FAULT_TYPES)
    precursor_duration = random.uniform(*PRECURSOR_RANGE)
    precursor_start = time.time()
    precursor_end = precursor_start + precursor_duration
    print(f"[SCHED] >>> precursor for {scheduled_fault} ({precursor_duration:.1f}s drift)")


def promote_scheduled_to_active():
    """When precursor window ends, promote to active fault."""
    global scheduled_fault, active_fault, fault_end
    global stroking, stroke_target, stroke_start, stroke_duration
    if scheduled_fault is None or time.time() < precursor_end:
        return

    name = scheduled_fault
    lo, hi = FAULT_DURATIONS[name]
    duration = random.uniform(lo, hi)
    active_fault = name
    fault_end = time.time() + duration
    scheduled_fault = None

    if name in ("OBSTRUCTION", "OVER_CURRENT") and not stroking:
        stroking = True
        stroke_target = "R" if position == "N" else "N"
        stroke_start = time.time()
        if name == "OBSTRUCTION":
            stroke_duration = duration
        else:
            stroke_duration = random.uniform(5.0, 7.0)

    print(f"[FAULT] >>> {name} active for {duration:.1f}s")


def clear_fault_if_expired():
    global active_fault, fault_end
    if active_fault is not None and time.time() >= fault_end:
        print(f"[FAULT] <<< {active_fault} cleared")
        active_fault = None
        fault_end = 0.0


def precursor_progress():
    """0..1 if a fault is in precursor phase, else None."""
    if scheduled_fault is None:
        return None
    p = (time.time() - precursor_start) / max(precursor_duration, 0.001)
    return max(0.0, min(1.0, p))


def stroke_current_profile(t_norm: float, over_current: bool = False) -> float:
    scale = random.uniform(2.2, 2.8) if over_current else 1.0
    if t_norm < 0.06:
        return (9.5 + random.uniform(-0.4, 0.4)) * scale
    if t_norm < 0.85:
        return (4.5 + random.uniform(-0.3, 0.3)) * scale
    if t_norm < 1.0:
        tail = 4.5 * (1 - (t_norm - 0.85) / 0.15)
        return max(0.0, tail) * scale + random.uniform(-0.2, 0.2)
    return 0.0


def maybe_start_stroke():
    global stroking, stroke_target, stroke_start, stroke_duration
    if random.random() < 0.01:
        stroking = True
        stroke_target = "R" if position == "N" else "N"
        stroke_start = time.time()
        stroke_duration = random.uniform(5.0, 7.0)


def derive_label(rec):
    """3-class label from current state + FRS thresholds."""
    # FAULT class — active fault or breach past min_fail
    if active_fault is not None:
        return "FAULT"
    if rec["vpt_110_n"] < 82 or rec["vpt_110_r"] < 82:
        return "FAULT"
    if rec["nwkr"] and rec["vpt_nwkr"] < 18:
        return "FAULT"
    if rec["rwkr"] and rec["vpt_rwkr"] < 18:
        return "FAULT"
    if rec["tpt_n"] > 8 or rec["tpt_r"] > 8:
        return "FAULT"

    # MAINTENANCE_ALERT class — precursor drift or warning band
    if scheduled_fault is not None:
        return "MAINTENANCE_ALERT"
    if rec["vpt_110_n"] < 90 or rec["vpt_110_r"] < 90:
        return "MAINTENANCE_ALERT"
    if rec["nwkr"] and rec["vpt_nwkr"] < 21:
        return "MAINTENANCE_ALERT"
    if rec["rwkr"] and rec["vpt_rwkr"] < 21:
        return "MAINTENANCE_ALERT"
    if rec["tpt_n"] > 6 or rec["tpt_r"] > 6:
        return "MAINTENANCE_ALERT"
    if rec["vib_x"] > 0.7:
        return "MAINTENANCE_ALERT"

    return "NORMAL"


def tick():
    global stroking, stroke_target, position

    clear_fault_if_expired()
    promote_scheduled_to_active()
    maybe_schedule_fault()

    now = time.time()

    if not stroking:
        maybe_start_stroke()

    if stroking:
        elapsed = now - stroke_start
        if elapsed >= stroke_duration:
            position = stroke_target
            stroking = False
            stroke_target = None
            ipt_active = 0.0
            tpt_value = 0.0
        else:
            over_current = (active_fault == "OVER_CURRENT")
            if active_fault == "OBSTRUCTION":
                ipt_active = 5.0 + random.uniform(-0.4, 0.4)
            else:
                ipt_active = stroke_current_profile(elapsed / stroke_duration, over_current)
            tpt_value = elapsed
    else:
        ipt_active = 0.0
        tpt_value = 0.0

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
    p = precursor_progress()
    if p is not None:
        if scheduled_fault == "LOW_VPT_NWKR":
            if nwkr:
                vpt_nwkr -= 4.0 * p   # 24 -> ~20
                vpt_24_n -= 4.0 * p
            if rwkr:
                vpt_rwkr -= 4.0 * p
                vpt_24_r -= 4.0 * p
        elif scheduled_fault == "LOW_VPT_110":
            vpt_110_n -= 21.0 * p     # 110 -> ~89
            vpt_110_r -= 21.0 * p
        elif scheduled_fault == "VIB_SPIKE":
            vib_x += 0.65 * p         # 0.05 -> ~0.7
        elif scheduled_fault == "PHANTOM_CURRENT" and not stroking:
            ipt_n += 0.15 * p
        elif scheduled_fault == "STUCK_NWKR_DROP" and nwkr:
            vpt_nwkr -= 4.0 * p
            vpt_24_n -= 4.0 * p
        elif scheduled_fault == "OVER_CURRENT":
            vib_x += 0.3 * p
            if not stroking:
                ipt_n += 0.05 * p
                ipt_r += 0.05 * p
        elif scheduled_fault == "OBSTRUCTION":
            vib_x += 0.4 * p
            if not stroking:
                ipt_n += 0.08 * p

    # ---- Active-fault overrides (push past min_fail) ----
    if active_fault == "LOW_VPT_NWKR":
        if nwkr:
            vpt_nwkr = 15.5 + random.uniform(-0.6, 0.6)
            vpt_24_n = 15.0 + random.uniform(-0.6, 0.6)
        if rwkr:
            vpt_rwkr = 15.5 + random.uniform(-0.6, 0.6)
            vpt_24_r = 15.0 + random.uniform(-0.6, 0.6)
    if active_fault == "LOW_VPT_110":
        vpt_110_n = 78.0 + random.uniform(-1.5, 1.5)
        vpt_110_r = 78.0 + random.uniform(-1.5, 1.5)
    if active_fault == "VIB_SPIKE":
        vib_x = 0.85 + random.uniform(-0.1, 0.1)
    if active_fault == "PHANTOM_CURRENT" and not stroking:
        ipt_n = 0.4 + random.uniform(-0.05, 0.05)
    if active_fault == "STUCK_NWKR_DROP":
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
        "fault":     active_fault or "",
    }
    record["label"] = derive_label(record)
    return record


i = 0
try:
    while True:
        data = tick()
        payload = cipher.encrypt(json.dumps(data).encode())
        client.publish(TOPIC, payload)

        if i % 5 == 0 or stroking or active_fault or scheduled_fault:
            tag = f"STROKE->{stroke_target}" if stroking else f"IDLE@{position}"
            sched_tag = f" SCHED={scheduled_fault}" if scheduled_fault else ""
            flt = f" FAULT={active_fault}" if active_fault else ""
            print(f"[{i:05d}] {tag:12s}  I_N={data['ipt_n']:.2f}  I_R={data['ipt_r']:.2f}  "
                  f"V110_N={data['vpt_110_n']:.1f}  TPT_N={data['tpt_n']:.1f}  "
                  f"label={data['label']}{sched_tag}{flt}")
        i += 1
        time.sleep(SAMPLE_PERIOD)
except KeyboardInterrupt:
    print("\nStopping publisher...")
finally:
    client.disconnect()
