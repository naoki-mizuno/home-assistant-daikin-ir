"""Multiple-choice controls (湿度設定, 留守エコ, ブザー, ランプ, タイマー種別)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import DaikinIrEntity, controls_of
from .lib.protocol import SELECT


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    device = entry.runtime_data
    async_add_entities(
        DaikinIrSelect(device, control) for control in controls_of(device, SELECT)
    )


class DaikinIrSelect(DaikinIrEntity, SelectEntity):
    _attr_assumed_state = True

    @property
    def options(self) -> list[str]:
        """Per-mode, so a mode that forbids an option stops offering it."""
        return list(self.device.protocol.options_for(self.control, self.device.state))

    @property
    def current_option(self) -> str:
        return str(self.value)

    async def async_select_option(self, option: str) -> None:
        await self.async_set(option)
