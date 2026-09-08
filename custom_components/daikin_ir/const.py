"""Constants and config keys."""

from __future__ import annotations

DOMAIN = "daikin_ir"

CONF_PROTOCOL = "protocol"
CONF_CODEC = "codec"
CONF_MQTT_TOPIC = "mqtt_topic"
CONF_PAYLOAD_KEY = "payload_key"
CONF_SEND_DELAY = "send_delay"
CONF_TEMPERATURE_SENSOR = "temperature_sensor"
CONF_HUMIDITY_SENSOR = "humidity_sensor"
CONF_POWER_SENSOR = "power_sensor"

DEFAULT_PROTOCOL = "daikin312"
DEFAULT_CODEC = "tuya"
# Long enough to swallow a script that sets several things at once, short
# enough that a button press still feels instant.
DEFAULT_SEND_DELAY = 0.1

STORAGE_VERSION = 1
