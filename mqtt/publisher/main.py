"""
Publisher entry point.

Creates the MQTT client, FaultEngine, and StrokeManager, then loops at
5 Hz publishing encrypted telemetry to the broker.
"""

import time
import json
import paho.mqtt.client as mqtt

from common.config import MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS, TOPIC
from common.encryption import get_cipher
from publisher.config import SAMPLE_PERIOD
from publisher.fault_engine import FaultEngine
from publisher.stroke import StrokeManager
from publisher.telemetry import generate_record


def run() -> None:
    """Start the telemetry publisher loop."""
    cipher = get_cipher()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.connect(MQTT_HOST, MQTT_PORT, 60)

    fault_engine = FaultEngine()
    stroke_mgr = StrokeManager()

    i = 0
    try:
        while True:
            data = generate_record(fault_engine, stroke_mgr)
            payload = cipher.encrypt(json.dumps(data).encode())
            client.publish(TOPIC, payload)

            stroking = stroke_mgr.stroking
            active_fault = fault_engine.active_fault
            scheduled_fault = fault_engine.scheduled_fault

            if i % 5 == 0 or stroking or active_fault or scheduled_fault:
                tag = (
                    f"STROKE->{stroke_mgr.stroke_target}"
                    if stroking
                    else f"IDLE@{stroke_mgr.position}"
                )
                sched_tag = f" SCHED={scheduled_fault}" if scheduled_fault else ""
                flt = f" FAULT={active_fault}" if active_fault else ""
                print(
                    f"[{i:05d}] {tag:12s}  I_N={data['ipt_n']:.2f}  "
                    f"I_R={data['ipt_r']:.2f}  V110_N={data['vpt_110_n']:.1f}  "
                    f"TPT_N={data['tpt_n']:.1f}  label={data['label']}"
                    f"{sched_tag}{flt}"
                )
            i += 1
            time.sleep(SAMPLE_PERIOD)
    except KeyboardInterrupt:
        print("\nStopping publisher...")
    finally:
        client.disconnect()
