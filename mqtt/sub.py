"""
Live point-machine telemetry subscriber + dashboard.

Decrypts the 15-parameter envelope produced by pub.py and renders a 3x3
matplotlib dashboard with FRS-defined safety thresholds drawn as horizontal
lines (orange = min_safe, red = min_fail; for TPT the line is max_safe).
"""

import paho.mqtt.client as mqtt
import json
import threading
from collections import deque
from datetime import datetime
from cryptography.fernet import Fernet
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

KEY_FILE = "secret.key"
DATA_FILE = "received_data.jsonl"   # JSONL: one record per line, O(1) append
MAX_POINTS = 300                    # last ~60 s at 5 Hz
PLOT_INTERVAL_MS = 250              # GUI refresh period
LOG_EVERY = 10                      # print 1 in N messages to keep stdout cheap

with open(KEY_FILE, "rb") as f:
    cipher = Fernet(f.read())

PARAMS = (
    "vpt_nwkr", "vpt_rwkr",
    "nwkr", "rwkr", "nwcr", "rwcr",
    "vpt_110_n", "vpt_110_r",
    "ipt_n", "ipt_r",
    "vpt_24_n", "vpt_24_r",
    "vib_x",
    "tpt_n", "tpt_r",
)

times = deque(maxlen=MAX_POINTS)
buffers = {p: deque(maxlen=MAX_POINTS) for p in PARAMS}
fault_buf = deque(maxlen=MAX_POINTS)
label_buf = deque(maxlen=MAX_POINTS)
lock = threading.Lock()


# Persistent append-only log. JSONL is O(1) per record vs. JSON array which
# rewrites the whole file every message and stalls the callback after a few
# thousand records.
log_file = open(DATA_FILE, "a", buffering=1)  # line-buffered
msg_counter = 0
data_dirty = threading.Event()


def append_to_jsonl(record):
    log_file.write(json.dumps(record))
    log_file.write("\n")


def on_connect(client, userdata, flags, reason_code, properties):
    print("Connected! Code:", reason_code)
    client.subscribe("rdpms/point-machine")


def on_message(client, userdata, msg):
    global msg_counter
    try:
        data = json.loads(cipher.decrypt(msg.payload).decode())
    except Exception as e:
        print(f"Failed to decrypt/parse: {e}")
        return

    msg_counter += 1
    if msg_counter % LOG_EVERY == 0:
        print(f"[{msg_counter}] {data.get('timestamp', 0):.1f} "
              f"fault={data.get('fault', '') or '-'}")

    with lock:
        times.append(datetime.fromtimestamp(data["timestamp"]))
        for p in PARAMS:
            buffers[p].append(data.get(p, 0))
        fault_buf.append(data.get("fault", ""))
        label_buf.append(data.get("label", "NORMAL"))
    data_dirty.set()

    append_to_jsonl(data)


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect("broker.hivemq.com", 1883, 60)
client.loop_start()


# ---- Dashboard ----
fig = plt.figure(figsize=(15, 9))
gs = fig.add_gridspec(3, 3)
fig.suptitle("Point Machine Live Telemetry — RDPMS FRS Parameters")

ax_v110     = fig.add_subplot(gs[0, 0])
ax_ipt      = fig.add_subplot(gs[0, 1])
ax_tpt      = fig.add_subplot(gs[0, 2])
ax_vpt_rr   = fig.add_subplot(gs[1, 0])
ax_vpt_loc  = fig.add_subplot(gs[1, 1])
ax_vib      = fig.add_subplot(gs[1, 2])
ax_pos_rly  = fig.add_subplot(gs[2, 0])
ax_con_rly  = fig.add_subplot(gs[2, 1])
ax_status   = fig.add_subplot(gs[2, 2])

# 110 V at LOC — thresholds: min_safe=90, min_fail=82
(line_110n,) = ax_v110.plot([], [], "b-",  lw=1.4, label="VPT 110 N")
(line_110r,) = ax_v110.plot([], [], "b--", lw=1.4, label="VPT 110 R")
ax_v110.axhline(90, color="orange", lw=1, ls=":", label="min_safe 90 V")
ax_v110.axhline(82, color="red",    lw=1, ls=":", label="min_fail 82 V")
ax_v110.set_ylabel("Volts")
ax_v110.set_title("110 V DC at Location")
ax_v110.set_ylim(70, 120)

# Motor current
(line_in,) = ax_ipt.plot([], [], "r-",  lw=1.4, label="IPT N")
(line_ir,) = ax_ipt.plot([], [], "r--", lw=1.4, label="IPT R")
ax_ipt.set_ylabel("Amps")
ax_ipt.set_title("Motor Current (Stroke Signature)")
ax_ipt.set_ylim(-0.5, 12)

