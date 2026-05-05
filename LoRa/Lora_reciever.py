import serial
import time
import re
import json
import os

PORT     = "/dev/ttyUSB0"
BAUDRATE = 9600
DATA_FILE = "lora_received.json"

ser = None  # opened in main()


def open_serial():
    global ser
    ser = serial.Serial(
        port     = PORT,
        baudrate = BAUDRATE,
        timeout  = 1,
    )

# Lines from LoRa-E5 in test RX mode look like:  +TEST: RX "7B2271223A22"
RX_LINE_RE = re.compile(r'\+TEST:\s*RX\s*"([0-9A-Fa-f]+)"')


def send_at(command):
    ser.write((command + "\r\n").encode())
    time.sleep(0.3)
    response = ""
    while ser.in_waiting > 0:
        response += ser.readline().decode("utf-8", errors="replace")
    return response.strip()


def setup_lora():
    print("Initializing LoRa-E5...")
    print(send_at("AT"))
    print(send_at("AT+MODE=TEST"))
    # Must match the transmitter's RFCFG exactly: 433MHz, SF7, BW125, preamble 12, ...
    print(send_at("AT+TEST=RFCFG,433,SF7,125,12,15,14,ON,OFF,OFF"))
    print("LoRa-E5 configured. Listening for packets...")
    print("-" * 60)


def start_rx():
    # Single-packet receive mode — needs to be re-armed after each packet on LoRa-E5
    ser.write(b"AT+TEST=RXLRPKT\r\n")
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


def listen():
    buf = b""
    start_rx()
    while True:
        line = ser.readline().decode("utf-8", errors="replace").strip()
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
            print(f"[CHUNK] +{len(chunk)}B  buf={len(buf)}B  hex={hex_part}")

            messages, buf = extract_json_messages(buf)
            for obj in messages:
                print(f"[MSG]   {json.dumps(obj)}")
                append_to_json(obj)

            start_rx()  # re-arm for the next fragment
        elif line.startswith("+TEST:"):
            # Header lines like '+TEST: LEN:6, RSSI:-30, SNR:8' — useful for link diagnostics
            print(f"[INFO] {line}")
        else:
            print(f"[SERIAL] {line}")


def main():
    open_serial()
    setup_lora()
    try:
        listen()
    except KeyboardInterrupt:
        print("\nStopping receiver...")
    finally:
        ser.close()


if __name__ == "__main__":
    main()
