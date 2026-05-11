"""
JSONL data logging for raw and conditioned telemetry.

Uses line-buffered append-only files: O(1) per record, no full-file rewrites.
"""

import json

from subscriber.config import DATA_FILE, FILTERED_FILE, FILTERED_PARAMS
from subscriber.signal_conditioning import condition_signal


class DataLogger:
    """Manages raw and filtered JSONL log files."""

    def __init__(self):
        self._raw_file = open(DATA_FILE, "a", buffering=1)
        self._filtered_file = open(FILTERED_FILE, "a", buffering=1)

    def append_raw(self, record: dict) -> None:
        """Write one raw telemetry record."""
        self._raw_file.write(json.dumps(record))
        self._raw_file.write("\n")

    def append_filtered(self, timestamp: float, fault: str, label: str,
                        buffers: dict) -> None:
        """Compute conditioned values and write one filtered record.

        Parameters
        ----------
        buffers : dict
            Snapshot of ``{param: list_of_values}`` for FILTERED_PARAMS.
        """
        record = {"timestamp": timestamp, "fault": fault, "label": label}
        for p in FILTERED_PARAMS:
            clean = condition_signal(buffers.get(p, []))
            record[p] = round(clean[-1], 4) if clean else 0.0
        self._filtered_file.write(json.dumps(record))
        self._filtered_file.write("\n")

    def close(self) -> None:
        """Flush and close both log files."""
        self._raw_file.close()
        self._filtered_file.close()
