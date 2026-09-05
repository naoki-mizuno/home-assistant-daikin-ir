"""Daikin IR — control a Daikin A/C through any MQTT IR blaster."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .device import DaikinIrDevice

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.TIME,
]

type DaikinIrConfigEntry = ConfigEntry[DaikinIrDevice]


async def async_setup_entry(hass: HomeAssistant, entry: DaikinIrConfigEntry) -> bool:
    device = DaikinIrDevice(hass, entry)
    await device.async_setup()
    entry.runtime_data = device
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DaikinIrConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: DaikinIrConfigEntry) -> None:
    """Options changed (topic, codec, linked sensors) — rebuild the device."""
    await hass.config_entries.async_reload(entry.entry_id)
