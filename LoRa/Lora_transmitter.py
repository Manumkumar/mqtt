import serial
import time
import json
import math
import random
from datetime import datetime

PORT        = "/dev/ttyUSB0"   # Windows users: change to "COM3" etc.
BAUDRATE    = 9600
MAX_PACKETS = 32                # firmware constant — fragments per logical message
TX_TIMEOUT  = 2.0               # seconds to wait for "+TEST: TX DONE"
SEND_PERIOD = 1.0               # seconds between logical messages
SENSOR_ID   = "STM32_001"
NAME        = "PM"

ser = None  # opened in open_serial()


def open_serial():
    global ser
    ser = serial.Serial(
        port     = PORT,
        baudrate = BAUDRATE,
        timeout  = 1,
    )


def reconnect():
    """Close and reopen the serial port, then re-init the LoRa module."""
    global ser
    try:
        if ser is not None:
            ser.close()
    except Exception:
        pass
    while True:
        try:
            print("[SERIAL] reconnecting...")
            time.sleep(2.0)
            open_serial()
            time.sleep(0.5)
            send_at("AT")
            send_at("AT+MODE=TEST")
            send_at("AT+TEST=RFCFG,433,SF7,125,12,15,14,ON,OFF,OFF")
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


def safe_readline():
    try:
        return ser.readline()
    except (serial.SerialException, OSError) as e:
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
    # Must match the receiver's RFCFG: 433MHz, SF7, BW125, preamble 12
    print(send_at("AT+TEST=RFCFG,433,SF7,125,12,15,14,ON,OFF,OFF"))
    print("LoRa-E5 ready. Streaming packets...")
    print("-" * 60)


def wait_for_tx_done(timeout=TX_TIMEOUT):
    """Block until '+TEST: TX DONE' arrives. Return True on success, False on timeout/error."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if safe_in_waiting() > 0:
            line = safe_readline().decode("utf-8", errors="replace")
            if "TX DONE" in line:
                return True
            if "ERROR" in line or "TX FAIL" in line:
                return False
        else:
            time.sleep(0.01)
    return False


def send_packet(payload_obj, label):
    """Encode payload as JSON, split into ≤32 chunks, send each as AT+TEST=TXLRPKT."""
    payload = json.dumps(payload_obj, separators=(",", ":"))
    raw = payload.encode("ascii")
    hex_total = raw.hex().upper()
    msg_len = len(raw)
    hex_len = len(hex_total)

    print(f"[PKT] len={msg_len} hex_chars={hex_len}")
    print(f"[PKT IN]  {payload}")
    print(f"[PKT HEX] {hex_total}")

    chunk_bytes = max(1, math.ceil(msg_len / MAX_PACKETS))
    chunk_hex = chunk_bytes * 2
    print(f"[SPLIT] hex_total={hex_len} chunk_hex={chunk_hex} packets={MAX_PACKETS}")

    all_ok = True
    for i in range(MAX_PACKETS):
        offset = i * chunk_hex
        if offset >= hex_len:
            print("[SPLIT] no data for this part, stopping")
            break
        chunk = hex_total[offset : offset + chunk_hex]
        cmd = f"AT+TEST=TXLRPKT,{chunk}"
        cmd_len = len(cmd) + 2
        print(f"[PKT {i + 1}/{MAX_PACKETS}] offset={offset} len={len(chunk)} cmd_len={cmd_len}")
        print(f"[TX] {cmd}")

        safe_write((cmd + "\r\n").encode())
        if not wait_for_tx_done():
            all_ok = False

    print(f"[PKT] {'TX OK' if all_ok else 'TX FAIL'}")
    print(f"{label} pkt sent")
    print()


def make_message(seq, points):
    """Build the {q, s, n, p} envelope used by the firmware."""
    now = datetime.now()
    timestamp = now.strftime("%d-%m-%Y %H:%M:%S.") + f"{now.microsecond // 1000:03d}"
    for p in points:
        p["t"] = timestamp
    return {
        "q": f"{SENSOR_ID}_{seq:08d}",
        "s": SENSOR_ID,
        "n": NAME,
        "p": points,
    }


def main():
    open_serial()
    setup_lora()
    seq = 0

    categories = [
        ("V110", ["0001120A", "0001120B"], lambda: round(random.uniform(105.0, 115.0), 1)),
        ("V24",  ["00012840", "00012841"], lambda: round(random.uniform(23.0, 25.0), 1)),
        ("Cur",  ["0001000C", "0001000D"], lambda: round(random.uniform(0.0, 5.0), 3)),
        ("Vib",  ["00016050"],             lambda: round(random.uniform(0.0, 0.05), 3)),
    ]

    try:
        while True:
            for label, ids, gen in categories:
                points = [{"id": pid, "v": [gen()]} for pid in ids]
                msg = make_message(seq, points)
                send_packet(msg, label)
                seq += 1
                time.sleep(SEND_PERIOD)
    except KeyboardInterrupt:
        print("\nStopping transmitter...")
    finally:
        try:
            ser.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
