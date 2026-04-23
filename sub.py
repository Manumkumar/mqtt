import paho.mqtt.client as mqtt
import json
import os
from cryptography.fernet import Fernet

KEY_FILE = "secret.key"
DATA_FILE = "received_data.json"

with open(KEY_FILE, "rb") as f:
    cipher = Fernet(f.read())


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

    records = []
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            try:
                records = json.load(f)
            except json.JSONDecodeError:
                records = []
    records.append(data)
    with open(DATA_FILE, "w") as f:
        json.dump(records, f, indent=2)


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message

client.connect("broker.hivemq.com", 1883, 60)
client.loop_forever()
