"""Constants and config keys."""

from __future__ import annotations

DOMAIN = "daikin_ir"

CONF_PROTOCOL = "protocol"
CONF_CODEC = "codec"
CONF_MQTT_TOPIC = "mqtt_topic"
CONF_PAYLOAD_KEY = "payload_key"
CONF_TEMPERATURE_SENSOR = "temperature_sensor"
CONF_HUMIDITY_SENSOR = "humidity_sensor"
CONF_POWER_SENSOR = "power_sensor"

DEFAULT_PROTOCOL = "daikin312"
DEFAULT_CODEC = "tuya"

STORAGE_VERSION = 1
