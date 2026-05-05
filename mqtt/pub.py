"""
Point machine telemetry publisher (RDPMS FRS-aligned).

Publishes 15 parameters defined in the FRS:
- 6 analog voltages (VPT NWKR/RWKR, VPT 110 N/R, VPT 24 N/R LOC)
- 4 digital relay states (NWKR, RWKR, NWCR, RWCR)
- 2 motor currents (IPT N, IPT R)
- 1 vibration (Vibration X, optional)
- 2 derived operation times (TPT N, TPT R)

Includes a stroke-event state machine: idle most of the time, occasionally
trigger a Normal->Reverse or Reverse->Normal stroke. During a stroke the
contactor relay engages, motor current pulses (inrush -> run -> tail), the
position relay drops, and TPT counts up. After stroke completion the new
position relay picks up and 24 V detection feeds reflect the new state.
"""

import paho.mqtt.client as mqtt
import time
import json
import os
import random
from cryptography.fernet import Fernet

KEY_FILE = "secret.key"
TOPIC = "rdpms/point-machine"
SAMPLE_PERIOD = 0.2  # 5 Hz — enough resolution to capture current signature

if not os.path.exists(KEY_FILE):
    with open(KEY_FILE, "wb") as f:
        f.write(Fernet.generate_key())

with open(KEY_FILE, "rb") as f:
    cipher = Fernet(f.read())

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect("broker.hivemq.com", 1883, 60)


# Point machine state
position = "N"           # Settled position: "N" or "R"
stroking = False
stroke_target = None     # Direction of in-progress stroke: "N" or "R"
stroke_start = 0.0
stroke_duration = 0.0    # Seconds — randomised per stroke (5..7 s typical)


def stroke_current_profile(t_norm: float) -> float:
    """Approximate motor current signature, t_norm in [0,1]."""
    if t_norm < 0.06:
        return 9.5 + random.uniform(-0.4, 0.4)        # inrush spike
    if t_norm < 0.85:
        return 4.5 + random.uniform(-0.3, 0.3)        # steady run
    if t_norm < 1.0:
        tail = 4.5 * (1 - (t_norm - 0.85) / 0.15)
        return max(0.0, tail) + random.uniform(-0.2, 0.2)
    return 0.0


def maybe_start_stroke():
    global stroking, stroke_target, stroke_start, stroke_duration
    # ~4% chance per tick at 5 Hz ≈ 1 stroke every 5 s on average
    if random.random() < 0.01:
        stroking = True
        stroke_target = "R" if position == "N" else "N"
        stroke_start = time.time()
        stroke_duration = random.uniform(5.0, 7.0)


def tick():
    """Advance state machine, return one telemetry record."""
    global stroking, stroke_target, position

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
            ipt_active = stroke_current_profile(elapsed / stroke_duration)
            tpt_value = elapsed
    else:
        ipt_active = 0.0
        tpt_value = 0.0

    nwkr = 1 if (not stroking and position == "N") else 0
    rwkr = 1 if (not stroking and position == "R") else 0
    nwcr = 1 if (stroking and stroke_target == "N") else 0
    rwcr = 1 if (stroking and stroke_target == "R") else 0

    # 24 V at relay room reflects detected position
    vpt_nwkr = (24.0 + random.uniform(-0.2, 0.2)) if nwkr else random.uniform(0, 0.5)
    vpt_rwkr = (24.0 + random.uniform(-0.2, 0.2)) if rwkr else random.uniform(0, 0.5)

    # 110 V at location box. Drops while motor draws current on that direction.
    load_drop = 4.0 if stroking else 0.0
    base_n = 110.0 - (load_drop if stroke_target == "N" else 0.0)
    base_r = 110.0 - (load_drop if stroke_target == "R" else 0.0)
    vpt_110_n = base_n + random.uniform(-0.5, 0.5)
    vpt_110_r = base_r + random.uniform(-0.5, 0.5)

    # Motor current — only flows in stroking direction
    ipt_n = ipt_active if stroke_target == "N" else random.uniform(0.0, 0.05)
    ipt_r = ipt_active if stroke_target == "R" else random.uniform(0.0, 0.05)

    # 24 V going back to RR after detection at LOC
    vpt_24_n = (24.0 + random.uniform(-0.2, 0.2)) if nwkr else random.uniform(0, 0.3)
    vpt_24_r = (24.0 + random.uniform(-0.2, 0.2)) if rwkr else random.uniform(0, 0.3)

    # Vibration: low idle, higher during stroke
    vib_base = 0.5 if stroking else 0.05
    vib_x = vib_base + random.uniform(-0.03, 0.03)

    # Derived TPT
    tpt_n = tpt_value if stroke_target == "N" else 0.0
    tpt_r = tpt_value if stroke_target == "R" else 0.0

    return {
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
    }


i = 0
try:
    while True:
        data = tick()
        payload = cipher.encrypt(json.dumps(data).encode())
        client.publish(TOPIC, payload)

        if i % 5 == 0 or stroking:
            tag = f"STROKE->{stroke_target}" if stroking else f"IDLE@{position}"
            print(f"[{i:05d}] {tag:12s}  I_N={data['ipt_n']:.2f}  I_R={data['ipt_r']:.2f}  "
                  f"V110_N={data['vpt_110_n']:.1f}  TPT_N={data['tpt_n']:.1f}")
        i += 1
        time.sleep(SAMPLE_PERIOD)
except KeyboardInterrupt:
    print("\nStopping publisher...")
finally:
    client.disconnect()