# TPT — max_safe=8 s
(line_tn,) = ax_tpt.plot([], [], "g-",  lw=1.4, label="TPT N")
(line_tr,) = ax_tpt.plot([], [], "g--", lw=1.4, label="TPT R")
ax_tpt.axhline(8, color="red", lw=1, ls=":", label="max_safe 8 s")
ax_tpt.set_ylabel("Seconds")
ax_tpt.set_title("Operation Time (derived)")
ax_tpt.set_ylim(0, 12)

# 24 V at RR (NWKR/RWKR) — thresholds: min_safe=21, min_fail=18
(line_nwkr_v,) = ax_vpt_rr.plot([], [], "m-",  lw=1.4, label="VPT NWKR")
(line_rwkr_v,) = ax_vpt_rr.plot([], [], "m--", lw=1.4, label="VPT RWKR")
ax_vpt_rr.axhline(21, color="orange", lw=1, ls=":", label="min_safe 21 V")
ax_vpt_rr.axhline(18, color="red",    lw=1, ls=":", label="min_fail 18 V")
ax_vpt_rr.set_ylabel("Volts")
ax_vpt_rr.set_title("24 V at Relay Room (NWKR / RWKR)")
ax_vpt_rr.set_ylim(-2, 28)

# 24 V at LOC after detection — no FRS thresholds
(line_24n,) = ax_vpt_loc.plot([], [], "c-",  lw=1.4, label="VPT 24 N (LOC)")
(line_24r,) = ax_vpt_loc.plot([], [], "c--", lw=1.4, label="VPT 24 R (LOC)")
ax_vpt_loc.set_ylabel("Volts")
ax_vpt_loc.set_title("24 V at LOC after Detection")
ax_vpt_loc.set_ylim(-2, 28)

# Vibration
(line_vib,) = ax_vib.plot([], [], "y-", lw=1.4, label="Vibration X")
ax_vib.set_ylabel("Vib")
ax_vib.set_title("Vibration X (optional)")
ax_vib.set_ylim(-0.1, 1.0)

# Position relays (NWKR / RWKR digital) — step plot
(line_nwkr_d,) = ax_pos_rly.plot([], [], "b-",  drawstyle="steps-post", lw=1.6, label="NWKR")
(line_rwkr_d,) = ax_pos_rly.plot([], [], "g-",  drawstyle="steps-post", lw=1.6, label="RWKR")
ax_pos_rly.set_ylim(-0.2, 1.2)
ax_pos_rly.set_yticks([0, 1])
ax_pos_rly.set_title("Position Relays (NWKR / RWKR)")

# Contactor relays (NWCR / RWCR digital)
(line_nwcr_d,) = ax_con_rly.plot([], [], "r-",  drawstyle="steps-post", lw=1.6, label="NWCR")
(line_rwcr_d,) = ax_con_rly.plot([], [], "m-",  drawstyle="steps-post", lw=1.6, label="RWCR")
ax_con_rly.set_ylim(-0.2, 1.2)
ax_con_rly.set_yticks([0, 1])
ax_con_rly.set_title("Contactor Relays (NWCR / RWCR)")
ax_con_rly.set_xlabel("Time")

# Status panel — text only
ax_status.axis("off")
ax_status.set_title("Status")
status_text = ax_status.text(0.02, 0.95, "", transform=ax_status.transAxes,
                             family="monospace", fontsize=10, va="top")

for ax in (ax_v110, ax_ipt, ax_tpt, ax_vpt_rr, ax_vpt_loc, ax_vib,
           ax_pos_rly, ax_con_rly):
    ax.grid(True, alpha=0.4)
    ax.legend(loc="upper right", fontsize=7, ncol=2)


def derive_state(latest):
    if latest["nwcr"]:
        return f"STROKING -> Normal (NWCR active)"
    if latest["rwcr"]:
        return f"STROKING -> Reverse (RWCR active)"
    if latest["nwkr"]:
        return "IDLE @ Normal (NWKR detected)"
    if latest["rwkr"]:
        return "IDLE @ Reverse (RWKR detected)"
    return "UNKNOWN"


