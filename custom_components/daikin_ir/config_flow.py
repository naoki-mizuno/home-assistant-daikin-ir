"""GUI setup: one config entry per A/C unit (each has its own IR blaster)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CODEC,
    CONF_HUMIDITY_SENSOR,
    CONF_MQTT_TOPIC,
    CONF_PAYLOAD_KEY,
    CONF_POWER_SENSOR,
    CONF_PROTOCOL,
    CONF_TEMPERATURE_SENSOR,
    DEFAULT_CODEC,
    DEFAULT_PROTOCOL,
    DOMAIN,
)
from .lib import codecs, protocol_labels


def _options(labels: dict[str, str]) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value=value, label=label)
                for value, label in labels.items()
            ],
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _entity(domains: list[str]) -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain=domains, multiple=False)
    )


def _schema(defaults: dict[str, Any], *, with_name: bool) -> vol.Schema:
    """Build the form; `defaults` prefills it when reconfiguring."""
    fields: dict[Any, Any] = {}
    if with_name:
        fields[vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, ""))] = str
    fields.update(
        {
            vol.Required(
                CONF_PROTOCOL, default=defaults.get(CONF_PROTOCOL, DEFAULT_PROTOCOL)
            ): _options(protocol_labels()),
            vol.Required(
                CONF_CODEC, default=defaults.get(CONF_CODEC, DEFAULT_CODEC)
            ): _options({name: label for name, (label, _) in codecs.CODECS.items()}),
            vol.Required(
                CONF_MQTT_TOPIC, default=defaults.get(CONF_MQTT_TOPIC, "")
            ): str,
            # Blank means "whatever this codec's blaster normally expects".
            vol.Optional(
                CONF_PAYLOAD_KEY,
                description={"suggested_value": defaults.get(CONF_PAYLOAD_KEY)},
            ): str,
            vol.Optional(
                CONF_TEMPERATURE_SENSOR,
                description={"suggested_value": defaults.get(CONF_TEMPERATURE_SENSOR)},
            ): _entity(["sensor"]),
            vol.Optional(
                CONF_HUMIDITY_SENSOR,
                description={"suggested_value": defaults.get(CONF_HUMIDITY_SENSOR)},
            ): _entity(["sensor"]),
            vol.Optional(
                CONF_POWER_SENSOR,
                description={"suggested_value": defaults.get(CONF_POWER_SENSOR)},
            ): _entity(["binary_sensor", "sensor", "switch", "input_boolean"]),
        }
    )
    return vol.Schema(fields)


class DaikinIrConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add one A/C unit."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title=user_input.pop(CONF_NAME), data=user_input
            )
        return self.async_show_form(
            step_id="user", data_schema=_schema({}, with_name=True)
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return DaikinIrOptionsFlow()


class DaikinIrOptionsFlow(OptionsFlow):
    """Edit an existing unit — same form, minus the name."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init", data_schema=_schema(current, with_name=False)
        )
