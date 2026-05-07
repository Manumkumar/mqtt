import serial
import time
import re
import json

import paho.mqtt.client as mqtt

PORT      = "/dev/ttyUSB0"
BAUDRATE  = 9600
DATA_FILE = "lora_received.jsonl"
MAX_BUF   = 8192   # drop buffer if it grows past this without a complete JSON object

MQTT_HOST  = "relldevices.in"
MQTT_PORT  = 1883
MQTT_USER  = "mosquitto"
MQTT_PASS  = "dIju32432saafgsd"
MQTT_TOPIC = "parameter_e/stngw_001/01"

ser    = None  # opened in main()
client = None  # MQTT client, set in main()


def open_serial():
    global ser
    ser = serial.Serial(
        port     = PORT,
        baudrate = BAUDRATE,
        timeout  = 1,
    )


def reconnect(full_init=False):
    """Close and reopen the serial port. By default just re-arms RX so we don't
    flood the radio with AT echoes during transient USB stalls. Pass
    full_init=True to also re-run AT+MODE/RFCFG (e.g. after a hard module reset)."""
    global ser
    try:
        if ser is not None:
            ser.close()
    except Exception:
        pass
    while True:
        try:
            print("[SERIAL] reconnecting...")
            time.sleep(1.0)
            open_serial()
            time.sleep(0.2)
            if full_init:
                send_at("AT")
                send_at("AT+MODE=TEST")
                send_at("AT+TEST=RFCFG,868,SF12,125,8,8,14,ON,OFF,OFF")
            start_rx()
            print("[SERIAL] reconnected and re-armed.")
            return
        except (serial.SerialException, OSError) as e:
            print(f"[SERIAL] reconnect failed: {e}")


def safe_write(data):
    while True:
        try:
            ser.write(data)
            return
        except (serial.SerialException, OSError) as e:
            print(f"[SERIAL] write error: {e}")
            reconnect()


_read_stall_count = 0
_READ_STALL_LIMIT = 30  # consecutive transient stalls before forcing reconnect


def safe_readline():
    global _read_stall_count
    try:
        data = ser.readline()
        _read_stall_count = 0
        return data
    except (serial.SerialException, OSError) as e:
        msg = str(e)
        # Transient USB stall: pyserial reports readiness but read returns 0.
        # Module is fine; reconnecting just floods serial. Retry instead.
        if "readiness to read but returned no data" in msg:
            _read_stall_count += 1
            if _read_stall_count < _READ_STALL_LIMIT:
                time.sleep(0.1)
                return b""
            print(f"[SERIAL] {_read_stall_count} consecutive stalls — forcing reconnect")
            _read_stall_count = 0
        else:
            print(f"[SERIAL] read error: {e}")
        reconnect()
        return b""


def safe_in_waiting():
    try:
        return ser.in_waiting
    except (serial.SerialException, OSError) as e:
        print(f"[SERIAL] in_waiting error: {e}")
        reconnect()
        return 0


# Lines from LoRa-E5 in test RX mode look like:  +TEST: RX "7B2271223A22"
RX_LINE_RE = re.compile(r'\+TEST:\s*RX\s*"([0-9A-Fa-f]+)"')


def send_at(command, wait=0.3):
    safe_write((command + "\r\n").encode())
    time.sleep(wait)
    response = ""
    while safe_in_waiting() > 0:
        response += safe_readline().decode("utf-8", errors="replace")
    return response.strip()


def setup_lora():
    print("Initializing LoRa-E5...")
    print(send_at("AT"))
    print(send_at("AT+MODE=TEST"))
    # Must match the transmitter's RFCFG exactly: 868MHz, SF12, BW125, preamble 8, ...
    print(send_at("AT+TEST=RFCFG,868,SF12,125,8,8,14,ON,OFF,OFF"))
    print("LoRa-E5 configured. Listening for packets...")
    print("-" * 60)


def start_rx():
    # Single-packet receive mode — needs to be re-armed after each packet on LoRa-E5
    safe_write(b"AT+TEST=RXLRPKT\r\n")
    time.sleep(0.05)


