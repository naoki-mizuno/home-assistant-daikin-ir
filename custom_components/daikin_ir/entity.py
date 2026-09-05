"""Base entity shared by every control platform."""

from __future__ import annotations

from homeassistant.const import EntityCategory
from homeassistant.helpers.entity import Entity

from .device import DaikinIrDevice
from .lib.protocol import Control


class DaikinIrEntity(Entity):
    """An entity backed by one field of the device's assumed state."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, device: DaikinIrDevice, control: Control) -> None:
        self.device = device
        self.control = control
        self._attr_unique_id = f"{device.entry.entry_id}_{control.key}"
        self._attr_translation_key = control.key
        self._attr_device_info = device.device_info
        self._attr_icon = control.icon
        if control.category:
            self._attr_entity_category = EntityCategory(control.category)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.device.add_listener(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        """False while the current HVAC mode ignores this control."""
        if self.control.modes is None:
            return True
        return getattr(self.device.state, "mode", None) in self.control.modes

    @property
    def value(self):
        return self.device.get(self.control.key)

    async def async_set(self, value) -> None:
        await self.device.async_set(**{self.control.key: value})


def controls_of(device: DaikinIrDevice, kind: str) -> list[Control]:
    """Every control of one entity kind, for a platform's async_setup_entry."""
    return [c for c in device.protocol.controls if c.kind == kind]