def threshold_alarms(latest):
    """Return list of human-readable threshold breaches per FRS."""
    alarms = []
    if latest["vpt_110_n"] < 82:
        alarms.append(f"VPT_110_N={latest['vpt_110_n']:.1f} < min_fail 82")
    elif latest["vpt_110_n"] < 90:
        alarms.append(f"VPT_110_N={latest['vpt_110_n']:.1f} < min_safe 90")
    if latest["vpt_110_r"] < 82:
        alarms.append(f"VPT_110_R={latest['vpt_110_r']:.1f} < min_fail 82")
    elif latest["vpt_110_r"] < 90:
        alarms.append(f"VPT_110_R={latest['vpt_110_r']:.1f} < min_safe 90")
    # 24 V detection feeds — only meaningful when relay should be active
    if latest["nwkr"] and latest["vpt_nwkr"] < 18:
        alarms.append(f"VPT_NWKR={latest['vpt_nwkr']:.1f} < min_fail 18")
    elif latest["nwkr"] and latest["vpt_nwkr"] < 21:
        alarms.append(f"VPT_NWKR={latest['vpt_nwkr']:.1f} < min_safe 21")
    if latest["rwkr"] and latest["vpt_rwkr"] < 18:
        alarms.append(f"VPT_RWKR={latest['vpt_rwkr']:.1f} < min_fail 18")
    elif latest["rwkr"] and latest["vpt_rwkr"] < 21:
        alarms.append(f"VPT_RWKR={latest['vpt_rwkr']:.1f} < min_safe 21")
    if latest["tpt_n"] > 8:
        alarms.append(f"TPT_N={latest['tpt_n']:.1f} > max_safe 8 (obstruction)")
    if latest["tpt_r"] > 8:
        alarms.append(f"TPT_R={latest['tpt_r']:.1f} > max_safe 8 (obstruction)")
    return alarms


def update(_frame):
    if not data_dirty.is_set():
        return ()
    with lock:
        if not times:
            return ()
        x = list(times)
        snap = {p: list(buffers[p]) for p in PARAMS}
        fault_now = fault_buf[-1] if fault_buf else ""
        label_now = label_buf[-1] if label_buf else "NORMAL"
        data_dirty.clear()

    line_110n.set_data(x, snap["vpt_110_n"])
    line_110r.set_data(x, snap["vpt_110_r"])

    line_in.set_data(x, snap["ipt_n"])
    line_ir.set_data(x, snap["ipt_r"])

    line_tn.set_data(x, snap["tpt_n"])
    line_tr.set_data(x, snap["tpt_r"])

    line_nwkr_v.set_data(x, snap["vpt_nwkr"])
    line_rwkr_v.set_data(x, snap["vpt_rwkr"])

    line_24n.set_data(x, snap["vpt_24_n"])
    line_24r.set_data(x, snap["vpt_24_r"])

    line_vib.set_data(x, snap["vib_x"])

    line_nwkr_d.set_data(x, snap["nwkr"])
    line_rwkr_d.set_data(x, snap["rwkr"])
    line_nwcr_d.set_data(x, snap["nwcr"])
    line_rwcr_d.set_data(x, snap["rwcr"])

    for ax in (ax_v110, ax_ipt, ax_tpt, ax_vpt_rr, ax_vpt_loc, ax_vib,
               ax_pos_rly, ax_con_rly):
        ax.relim()
        ax.autoscale_view(scalex=True, scaley=False)

    latest = {p: snap[p][-1] for p in PARAMS}
    alarms = threshold_alarms(latest)
    fault_line = f"FAULT : {fault_now}" if fault_now else "FAULT : (none)"
    alarm_block = ("\n  ! " + "\n  ! ".join(alarms)) if alarms else "  (none)"
    text = (
        f"State : {derive_state(latest)}\n"
        f"LABEL : {label_now}\n"
        f"{fault_line}\n"
        f"\n"
        f"NWKR={latest['nwkr']}   RWKR={latest['rwkr']}\n"
        f"NWCR={latest['nwcr']}   RWCR={latest['rwcr']}\n"
        f"\n"
        f"V110_N = {latest['vpt_110_n']:6.2f} V    "
        f"V110_R = {latest['vpt_110_r']:6.2f} V\n"
        f"VPT_NWKR = {latest['vpt_nwkr']:6.2f} V  "
        f"VPT_RWKR = {latest['vpt_rwkr']:6.2f} V\n"
        f"VPT_24_N = {latest['vpt_24_n']:6.2f} V  "
        f"VPT_24_R = {latest['vpt_24_r']:6.2f} V\n"
        f"\n"
        f"IPT_N = {latest['ipt_n']:6.2f} A    "
        f"IPT_R = {latest['ipt_r']:6.2f} A\n"
        f"TPT_N = {latest['tpt_n']:6.2f} s    "
        f"TPT_R = {latest['tpt_r']:6.2f} s\n"
        f"VIB_X = {latest['vib_x']:6.3f}\n"
        f"\n"
        f"ALARMS:{alarm_block}"
    )
    if label_now == "FAULT":
        color = "red"
    elif label_now == "MAINTENANCE_ALERT":
        color = "darkorange"
    else:
        color = "black"
    status_text.set_text(text)
    status_text.set_color(color)

    return ()


fig.autofmt_xdate()  # one-shot tick rotation; not in the redraw loop
ani = FuncAnimation(fig, update, interval=PLOT_INTERVAL_MS, cache_frame_data=False)

try:
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.show()
finally:
    client.loop_stop()
    client.disconnect()
    log_file.close()
