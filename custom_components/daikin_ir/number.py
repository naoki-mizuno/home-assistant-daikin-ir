"""Numeric controls — currently the Comfort Auto temperature offset."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import DaikinIrEntity, controls_of
from .lib.protocol import NUMBER


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    device = entry.runtime_data
    async_add_entities(
        DaikinIrNumber(device, control) for control in controls_of(device, NUMBER)
    )


class DaikinIrNumber(DaikinIrEntity, NumberEntity):
    _attr_assumed_state = True
    _attr_mode = NumberMode.SLIDER

    def __init__(self, device, control) -> None:
        super().__init__(device, control)
        self._attr_native_min_value = control.min
        self._attr_native_max_value = control.max
        self._attr_native_step = control.step
        self._attr_native_unit_of_measurement = control.unit

    @property
    def native_value(self) -> float:
        return float(self.value)

    async def async_set_native_value(self, value: float) -> None:
        await self.async_set(value)
