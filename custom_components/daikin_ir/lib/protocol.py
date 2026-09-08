"""Protocol interface shared by every supported A/C protocol.

A protocol owns everything IR-specific: the state it can express, how a change
is validated, and how a state becomes raw µs timings. The Home Assistant layer
only ever sees this interface, so adding e.g. Daikin216 is one module plus a
registry entry.

State objects are plain dataclasses with JSON-friendly values (bools, numbers,
option strings), so they survive a restart through `RestoreEntity`.
"""

from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from typing import Any

# Home Assistant HVAC mode strings used as protocol mode keys.
MODE_OFF = "off"
MODE_AUTO = "auto"
MODE_HEAT_COOL = "heat_cool"
MODE_COOL = "cool"
MODE_HEAT = "heat"
MODE_DRY = "dry"
MODE_FAN_ONLY = "fan_only"

SWITCH = "switch"
SELECT = "select"
NUMBER = "number"
TIME = "time"


@dataclasses.dataclass(frozen=True, slots=True)
class Control:
    """One state field exposed as its own entity (not part of `climate`)."""

    key: str
    kind: str
    options: tuple[str, ...] = ()
    min: float | None = None
    max: float | None = None
    step: float | None = None
    unit: str | None = None
    # HVAC modes the control does something in; None means "always".
    modes: tuple[str, ...] | None = None
    # HA EntityCategory value, or None to put it on the main dashboard card.
    category: str | None = "config"
    icon: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class Capabilities:
    """What the `climate` entity can offer for this protocol."""

    hvac_modes: tuple[str, ...]
    fan_modes: tuple[str, ...]
    swing_modes: tuple[str, ...]
    swing_horizontal_modes: tuple[str, ...]
    humidity_modes: tuple[str, ...]
    temp_step: float = 0.5
    humidity_step: int = 5  # every Daikin remote we've seen steps humidity by 5%


class Protocol(ABC):
    """Base class for an IR protocol."""

    name: str
    label: str
    freq: int
    capabilities: Capabilities
    controls: tuple[Control, ...]
    # HA hvac_mode string -> the mode this protocol actually stores it as.
    # Empty for protocols where every HA mode is a distinct unit mode; a
    # protocol whose unit conflates two HA modes (e.g. Daikin312's single
    # Comfort Auto mode answering to both "auto" and "heat_cool") overrides this.
    mode_aliases: dict[str, str] = {}

    @abstractmethod
    def new_state(self) -> Any:
        """Return a fresh state with sane defaults."""

    @abstractmethod
    def apply(self, state: Any, changes: dict[str, Any]) -> Any:
        """Return a new state with `changes` applied, clamped and made consistent.

        Also decides what the unit should announce, from which keys changed.
        """

    @abstractmethod
    def timings(self, state: Any) -> list[int]:
        """Render a state as raw IR durations in µs (mark/space, starting on a mark)."""

    @abstractmethod
    def temp_range(self, state: Any) -> tuple[float, float]:
        """Return (min, max) target temperature for the state's current mode."""

    @abstractmethod
    def humidity_range(self, state: Any) -> tuple[int, int]:
        """Return (min, max) target humidity for the state's current mode."""

    def settable(self, state: Any) -> frozenset[str]:
        """Which of {"temp", "humidity"} the unit accepts in the current mode.

        A mode the unit gives no setting for must not show a slider the frame
        cannot carry, so `climate` drops the feature instead of offering a
        control that silently does nothing.
        """
        return frozenset({"temp", "humidity"})

    def options_for(self, control: Control, state: Any) -> tuple[str, ...]:
        """The options a select may offer in the current mode.

        Defaults to all of them; override where a mode forbids one, so the
        option disappears rather than being accepted and then clamped away.
        """
        return control.options

    def to_dict(self, state: Any) -> dict[str, Any]:
        return dataclasses.asdict(state)

    def from_dict(self, data: dict[str, Any]) -> Any:
        state = self.new_state()
        known = {f.name for f in dataclasses.fields(state)}
        wanted = {k: v for k, v in data.items() if k in known}
        return dataclasses.replace(state, **wanted)


_PROTOCOLS: dict[str, Protocol] = {}


def register(protocol: Protocol) -> Protocol:
    _PROTOCOLS[protocol.name] = protocol
    return protocol


def get_protocol(name: str) -> Protocol:
    return _PROTOCOLS[name]


def protocol_labels() -> dict[str, str]:
    """name -> human label, for the config flow dropdown."""
    return {name: p.label for name, p in _PROTOCOLS.items()}
