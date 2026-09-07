"""The climate entity: power, mode, temperature, humidity, fan and both swings."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .device import DaikinIrDevice


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([DaikinIrClimate(entry.runtime_data)])


class DaikinIrClimate(ClimateEntity):
    """Assumed-state climate entity for an IR-controlled Daikin unit."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False
    _attr_assumed_state = True
    _attr_translation_key = "daikin_ir"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _BASE_FEATURES = (
        ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
        | ClimateEntityFeature.SWING_HORIZONTAL_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, device: DaikinIrDevice) -> None:
        self.device = device
        caps = device.protocol.capabilities
        self._attr_unique_id = device.entry.entry_id
        self._attr_device_info = device.device_info
        self._attr_hvac_modes = [HVACMode.OFF, *(HVACMode(m) for m in caps.hvac_modes)]
        self._attr_fan_modes = list(caps.fan_modes)
        self._attr_swing_modes = list(caps.swing_modes)
        self._attr_swing_horizontal_modes = list(caps.swing_horizontal_modes)
        self._attr_target_temperature_step = caps.temp_step
        self._attr_target_humidity_step = caps.humidity_step

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.device.add_listener(self.async_write_ha_state))

    # ── reported state ───────────────────────────────────────────────────────

    @property
    def _state(self):
        return self.device.state

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Only offer the sliders the unit accepts in the current mode."""
        features = self._BASE_FEATURES
        settable = self.device.protocol.settable(self._state)
        if "temp" in settable:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE
        if "humidity" in settable:
            features |= ClimateEntityFeature.TARGET_HUMIDITY
        return features

    @property
    def hvac_mode(self) -> HVACMode:
        return HVACMode(self._state.mode) if self._state.power else HVACMode.OFF

    @property
    def current_temperature(self) -> float | None:
        return self.device.current_temperature

    @property
    def current_humidity(self) -> float | None:
        return self.device.current_humidity

    @property
    def target_temperature(self) -> float | None:
        # In auto the unit picks the temperature and the offset number entity is
        # the only handle; dry and fan-only have no temperature setting at all.
        # Report nothing rather than a value the slider cannot change.
        if "temp" not in self.device.protocol.settable(self._state):
            return None
        return self._state.temp

    @property
    def min_temp(self) -> float:
        return self.device.protocol.temp_range(self._state)[0]

    @property
    def max_temp(self) -> float:
        return self.device.protocol.temp_range(self._state)[1]

    @property
    def target_humidity(self) -> int | None:
        if "humidity" not in self.device.protocol.settable(self._state):
            return None
        return self._state.humidity

    @property
    def min_humidity(self) -> int:
        return self.device.protocol.humidity_range(self._state)[0]

    @property
    def max_humidity(self) -> int:
        return self.device.protocol.humidity_range(self._state)[1]

    @property
    def fan_mode(self) -> str:
        return self._state.fan

    @property
    def swing_mode(self) -> str:
        return self._state.swing_v

    @property
    def swing_horizontal_mode(self) -> str:
        return self._state.swing_h

    # ── commands ─────────────────────────────────────────────────────────────

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.device.async_set(power=False)
            return
        aliases = self.device.protocol.mode_aliases
        mode = aliases.get(str(hvac_mode), str(hvac_mode))
        await self.device.async_set(power=True, mode=mode)

    async def async_turn_on(self) -> None:
        await self.device.async_set(power=True)

    async def async_turn_off(self) -> None:
        await self.device.async_set(power=False)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        if "temp" not in self.device.protocol.settable(self._state):
            return  # see target_temperature
        await self.device.async_set(temp=float(temperature))

    async def async_set_humidity(self, humidity: int) -> None:
        # apply() turns this into the matching set point on the select.
        await self.device.async_set(humidity=int(humidity))

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        await self.device.async_set(fan=fan_mode)

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        await self.device.async_set(swing_v=swing_mode)

    async def async_set_swing_horizontal_mode(self, swing_horizontal_mode: str) -> None:
        await self.device.async_set(swing_h=swing_horizontal_mode)
