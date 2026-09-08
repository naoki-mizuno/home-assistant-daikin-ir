"""One-shot commands with no persisted state (mold proof / filter clean, run
once while the unit is stopped — see the module docstring in daikin312.py)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import DaikinIrEntity, controls_of
from .lib.protocol import BUTTON


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    device = entry.runtime_data
    async_add_entities(
        DaikinIrButton(device, control) for control in controls_of(device, BUTTON)
    )


class DaikinIrButton(DaikinIrEntity, ButtonEntity):
    async def async_press(self) -> None:
        await self.device.async_press(self.control.key)
