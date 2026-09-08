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
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector

from .const import (
    CODEC_INFRARED,
    CONF_CODEC,
    CONF_HUMIDITY_SENSOR,
    CONF_INFRARED_ENTITY,
    CONF_MQTT_TOPIC,
    CONF_PAYLOAD_KEY,
    CONF_POWER_SENSOR,
    CONF_PROTOCOL,
    CONF_SEND_DELAY,
    CONF_TEMPERATURE_SENSOR,
    DEFAULT_CODEC,
    DEFAULT_PROTOCOL,
    DOMAIN,
    INFRARED_DOMAIN,
)
from .lib import codecs, protocol_labels

# Fields for each group
SECTION_MQTT = "mqtt"
SECTION_INFRARED = "infrared"
SECTIONS = {
    SECTION_MQTT: (CONF_MQTT_TOPIC, CONF_PAYLOAD_KEY),
    SECTION_INFRARED: (CONF_INFRARED_ENTITY,),
}


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


def _emitters(hass: HomeAssistant) -> list[str]:
    """Entity ids of the infrared emitters this Home Assistant has, if any.

    Empty before 2026.4, and on any install whose blasters are all driven over
    plain MQTT, in which case the infrared output format simply cannot be
    completed, which is what the form tells the user.
    """
    try:
        from homeassistant.components.infrared import async_get_emitters
    except ImportError:
        return []
    return async_get_emitters(hass)


def _codec_labels() -> dict[str, str]:
    return {
        **{name: label for name, (label, _) in codecs.CODECS.items()},
        CODEC_INFRARED: "Home Assistant infrared entity",
    }


def _schema(
    hass: HomeAssistant, defaults: dict[str, Any], *, with_name: bool
) -> vol.Schema:
    """Build the form; `defaults` prefills it when reconfiguring."""
    # Only one of the two groups is ever used, so open the one the saved output
    # format needs and fold the other away.
    infrared = defaults.get(CONF_CODEC, DEFAULT_CODEC) == CODEC_INFRARED
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
            ): _options(_codec_labels()),
            # Form doesn't have a built-in mutual exclusion, so every field
            # in both is optional here and _errors() insists on the right one.
            vol.Required(SECTION_MQTT): section(
                vol.Schema(
                    {
                        vol.Optional(
                            CONF_MQTT_TOPIC,
                            default=defaults.get(CONF_MQTT_TOPIC, ""),
                        ): str,
                        # Blank = codec's default.
                        vol.Optional(
                            CONF_PAYLOAD_KEY,
                            description={
                                "suggested_value": defaults.get(CONF_PAYLOAD_KEY)
                            },
                        ): str,
                    }
                ),
                {"collapsed": infrared},
            ),
            vol.Required(SECTION_INFRARED): section(
                vol.Schema(
                    {
                        vol.Optional(
                            CONF_INFRARED_ENTITY,
                            description={
                                "suggested_value": defaults.get(CONF_INFRARED_ENTITY)
                            },
                        ): selector.EntitySelector(
                            selector.EntitySelectorConfig(
                                domain=INFRARED_DOMAIN,
                                include_entities=_emitters(hass),
                                multiple=False,
                            )
                        ),
                    }
                ),
                {"collapsed": not infrared},
            ),
            # Blank means DEFAULT_SEND_DELAY, so an entry that never set one
            # follows the default. To indicate "one frame per change," 0 must be
            # explicitly set.
            vol.Optional(
                CONF_SEND_DELAY,
                description={"suggested_value": defaults.get(CONF_SEND_DELAY)},
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=5,
                    step=0.05,
                    unit_of_measurement="s",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
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


def _flatten(user_input: dict[str, Any]) -> dict[str, Any]:
    """Lift the grouped fields back to the top level of a flat entry."""
    flat = {key: value for key, value in user_input.items() if key not in SECTIONS}
    for name in SECTIONS:
        flat.update(user_input.get(name) or {})
    return flat


def _errors(user_input: dict[str, Any]) -> dict[str, str]:
    """Complain based on chosen output format.
    """
    if user_input[CONF_CODEC] == CODEC_INFRARED:
        if not user_input.get(CONF_INFRARED_ENTITY):
            return {"base": "infrared_entity_required"}
    elif not user_input.get(CONF_MQTT_TOPIC):
        return {"base": "mqtt_topic_required"}
    return {}


class DaikinIrConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add one A/C unit."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = _flatten(user_input)
            if not (errors := _errors(user_input)):
                # Unused fields are left in place rather than stripped
                # so that it can be used when switching back later.
                return self.async_create_entry(
                    title=user_input.pop(CONF_NAME), data=user_input
                )
        return self.async_show_form(
            step_id="user",
            data_schema=_schema(self.hass, user_input or {}, with_name=True),
            errors=errors,
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
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = _flatten(user_input)
            if not (errors := _errors(user_input)):
                return self.async_create_entry(data=user_input)
            current = user_input
        else:
            current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(self.hass, current, with_name=False),
            errors=errors,
        )
