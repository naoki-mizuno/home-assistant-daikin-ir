"""One A/C unit: holds its assumed state and pushes IR codes to its blaster.

IR is write-only, so this is the single source of truth for what the unit was
last told. It is persisted, because losing it across a restart would leave the
UI lying about the unit.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CODEC,
    CONF_HUMIDITY_SENSOR,
    CONF_MQTT_TOPIC,
    CONF_PAYLOAD_KEY,
    CONF_POWER_SENSOR,
    CONF_PROTOCOL,
    CONF_TEMPERATURE_SENSOR,
    DOMAIN,
    STORAGE_VERSION,
)
from .lib import codecs, get_protocol

_LOGGER = logging.getLogger(__name__)

_UNUSABLE = (None, STATE_UNKNOWN, STATE_UNAVAILABLE, "")


class DaikinIrDevice:
    """State + transport for a single configured A/C."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        config = {**entry.data, **entry.options}

        self.protocol = get_protocol(config[CONF_PROTOCOL])
        self.codec: str = config[CONF_CODEC]
        self.topic: str = config[CONF_MQTT_TOPIC]
        self.payload_key: str = (
            config.get(CONF_PAYLOAD_KEY) or codecs.DEFAULT_PAYLOAD_KEY[self.codec]
        )
        self._sensors = {
            key: config.get(key)
            for key in (
                CONF_TEMPERATURE_SENSOR,
                CONF_HUMIDITY_SENSOR,
                CONF_POWER_SENSOR,
            )
        }

        self.state = self.protocol.new_state()
        self.current_temperature: float | None = None
        self.current_humidity: float | None = None

        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._listeners: list[Callable[[], None]] = []

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def async_setup(self) -> None:
        """Restore the last known state and start following the linked sensors."""
        if stored := await self._store.async_load():
            try:
                self.state = self.protocol.from_dict(stored)
            except (TypeError, ValueError):  # protocol changed under us
                _LOGGER.warning(
                    "Discarding incompatible stored state for %s", self.name
                )

        for key, entity_id in self._sensors.items():
            if entity_id:
                self._read_sensor(key, self.hass.states.get(entity_id))

        tracked = [entity_id for entity_id in self._sensors.values() if entity_id]
        if tracked:
            self.entry.async_on_unload(
                async_track_state_change_event(
                    self.hass, tracked, self._handle_sensor_event
                )
            )

    @property
    def name(self) -> str:
        return self.entry.title

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=self.name,
            manufacturer="Daikin",
            model=self.protocol.label,
        )

    # ── entity plumbing ──────────────────────────────────────────────────────

    def add_listener(self, update: Callable[[], None]) -> Callable[[], None]:
        """Register an entity's update callback; returns the unsubscribe."""
        self._listeners.append(update)
        return lambda: self._listeners.remove(update)

    @callback
    def _notify(self) -> None:
        for update in self._listeners:
            update()

    # ── commands ─────────────────────────────────────────────────────────────

    async def async_set(self, **changes: Any) -> None:
        """Apply changes stamped with the current clock, then send and persist.

        The clock must be stamped in the same apply() call as the real change:
        apply() decides what to announce by diffing against the prior state, so
        a separate clock-only apply() afterwards would see no real change and
        reset the announcement back to disabled.
        """
        now: datetime = dt_util.now()
        changes = {**changes, "clock": now.hour * 60 + now.minute}
        self.state = self.protocol.apply(self.state, changes)
        code = codecs.encode(
            self.codec, self.protocol.timings(self.state), self.protocol.freq
        )
        await mqtt.async_publish(
            self.hass, self.topic, json.dumps({self.payload_key: code})
        )
        await self._store.async_save(self.protocol.to_dict(self.state))
        self._notify()

    def get(self, key: str) -> Any:
        return getattr(self.state, key)

    # ── linked sensors ───────────────────────────────────────────────────────

    @callback
    def _handle_sensor_event(self, event: Event) -> None:
        entity_id = event.data["entity_id"]
        for key, tracked in self._sensors.items():
            if tracked == entity_id:
                self._read_sensor(key, event.data.get("new_state"))
        self._notify()

    @callback
    def _read_sensor(self, key: str, state: Any) -> None:
        value = state.state if state else None
        if value in _UNUSABLE:
            return
        if key == CONF_POWER_SENSOR:
            # The unit can be switched off by its own remote or a power cut; a
            # power sensor is the only way we ever learn about it. Never echoes
            # an IR frame back — this only corrects what we assume.
            power = value not in (STATE_OFF, "0", "false", "False")
            if power != self.state.power:
                self.state = self.protocol.apply(self.state, {"power": power})
            return
        try:
            number = float(value)
        except ValueError:
            return
        if key == CONF_TEMPERATURE_SENSOR:
            self.current_temperature = number
        else:
            self.current_humidity = number
