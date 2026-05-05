import paho.mqtt.client as mqtt
import time
import json
import os
import random
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

i = 0
try:
    while True:
        data = {
            "timestamp": time.time(),
            "voltage": round(random.uniform(220, 240), 2),
            "current": round(random.uniform(5, 15), 2),
            "vibration": round(random.uniform(0.0, 2.0), 2),
        }
        payload = cipher.encrypt(json.dumps(data).encode())
        client.publish("rdpms/point-machine", payload)
        print(f"Sent message {i}")
        print(f"  Plain:     {data}")
        print(f"  Encrypted: {payload.decode()}")
        i += 1
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopping publisher...")
finally:
    client.disconnect()
