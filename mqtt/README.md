# Point Machine Telemetry — MQTT Pub/Sub

End-to-end demo: a fault-injecting publisher streams 15 RDPMS FRS-aligned point-machine
parameters over MQTT, an encrypted-payload subscriber receives them, persists to
JSONL, renders a live 3×3 dashboard, and runs a Median → Savitzky-Golay → Kalman
signal-conditioning pipeline in a second window.

```
 pub.py  ──MQTT (Fernet-encrypted JSON)──►  relldevices.in:1883
                                                      │
                                                      ▼
                                                   sub.py
                                                      │
                            ┌─────────────────────────┼────────────────────────┐
                            ▼                         ▼                        ▼
                    received_data.jsonl       Live FRS dashboard        Conditioned signals
                    (one record per line)     (3×3 matplotlib)          (2nd matplotlib window)
```

---

## Project Structure

The codebase is organised into three Python packages with thin launcher scripts:

```
mqtt/
├── common/                          # Shared utilities
│   ├── __init__.py
│   ├── config.py                    # MQTT host/port/creds, topic, key path
│   └── encryption.py                # Fernet key load/generate + cipher factory
│
├── publisher/                       # Telemetry publisher package
│   ├── __init__.py
│   ├── config.py                    # Sample rate, fault catalogue & durations
│   ├── fault_engine.py              # FaultEngine class (schedule → precursor → active → clear)
│   ├── stroke.py                    # StrokeManager class (position, motor-current profile)
│   ├── labeling.py                  # 3-class label derivation (NORMAL / MAINTENANCE_ALERT / FAULT)
│   ├── telemetry.py                 # Record generation (composes FaultEngine + StrokeManager)
│   └── main.py                     # Entry point: run()
│
├── subscriber/                      # Dashboard subscriber package
│   ├── __init__.py
│   ├── config.py                    # Buffer sizes, param lists, logging cadence
│   ├── signal_conditioning.py       # Median → Savitzky-Golay → Kalman pipeline
│   ├── data_store.py                # Thread-safe DataStore (rolling deques + lock)
│   ├── data_logging.py              # DataLogger class (raw + filtered JSONL append)
│   ├── mqtt_client.py               # Client factory with on_connect / on_message callbacks
│   ├── dashboard.py                 # 3×3 raw telemetry matplotlib dashboard
│   ├── conditioned_dashboard.py     # 4×2 conditioned-signal matplotlib dashboard
│   └── main.py                     # Entry point: run()
│
├── pub.py                           # Thin launcher → publisher.main.run()
├── sub.py                           # Thin launcher → subscriber.main.run()
├── secret.key                       # Auto-generated Fernet key (do not commit)
├── received_data.jsonl              # Raw telemetry log (subscriber output)
└── filtered_value.json              # Conditioned-signal log (subscriber output)
```

### Module responsibilities

| Package | Module | Responsibility |
|---------|--------|----------------|
| `common` | `config.py` | Single source of truth for MQTT credentials, topic, key file path |
| `common` | `encryption.py` | `get_cipher()` — creates key on first run, returns `Fernet` instance |
| `publisher` | `config.py` | `SAMPLE_PERIOD`, `FAULT_TYPES`, `FAULT_DURATIONS`, `PRECURSOR_RANGE`, `FAULT_TRIGGER_PROB` |
| `publisher` | `fault_engine.py` | `FaultEngine` class — fault scheduling, precursor drift, activation, clearing |
| `publisher` | `stroke.py` | `StrokeManager` class — position tracking, stroke lifecycle, motor-current waveform |
| `publisher` | `labeling.py` | `derive_label()` — classifies records using FRS thresholds |
| `publisher` | `telemetry.py` | `generate_record()` — builds the 15-parameter dict with drift and overrides |
| `publisher` | `main.py` | `run()` — MQTT connect, main loop, encrypted publish |
| `subscriber` | `config.py` | `MAX_POINTS`, `PLOT_INTERVAL_MS`, `PARAMS`, `FILTERED_PARAMS` |
| `subscriber` | `signal_conditioning.py` | `condition_signal()` — median → Savitzky-Golay → Kalman pipeline |
| `subscriber` | `data_store.py` | `DataStore` class — thread-safe rolling deques shared across threads |
| `subscriber` | `data_logging.py` | `DataLogger` class — append-only JSONL for raw and filtered records |
| `subscriber` | `mqtt_client.py` | `create_client()` — configures callbacks, connects, starts background loop |
| `subscriber` | `dashboard.py` | `create_raw_dashboard()` — 3×3 FRS dashboard with threshold lines |
| `subscriber` | `conditioned_dashboard.py` | `create_conditioned_dashboard()` — 4×2 raw vs. conditioned overlay |
| `subscriber` | `main.py` | `run()` — wires DataStore + DataLogger + MQTT + dashboards |

