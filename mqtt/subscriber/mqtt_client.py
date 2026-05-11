"""
MQTT client setup and callbacks for the subscriber.

Decrypts incoming messages, populates the shared DataStore, and triggers
data logging.
"""

from datetime import datetime
import json

import paho.mqtt.client as mqtt

from common.config import MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS, TOPIC
from common.encryption import get_cipher
from subscriber.config import PARAMS, FILTERED_PARAMS, LOG_EVERY
from subscriber.data_store import DataStore
from subscriber.data_logging import DataLogger


def create_client(data_store: DataStore, data_logger: DataLogger) -> mqtt.Client:
    """Build, configure, and connect the MQTT subscriber client.

    The client's background network loop is started before returning.
    """
    cipher = get_cipher()
    msg_counter = {"n": 0}  # mutable container for closure

    def on_connect(_client, _userdata, _flags, reason_code, _properties):
        print("Connected! Code:", reason_code)
        _client.subscribe(TOPIC)

    def on_message(_client, _userdata, msg):
        try:
            data = json.loads(cipher.decrypt(msg.payload).decode())
        except Exception as e:
            print(f"Failed to decrypt/parse: {e}")
            return

        msg_counter["n"] += 1
        if msg_counter["n"] % LOG_EVERY == 0:
            print(
                f"[{msg_counter['n']}] {data.get('timestamp', 0):.1f} "
                f"fault={data.get('fault', '') or '-'}"
            )

        with data_store.lock:
            data_store.times.append(datetime.fromtimestamp(data["timestamp"]))
            for p in PARAMS:
                data_store.buffers[p].append(data.get(p, 0))
            data_store.fault_buf.append(data.get("fault", ""))
            data_store.label_buf.append(data.get("label", "NORMAL"))
        data_store.data_dirty.set()

        # Logging
        data_logger.append_raw(data)
        with data_store.lock:
            snap = {p: list(data_store.buffers[p]) for p in FILTERED_PARAMS}
        data_logger.append_filtered(
            data.get("timestamp", 0),
            data.get("fault", ""),
            data.get("label", "NORMAL"),
            snap,
        )

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_start()
    return client
