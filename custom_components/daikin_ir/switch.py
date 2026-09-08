"""Boolean controls (powerful, streamer air purifying, cleaning filter …)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import DaikinIrEntity, controls_of
from .lib.protocol import SWITCH


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    device = entry.runtime_data
    async_add_entities(
        DaikinIrSwitch(device, control) for control in controls_of(device, SWITCH)
    )


class DaikinIrSwitch(DaikinIrEntity, SwitchEntity):
    _attr_assumed_state = True

    @property
    def is_on(self) -> bool:
        return bool(self.value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.async_set(False)