---

## Publisher — `publisher/`

Generates synthetic 5 Hz telemetry with realistic stroke profiles and randomly
injected fault scenarios. Each fault has a slow precursor phase (so the dataset
includes leading indicators a predictive-maintenance model can learn from)
followed by an active phase that breaches FRS thresholds.

### Published parameters (17 fields)

| Field        | Type    | Meaning                                              |
|--------------|---------|------------------------------------------------------|
| `timestamp`  | float   | Unix seconds                                         |
| `vpt_nwkr`   | volts   | 24 V detection feed at relay room (Normal side)      |
| `vpt_rwkr`   | volts   | 24 V detection feed at relay room (Reverse side)     |
| `nwkr`       | 0/1     | Normal position relay state                          |
| `rwkr`       | 0/1     | Reverse position relay state                         |
| `nwcr`       | 0/1     | Normal contactor relay (active mid-stroke to N)      |
| `rwcr`       | 0/1     | Reverse contactor relay (active mid-stroke to R)     |
| `vpt_110_n`  | volts   | 110 V supply at LOC, Normal side                     |
| `vpt_110_r`  | volts   | 110 V supply at LOC, Reverse side                    |
| `ipt_n`      | amps    | Motor current, Normal side                           |
| `ipt_r`      | amps    | Motor current, Reverse side                          |
| `vpt_24_n`   | volts   | 24 V at LOC after detection (Normal)                 |
| `vpt_24_r`   | volts   | 24 V at LOC after detection (Reverse)                |
| `vib_x`      | g       | Vibration X axis                                     |
| `tpt_n`      | seconds | Derived stroke time, Normal direction                |
| `tpt_r`      | seconds | Derived stroke time, Reverse direction               |
| `fault`      | string  | Name of currently active fault, `""` if none         |
| `label`      | string  | `NORMAL` \| `MAINTENANCE_ALERT` \| `FAULT`           |

### Fault catalogue

Each fault runs in two phases:

- **PRECURSOR** (10–18 s) — slow drift of relevant params toward the FRS
  `min_safe` warning band. Labelled `MAINTENANCE_ALERT`.
- **ACTIVE** (3–20 s) — pushes past `min_fail` / abnormal range. Labelled `FAULT`.

| Fault              | What it simulates                                                     |
|--------------------|-----------------------------------------------------------------------|
| `LOW_VPT_NWKR`     | 24 V detection feed sags (battery / wire degradation)                 |
| `LOW_VPT_110`      | 110 V supply dip                                                      |
| `OBSTRUCTION`      | Stroke runs longer than `max_safe` TPT (8 s); current stays elevated  |
| `OVER_CURRENT`     | Abnormally high motor current during stroke                           |
| `VIB_SPIKE`        | Abnormal vibration                                                    |
| `PHANTOM_CURRENT`  | Small idle current (leakage / hot wire)                               |
| `STUCK_NWKR_DROP`  | NWKR position relay fails to pick up at Normal                        |

### Publisher configuration

Defined in `publisher/config.py`:

| Constant             | Value                  | Role                                       |
|----------------------|------------------------|---------------------------------------------|
| `SAMPLE_PERIOD`      | `0.2 s`                | 5 Hz publish rate                          |
| `FAULT_TRIGGER_PROB` | `0.008`                | ~1 fault every 25 s                        |
| `PRECURSOR_RANGE`    | `(10.0, 18.0)`         | Duration range for precursor phase         |

Shared config in `common/config.py`:

| Constant             | Value                    | Role                                     |
|----------------------|--------------------------|-------------------------------------------|
| `MQTT_HOST`          | `relldevices.in`         | Broker hostname                           |
| `MQTT_PORT`          | `1883`                   | Broker port                               |
| `TOPIC`              | `rdpms/point-machine`    | MQTT topic                                |
| `KEY_FILE`           | `secret.key`             | Fernet key (auto-created on first run)    |

### Encryption

Each JSON payload is encrypted with **Fernet (AES-128-CBC + HMAC-SHA256)**
before publishing. The key is generated on first run by `common/encryption.py`
and persisted in `secret.key` — the subscriber loads the same file to decrypt.
The unencrypted JSON never leaves the publisher.

---

## Subscriber — `subscriber/`

Three things happen on every received message:

1. Decrypt + parse JSON, append to `received_data.jsonl` (line-buffered, O(1)).
2. Push into rolling deques (`MAX_POINTS = 300` ≈ 60 s history at 5 Hz).
3. Set a `data_dirty` event so the GUI loops know there's something new.

