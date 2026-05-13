"""
Subscriber entry point.

Wires together the MQTT client, data store, data logger, control panel,
and all matplotlib dashboards, then blocks on ``plt.show()``.
"""

import matplotlib.pyplot as plt

from subscriber.data_store import DataStore
from subscriber.data_logging import DataLogger
from subscriber.mqtt_client import create_client
from subscriber.dashboard import create_raw_dashboard
from subscriber.conditioned_dashboard import create_conditioned_dashboard
from subscriber.features_dashboard import create_features_dashboard
from subscriber.correlation_dashboard import create_correlation_dashboard
from subscriber.time_features_dashboard import create_time_features_dashboard
from subscriber.control_panel import create_control_panel


def run() -> None:
    """Start the subscriber with live dashboards."""
    data_store = DataStore()
    data_logger = DataLogger()
    client = create_client(data_store, data_logger)

    # Build all dashboard windows (must keep references to animations)
    fig1, ani1 = create_raw_dashboard(data_store)
    fig2, ani2 = create_conditioned_dashboard(data_store)
    fig3, ani3 = create_features_dashboard(data_store)
    fig4, ani4 = create_correlation_dashboard(data_store)
    fig5, ani5 = create_time_features_dashboard(data_store)

    # Control panel to toggle dashboard visibility
    dashboards = {
        "FRS Raw Telemetry":    (fig1, ani1),
        "Conditioned Signals":  (fig2, ani2),
        "Time-Domain Features": (fig3, ani3),
        "V-I-Vib Correlations": (fig4, ani4),
        "System Time Features": (fig5, ani5),
    }
    _ctrl_fig, _ctrl_check = create_control_panel(dashboards)

    try:
        plt.show()
    finally:
        client.loop_stop()
        client.disconnect()
        data_logger.close()
