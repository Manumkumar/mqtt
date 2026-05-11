"""
Subscriber entry point.

Wires together the MQTT client, data store, data logger, and both
matplotlib dashboards, then blocks on ``plt.show()``.
"""

import matplotlib.pyplot as plt

from subscriber.data_store import DataStore
from subscriber.data_logging import DataLogger
from subscriber.mqtt_client import create_client
from subscriber.dashboard import create_raw_dashboard
from subscriber.conditioned_dashboard import create_conditioned_dashboard


def run() -> None:
    """Start the subscriber with live dashboards."""
    data_store = DataStore()
    data_logger = DataLogger()
    client = create_client(data_store, data_logger)

    # Build both dashboard windows (must keep references to animations)
    _fig1, _ani1 = create_raw_dashboard(data_store)
    _fig2, _ani2 = create_conditioned_dashboard(data_store)

    try:
        plt.tight_layout(rect=[0, 0, 1, 0.96])
        plt.show()
    finally:
        client.loop_stop()
        client.disconnect()
        data_logger.close()
