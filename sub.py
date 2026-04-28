import paho.mqtt.client as mqtt
import json
import os
import threading
from collections import deque
from datetime import datetime
from cryptography.fernet import Fernet
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

KEY_FILE = "secret.key"
DATA_FILE = "received_data.json"
MAX_POINTS = 60  # show the last 60 readings on the graph

with open(KEY_FILE, "rb") as f:
    cipher = Fernet(f.read())

times = deque(maxlen=MAX_POINTS)
voltages = deque(maxlen=MAX_POINTS)
currents = deque(maxlen=MAX_POINTS)
vibrations = deque(maxlen=MAX_POINTS)
lock = threading.Lock()


def append_to_json(record):
    records = []
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            try:
                records = json.load(f)
            except json.JSONDecodeError:
                records = []
    records.append(record)
    with open(DATA_FILE, "w") as f:
        json.dump(records, f, indent=2)


def on_connect(client, userdata, flags, reason_code, properties):
    print("Connected! Code:", reason_code)
    client.subscribe("rdpms/point-machine")


def on_message(client, userdata, msg):
    try:
        data = json.loads(cipher.decrypt(msg.payload).decode())
    except Exception as e:
        print(f"Failed to decrypt/parse: {e}")
        return

    print(f"Received: {data}")

    with lock:
        times.append(datetime.fromtimestamp(data["timestamp"]))
        voltages.append(data["voltage"])
        currents.append(data["current"])
        vibrations.append(data["vibration"])

    append_to_json(data)


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect("broker.hivemq.com", 1883, 60)
client.loop_start()  # run network loop in a background thread so plt can own the main thread

fig, (ax_v, ax_c, ax_b) = plt.subplots(3, 1, sharex=True, figsize=(9, 7))
fig.suptitle("Live Sensor Readings — rdpms/point-machine")

(line_v,) = ax_v.plot([], [], "b-o", markersize=3, label="Voltage")
(line_c,) = ax_c.plot([], [], "r-o", markersize=3, label="Current")
(line_b,) = ax_b.plot([], [], "g-o", markersize=3, label="Vibration")

ax_v.set_ylabel("Voltage (V)")
ax_c.set_ylabel("Current (A)")
ax_b.set_ylabel("Vibration")
ax_b.set_xlabel("Time")

for ax in (ax_v, ax_c, ax_b):
    ax.grid(True)
    ax.legend(loc="upper right")


def update(frame):
    with lock:
        if not times:
            return line_v, line_c, line_b
        x = list(times)
        v = list(voltages)
        c = list(currents)
        b = list(vibrations)

    line_v.set_data(x, v)
    line_c.set_data(x, c)
    line_b.set_data(x, b)

    for ax in (ax_v, ax_c, ax_b):
        ax.relim()
        ax.autoscale_view()

    fig.autofmt_xdate()
    return line_v, line_c, line_b


ani = FuncAnimation(fig, update, interval=500, cache_frame_data=False)

try:
    plt.tight_layout()
    plt.show()
finally:
    client.loop_stop()
    client.disconnect()