Two matplotlib figures animate independently:

### Window 1 — RDPMS FRS Dashboard (3×3 grid)

Built by `subscriber/dashboard.py`:

| Cell    | Plot                                | FRS thresholds drawn                     |
|---------|-------------------------------------|------------------------------------------|
| (0, 0)  | 110 V at LOC (N + R)                | orange `min_safe = 90`, red `min_fail = 82` |
| (0, 1)  | Motor current (IPT N + R)           | —                                        |
| (0, 2)  | Operation time (TPT N + R)          | red `max_safe = 8 s`                     |
| (1, 0)  | 24 V at relay room (NWKR + RWKR)    | orange `min_safe = 21`, red `min_fail = 18` |
| (1, 1)  | 24 V at LOC after detection         | —                                        |
| (1, 2)  | Vibration X                         | —                                        |
| (2, 0)  | Position relays NWKR + RWKR (step)  | digital 0/1                              |
| (2, 1)  | Contactor relays NWCR + RWCR (step) | digital 0/1                              |
| (2, 2)  | Status text panel                   | live state, label, alarms                |

Status text colours: black for `NORMAL`, dark-orange for `MAINTENANCE_ALERT`,
red for `FAULT`.

### Window 2 — Conditioned Signals

Built by `subscriber/conditioned_dashboard.py`, using the pipeline from
`subscriber/signal_conditioning.py`:

```
raw  →  Median filter   (kernel = 5)        # removes single-sample spikes
     →  Savitzky-Golay  (window = 11, p=2)  # smooths while preserving waveform
     →  Kalman 1-D      (q = 1e-3, r = 0.5) # optimal constant-value estimate
     →  conditioned signal
```

Each panel overlays the raw stream (faded gray) and the conditioned output
(blue) so you can see exactly what the filters do. The Kalman filter is a
custom 1-D constant-value estimator; the other two come from `scipy.signal`.

### Tuning notes

The default values lean toward heavy smoothing — good for vibration and
slow voltage drift, too aggressive for relay step signals or motor-current
inrush spikes. Adjust per signal type in `subscriber/signal_conditioning.py`:

| Signal type       | Recommended treatment                              |
|-------------------|-----------------------------------------------------|
| Continuous noisy  | Defaults are fine                                  |
| Slow drift        | Lower `KALMAN_R` (e.g. `0.05`) for less lag        |
| Step / digital    | Skip the pipeline; plot raw                        |
| Sharp transients  | Drop `MEDIAN_KERNEL` to `3` to keep narrow peaks   |

### Subscriber configuration

Defined in `subscriber/config.py`:

| Constant            | Value                  | Role                                |
|---------------------|------------------------|--------------------------------------|
| `DATA_FILE`         | `received_data.jsonl`  | Append-only persistent log          |
| `FILTERED_FILE`     | `filtered_value.json`  | Conditioned-signal log              |
| `MAX_POINTS`        | `300`                  | Rolling window length               |
| `PLOT_INTERVAL_MS`  | `250`                  | GUI refresh period                  |
| `LOG_EVERY`         | `10`                   | Print 1-in-N message summaries      |

Signal conditioning constants in `subscriber/signal_conditioning.py`:

| Constant            | Value   | Role                                |
|---------------------|---------|--------------------------------------|
| `MEDIAN_KERNEL`     | `5`     | Median-filter kernel size           |
| `SAVGOL_WINDOW`     | `11`    | Savitzky-Golay window length        |
| `SAVGOL_POLY`       | `2`     | Savitzky-Golay polynomial order     |
| `KALMAN_Q`          | `1e-3`  | Kalman process noise                |
| `KALMAN_R`          | `0.5`   | Kalman measurement noise            |

---

## Setup

```bash
pip install paho-mqtt cryptography matplotlib scipy
```

Both publisher and subscriber share `secret.key` via `common/encryption.py` —
keep them in the same directory, or copy the key file across hosts.

## Running

In two terminals from the `mqtt/` directory (any order, the publisher creates the key):

```bash
# Terminal 1
python pub.py

# Terminal 2
python sub.py
```

Two matplotlib windows pop up: live FRS dashboard + conditioned-signal panel.
`received_data.jsonl` grows one line per received record.

Ctrl+C in either terminal stops cleanly (publisher disconnects MQTT, subscriber
closes the log files and disconnects).

## File outputs

| File                  | Producer | Format                                    |
|-----------------------|----------|-------------------------------------------|
| `secret.key`          | pub.py   | Raw Fernet key bytes (do not commit)      |
| `received_data.jsonl` | sub.py   | One JSON record per line, append-only     |
| `filtered_value.json` | sub.py   | One conditioned record per line, append-only |
