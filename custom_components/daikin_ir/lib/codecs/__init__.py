"""Output code formats.

A codec turns a list of raw IR durations (microseconds, mark/space alternating,
starting with a mark) into the string an IR blaster expects.

Add a format by dropping a module in here with `encode(timings, freq)` and
registering it below.
"""

from __future__ import annotations

from collections.abc import Callable

from . import broadlink_base64, tuya

# name -> (label shown in the config flow, encoder)
CODECS: dict[str, tuple[str, Callable[[list[int], int], str]]] = {
    "tuya": ("Tuya (base64)", tuya.encode),
    "broadlink_base64": ("Broadlink (base64)", broadlink_base64.encode),
}

# Default MQTT payload key per codec. Zigbee2MQTT's Tuya IR blasters read
# `ir_code_to_send`; other bridges may differ, so allow it to be edited.
DEFAULT_PAYLOAD_KEY: dict[str, str] = {
    "tuya": "ir_code_to_send",
    "broadlink_base64": "ir_code_to_send",
}


def encode(codec: str, timings: list[int], freq: int) -> str:
    """Encode raw µs timings with the named codec."""
    return CODECS[codec][1](timings, freq)


__all__ = ["CODECS", "DEFAULT_PAYLOAD_KEY", "encode"]