def extract_json_messages(buf: bytes):
    """
    Find complete top-level JSON objects in buf by brace-matching.
    Returns (list_of_objects, leftover_buf).
    Drops bytes before the first '{' (link noise / corrupted fragments).
    """
    text = buf.decode("utf-8", errors="replace")
    messages = []
    while True:
        start = text.find("{")
        if start < 0:
            text = ""
            break
        text = text[start:]  # discard garbage before first '{'
        depth = 0
        in_str = False
        esc = False
        end = -1
        for i, ch in enumerate(text):
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end < 0:
            break  # incomplete object — wait for more bytes
        candidate = text[: end + 1]
        try:
            messages.append(json.loads(candidate))
            text = text[end + 1 :]
        except json.JSONDecodeError:
            # Malformed: drop the opening '{' and keep scanning for the next one
            text = text[1:]
    return messages, text.encode("utf-8", errors="replace")


def append_to_jsonl(record):
    with open(DATA_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, separators=(",", ":")) + "\n")


def setup_mqtt():
    global client
    # Support both paho-mqtt 1.x and 2.x. CallbackAPIVersion only exists on 2.x.
    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.on_connect    = lambda c, u, f, rc, p: print(f"[MQTT]  connected rc={rc}")
        client.on_disconnect = lambda c, u, f, rc, p: print(f"[MQTT]  disconnected rc={rc}")
    else:
        client = mqtt.Client()
        client.on_connect    = lambda c, u, f, rc: print(f"[MQTT]  connected rc={rc}")
        client.on_disconnect = lambda c, u, rc:    print(f"[MQTT]  disconnected rc={rc}")
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()


def publish_to_mqtt(record):
    payload = json.dumps(record, separators=(",", ":"))
    info = client.publish(MQTT_TOPIC, payload, qos=1, retain=True)
    info.wait_for_publish(timeout=5.0)
    print(f"[MQTT]  pub topic={MQTT_TOPIC} mid={info.mid} rc={info.rc} sent={info.is_published()}")


def pretty_print_message(obj):
    """Render a decoded sensor envelope in a human-readable form."""
    seq    = obj.get("q", "?")
    sensor = obj.get("s", "?")
    name   = obj.get("n", "?")
    points = obj.get("p", [])
    print("  " + "-" * 56)
    print(f"  Sensor : {sensor}    Metric : {name}    Seq : {seq}")
    for p in points:
        pid    = p.get("id", "?")
        values = p.get("v", [])
        ts     = p.get("t", "?")
        vals   = ", ".join(str(v) for v in values)
        print(f"    id={pid}  v=[{vals}]  t={ts}")
    print("  " + "-" * 56)


def listen():
    buf = b""
    start_rx()
    while True:
        line = safe_readline().decode("utf-8", errors="replace").strip()
        if not line:
            continue

        m = RX_LINE_RE.search(line)
        if m:
            hex_part = m.group(1)
            try:
                chunk = bytes.fromhex(hex_part)
            except ValueError:
                print(f"[ERR] bad hex: {hex_part}")
                start_rx()
                continue

            buf += chunk
            ascii_preview = chunk.decode("ascii", errors="replace")
            print(f"[CHUNK] +{len(chunk)}B  buf={len(buf)}B  hex={hex_part}  ascii={ascii_preview!r}")

            messages, buf = extract_json_messages(buf)
            for obj in messages:
                # Reject inner-point fragments that escape from a corrupted envelope —
                # only the full {q, s, n, p} envelope is a real message.
                if not all(k in obj for k in ("q", "s", "n", "p")):
                    print(f"[SKIP]  fragment (no envelope keys): {json.dumps(obj, separators=(',', ':'))}")
                    continue
                print("[MSG]   " + json.dumps(obj, separators=(",", ":")))
                pretty_print_message(obj)
                append_to_jsonl(obj)
                publish_to_mqtt(obj)

            if len(buf) > MAX_BUF:
                print(f"[WARN] buf overflow ({len(buf)}B) — dropping")
                buf = b""

            start_rx()  # re-arm for the next fragment
        elif line.startswith("+TEST:"):
            # Header lines like '+TEST: LEN:6, RSSI:-30, SNR:8' — useful for link diagnostics
            print(f"[INFO] {line}")
        else:
            print(f"[SERIAL] {line}")


def main():
    setup_mqtt()
    open_serial()
    setup_lora()
    try:
        listen()
    except KeyboardInterrupt:
        print("\nStopping receiver...")
    finally:
        try:
            ser.close()
        except Exception:
            pass
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    main()
