"""
End-to-end simulator for the LoRa transmitter/receiver pipeline.

No radio hardware required. Continuously generates messages in the same envelope
as Lora_transmitter.py, fragments them with the same chunking rule, optionally
drops fragments to simulate radio loss, and feeds the survivors into
Lora_reciever.extract_json_messages() to verify reassembly.

Run forever; Ctrl+C to stop and see the summary.
"""

import json
import math
import random
import time
from datetime import datetime

from Lora_reciever import extract_json_messages

MAX_PACKETS = 32
SENSOR_ID = "STM32_001"
NAME = "PM"
SEND_PERIOD = 1.0    # seconds between logical messages
LOSS_RATE = 0.0      # 0.0 = perfect link; e.g. 0.05 = 5% per-fragment drop


def make_message(seq, points):
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


def fragment(msg_obj):
    """Encode and fragment exactly like Lora_transmitter.send_packet()."""
    payload = json.dumps(msg_obj, separators=(",", ":"))
    raw = payload.encode("ascii")
    hex_total = raw.hex().upper()

    chunk_bytes = max(1, math.ceil(len(raw) / MAX_PACKETS))
    chunk_hex = chunk_bytes * 2

    fragments = [hex_total[i : i + chunk_hex] for i in range(0, len(hex_total), chunk_hex)]
    return fragments, payload


CATEGORIES = [
    ("V110", ["0001120A", "0001120B"], lambda: round(random.uniform(105.0, 115.0), 1)),
    ("V24",  ["00012840", "00012841"], lambda: round(random.uniform(23.0, 25.0), 1)),
    ("Cur",  ["0001000C", "0001000D"], lambda: round(random.uniform(0.0, 5.0), 3)),
    ("Vib",  ["00016050"],             lambda: round(random.uniform(0.0, 0.05), 3)),
]


def run_live(send_period=SEND_PERIOD, loss_rate=LOSS_RATE):
    """Stream messages forever; stop on Ctrl+C."""
    seq = 0
    sent = 0
    received = 0
    total_fragments = 0
    dropped = 0
    rx_buffer = b""

    print(f"Streaming messages every {send_period}s, loss_rate={loss_rate * 100:.1f}%")
    print("Press Ctrl+C to stop.")
    print("-" * 60)

    try:
        while True:
            label, ids, gen = CATEGORIES[seq % len(CATEGORIES)]
            points = [{"id": pid, "v": [gen()]} for pid in ids]
            msg = make_message(seq, points)
            sent += 1

            fragments, payload = fragment(msg)
            print(f"[TX  {seq:04d}] {label:4s} len={len(payload)}B  fragments={len(fragments)}")

            for i, frag in enumerate(fragments):
                total_fragments += 1
                if random.random() < loss_rate:
                    dropped += 1
                    print(f"            [LOST] frag {i + 1}/{len(fragments)}")
                    continue
                rx_buffer += bytes.fromhex(frag)

            msgs, rx_buffer = extract_json_messages(rx_buffer)
            for m in msgs:
                received += 1
                values = ", ".join(
                    f"{p['id']}={p['v'][0]}" for p in m["p"]
                )
                print(f"[RX  {m['q'].split('_')[-1]}] {values}")

            seq += 1
            time.sleep(send_period)

    except KeyboardInterrupt:
        print()
        print("=" * 60)
        print("Stopped.")
        print(f"Messages sent:      {sent}")
        print(f"Messages received:  {received}")
        print(f"Loss rate:          {dropped}/{total_fragments} fragments "
              f"({100 * dropped / max(1, total_fragments):.1f}%)")
        print(f"Buffer leftover:    {len(rx_buffer)} bytes")


if __name__ == "__main__":
    run_live()
