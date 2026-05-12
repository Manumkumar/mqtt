"""
ShareV d MQTT and encryption configuration.

All broker credentials, topic names, and key-file paths live here so that
publisher and subscriber stay in sync without duplicating magic strings.
"""

# ---- MQTT broker ----
MQTT_HOST = "relldevices.in"
MQTT_PORT = 1883
MQTT_USER = "mosquitto"
MQTT_PASS = "dIju32432saafgsd"

# ---- Topic ----
TOPIC = "rdpms/point-machine"

# ---- Encryption ----
KEY_FILE = "secret.key"
