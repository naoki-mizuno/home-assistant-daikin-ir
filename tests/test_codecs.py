"""Output codec checks.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from custom_components.daikin_ir.lib import codecs
from custom_components.daikin_ir.lib.codecs import broadlink_base64, tuya

BASELINE = next(
    c
    for c in json.loads(
        (Path(__file__).parent / "fixtures" / "daikin312_IRremoteESP8266.json").read_text()
    )
    if c["label"] == "baseline"
)["timings"]


def test_tuya_round_trip():
    assert tuya.decode(tuya.encode(BASELINE, 36700)) == BASELINE


def test_broadlink_round_trip():
    # Broadlink counts in ~30.5 µs ticks, so half a tick of drift is the floor.
    decoded = broadlink_base64.decode(broadlink_base64.encode(BASELINE, 36700))
    assert len(decoded) == len(BASELINE)
    assert all(abs(a - b) <= 16 for a, b in zip(decoded, BASELINE, strict=True))


def test_broadlink_packet_layout():
    packet = base64.b64decode(broadlink_base64.encode(BASELINE, 36700))
    assert packet[0] == 0x26  # IR mode
    assert packet[1] == 0x00  # repeat count
    assert int.from_bytes(packet[2:4], "little") == len(packet) - 4
    assert packet[-2:] == b"\x0d\x05"
    # 10024 µs is far past one byte, so the long-pulse escape must be used.
    assert packet[4] == 0x00 and int.from_bytes(packet[5:7], "big") > 0xFF
