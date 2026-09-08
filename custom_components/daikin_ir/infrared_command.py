"""Bridge to Home Assistant's native infrared platform (HA 2026.4 and newer).

The platform hands an emitter entity raw µs timings and leaves the hardware's
own code format to it, so nothing here encodes anything: `lib/codecs` exists
only for blasters this integration publishes to over MQTT itself.

`async_send_command` takes an `InfraredCommand`, not a list, so a frame needs
this wrapper to be sendable at all. It lives outside `lib/`, which stays free of
Home Assistant imports.
"""

from __future__ import annotations

from homeassistant.components.infrared import InfraredCommand

from .lib import negate_spaces


class RawTimings(InfraredCommand):
    """One protocol frame, as a command the infrared platform can send.

    The platform is transport-only, so a command carrying the timings verbatim
    is all a protocol that already renders its own frames needs. Going through
    `ProntoCommand` instead would quantise every duration to one carrier period
    (27 µs at Daikin's 36.7 kHz) for nothing.
    """

    def __init__(self, timings: list[int], modulation: int) -> None:
        super().__init__(modulation=modulation)
        self._timings = negate_spaces(timings)

    def get_raw_timings(self) -> list[int]:
        return self._timings
