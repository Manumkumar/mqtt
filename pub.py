import paho.mqtt.client as mqtt
import time
import json
import os
from cryptography.fernet import Fernet

KEY_FILE = "secret.key"

# Generate key on first run, reuse afterwards so subscriber can decrypt
if not os.path.exists(KEY_FILE):
    with open(KEY_FILE, "wb") as f:
        f.write(Fernet.generate_key())

with open(KEY_FILE, "rb") as f:
    cipher = Fernet(f.read())

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect("broker.hivemq.com", 1883, 60)

for i in range(1,15):
    data = {
        "timestamp": time.time(),
        "voltage": i,
        "current": i + 2,
        "vibration": i/2
    }
    payload = cipher.encrypt(json.dumps(data).encode())
    client.publish("rdpms/point-machine", payload)
    print(f"Sent message {i}")
    print(f"  Encrypted: {payload.decode()}")
    time.sleep(1)

client.disconnect()
