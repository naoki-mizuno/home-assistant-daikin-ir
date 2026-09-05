"""Timer controls (入タイマー / 切タイマー).

The unit stores absolute clock times, not durations, which is why every frame
also carries the current time (see `DaikinIrDevice.async_set`).
"""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import DaikinIrEntity, controls_of
from .lib.protocol import TIME


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    device = entry.runtime_data
    async_add_entities(
        DaikinIrTime(device, control) for control in controls_of(device, TIME)
    )


class DaikinIrTime(DaikinIrEntity, TimeEntity):
    _attr_assumed_state = True

    @property
    def native_value(self) -> time:
        minutes = int(self.value)
        return time(hour=minutes // 60 % 24, minute=minutes % 60)

    async def async_set_value(self, value: time) -> None:
        # The remote's timers only have 10 minute granularity in the UI, but the
        # field is per-minute, so pass it through as given.
        await self.async_set(value.hour * 60 + value.minute)
