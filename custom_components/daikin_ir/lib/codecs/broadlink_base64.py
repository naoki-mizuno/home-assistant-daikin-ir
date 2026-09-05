"""Broadlink IR packet format, base64 encoded.

Packet layout (the form HA's broadlink integration and SmartIR accept):

    0x26 0x00 <len LE16> <pulses…> 0x0d 0x05

Each pulse is a duration in 269/8192 µs⁻¹ ticks (~30.45 µs); values above 255
are escaped as 0x00 <BE16>.
"""

from __future__ import annotations

import base64
from struct import pack

_TICKS_PER_US = 269 / 8192
_IR_MODE = 0x26  # IR (as opposed to 0xb2 RF433 / 0xd7 RF315)
_TRAILER = b"\x0d\x05"


def encode(timings: list[int], freq: int = 38000) -> str:  # noqa: ARG001 - Broadlink hardware picks its own carrier
    """Encode raw IR µs durations to a Broadlink base64 code string."""
    pulses = bytearray()
    for us in timings:
        ticks = max(1, round(us * _TICKS_PER_US))
        if ticks < 256:
            pulses.append(ticks)
        else:
            pulses += b"\x00" + pack(">H", min(ticks, 0xFFFF))
    body = pulses + _TRAILER
    packet = pack("<BBH", _IR_MODE, 0, len(body)) + body
    return base64.b64encode(packet).decode()


def decode(code: str) -> list[int]:
    """Decode a Broadlink base64 code string back to raw µs durations."""
    packet = base64.b64decode(code)
    body = packet[4 : 4 + int.from_bytes(packet[2:4], "little")]
    if body.endswith(_TRAILER):
        body = body[: -len(_TRAILER)]

    timings: list[int] = []
    i = 0
    while i < len(body):
        if body[i]:
            ticks, i = body[i], i + 1
        else:
            ticks, i = int.from_bytes(body[i + 1 : i + 3], "big"), i + 3
        timings.append(round(ticks / _TICKS_PER_US))
    return timings
