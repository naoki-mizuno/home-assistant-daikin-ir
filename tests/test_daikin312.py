"""Daikin312 encoder checks.

Two independent references:

* `daikin312_IRremoteESP8266.json`: frames from the SWIG-wrapped IRremoteESP8266
  build. Proves the pure-Python port matches that C++ implementation — not
  that either is correct, since Daikin never published the protocol.
* `daikin312_captures.json`: frames captured from a real ARC472A43 remote.
  Proves the bit map matches the hardware, including unknown header bits.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from lib import daikin312 as d

FIXTURES = Path(__file__).parent / "fixtures"
IRREMOTEESP8266 = json.loads((FIXTURES / "daikin312_IRremoteESP8266.json").read_text())
CAPTURES = json.loads((FIXTURES / "daikin312_captures.json").read_text())

PROTOCOL = d.PROTOCOL

# What IRDaikin312::stateReset() plus the SWIG wrapper's arguments amount to.
BASE = d.Daikin312State(
    power=True,
    mode="cool",
    temp=25.0,
    fan="auto",
    swing_v="off",
    swing_h="off",
    beep="quiet",
    light="bright",
    announce_item=0,
    clock=0x458,
)


def _frame(state_overrides: dict) -> str:
    state = dataclasses.replace(BASE, **state_overrides)
    return " ".join(f"{b:02X}" for b in PROTOCOL.pack(state).raw)


@pytest.mark.parametrize("case", IRREMOTEESP8266, ids=lambda c: c["label"])
def test_matches_irremoteesp8266(case):
    assert _frame(case["state"]) == " ".join(case["raw"])


def test_timings_match_irremoteesp8266():
    baseline = next(c for c in IRREMOTEESP8266 if c["label"] == "baseline")
    assert PROTOCOL.timings(BASE) == baseline["timings"]


def test_checksums_validate():
    frame = PROTOCOL.pack(dataclasses.replace(BASE, mode="heat", temp=21.5))
    assert frame.valid_checksum()


# ── Real remote captures ─────────────────────────────────────────────────────


def _capture(label: str) -> d.Daikin312Raw:
    entry = next(c for c in CAPTURES if c["label"] == label)
    return d.Daikin312Raw(bytes(int(b, 16) for b in entry["raw"]))


def test_captures_have_valid_checksums():
    for entry in CAPTURES:
        frame = d.Daikin312Raw(bytes(int(b, 16) for b in entry["raw"]))
        assert frame.valid_checksum(), entry["label"]


@pytest.mark.parametrize(
    ("label", "field", "expected"),
    [
        # Bits where the real remote disagrees with, or is missing from,
        # IRremoteESP8266's `union Daikin312Protocol` header (ir_Daikin.h) —
        # see the module docstring in daikin312.py.
        ("streamer on", "Streamer", 1),
        ("streamer off", "Streamer", 0),
        ("filter_clean on (0x17)", "FilterClean", 1),
        ("filter_clean off", "FilterClean", 0),
        ("sensor_airflow area", "SensorAirflow", d.SENSOR_AIRFLOW["area"]),
        ("sensor_airflow spot", "SensorAirflow", d.SENSOR_AIRFLOW["spot"]),
        ("sensor_airflow cancel", "SensorAirflow", 0),
        ("sleep on", "Sleep", 1),
        ("sleep off", "Sleep", 0),
        # Bits IRremoteESP8266's `union Daikin312Protocol` header (ir_Daikin.h)
        # does describe correctly.
        ("powerful on", "Powerful", 1),
        ("powerful off", "Powerful", 0),
        ("heat_high on", "HeatHigh", 1),
        ("eye 1h", "EyeTimer", 1),
        ("eye 3h", "EyeTimer", 2),
        ("eye off", "EyeTimer", 0),
        ("dry + humidity 50", "Humidity", 50),
        ("dry + humidity 50", "HumidOn", 1),
        ("off timer 13:00", "OffTime", 13 * 60),
        ("off timer 13:30", "OffTime", 13 * 60 + 30),
        ("off timer 13:00", "OffTimer", 1),
    ],
)
def test_capture_bit_map(label, field, expected):
    assert getattr(_capture(label), field) == expected


@pytest.mark.parametrize("mode", ["area", "spot"])
def test_sensor_airflow_reproduces_the_remote(mode):
    """Area/spot ride with both swing directions on auto and set raw[36] bits 0-2."""
    capture = _capture(f"sensor_airflow {mode}")
    mine = PROTOCOL.pack(dataclasses.replace(BASE, sensor_airflow=mode))
    assert (mine.SwingV, mine.SwingH, mine.SensorAirflow) == (
        capture.SwingV,
        capture.SwingH,
        capture.SensorAirflow,
    )
    assert mine.SensorAirflow == d.SENSOR_AIRFLOW[mode]


def test_comfort_offset_round_trip():
    """Comfort auto stores a signed half-degree offset where the temperature goes."""
    frame = _capture("comfort auto offset +5.0")
    assert frame.Mode == d.MODES["auto"]
    raw_temp = frame.raw[26]
    assert raw_temp & 0xC0 == 0xC0
    offset = raw_temp & 0x1F
    assert (offset - 32 if offset >= 16 else offset) / 2 == 5.0

    mine = PROTOCOL.pack(dataclasses.replace(BASE, mode="auto", auto_offset=5.0))
    assert mine.raw[26] == raw_temp
    assert mine.raw[27] == frame.raw[27]


@pytest.mark.parametrize("offset", [-5.0, -1.0, -0.5, 0.0, 0.5, 1.0, 5.0])
def test_comfort_offset_encoding(offset):
    frame = PROTOCOL.pack(dataclasses.replace(BASE, mode="auto", auto_offset=offset))
    raw5 = frame.raw[26] & 0x1F
    assert (raw5 - 32 if raw5 >= 16 else raw5) / 2 == offset


# ── apply() semantics ────────────────────────────────────────────────────────


def test_temperature_is_clamped_per_mode():
    """cool 18.0-32.0C, heat 14.0-30.0C (manual p.13)."""
    assert PROTOCOL.apply(BASE, {"mode": "cool", "temp": 12.0}).temp == 18.0
    assert PROTOCOL.apply(BASE, {"mode": "heat", "temp": 12.0}).temp == 14.0
    assert PROTOCOL.apply(BASE, {"mode": "heat", "temp": 32.0}).temp == 30.0


def test_humidity_snaps_to_supported_steps():
    state = PROTOCOL.apply(
        BASE, {"mode": "dry", "humidity_mode": "manual", "humidity": 53}
    )
    assert state.humidity == 55
    # heat mode has no humidity setting on this model, so the feature turns itself off.
    assert PROTOCOL.apply(state, {"mode": "heat"}).humidity_mode == "off"


def test_powerful_and_quiet_are_exclusive():
    state = PROTOCOL.apply(BASE, {"quiet": True})
    assert PROTOCOL.apply(state, {"powerful": True}).quiet is False


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"power": False}, d.A_POWER),
        ({"mode": "heat"}, d.A_HEAT),
        ({"mode": "dry"}, d.A_DRY),
        ({"mode": "fan_only"}, d.A_FAN_ONLY),
        ({"mode": "heat", "heat_high": True}, d.A_HEAT_HIGH),
        ({"temp": 27.0}, d.A_TEMP),
        ({"mode": "auto", "auto_offset": 1.0}, d.A_AUTO),
        ({"fan": "level_3"}, d.A_FAN),
        ({"swing_v": "position_6"}, d.A_SWING_V),
        ({"swing_v": "circulate"}, d.A_CIRCULATION),
        ({"swing_v": "auto", "swing_h": "auto"}, d.A_SWING_V),
        ({"sensor_airflow": "area"}, d.A_SWING_SENSOR),
        ({"sensor_airflow": "spot"}, d.A_SWING_SENSOR),
        ({"swing_h": "left"}, d.A_SWING_H),
        ({"powerful": True}, d.A_POWERFUL),
        ({"streamer": True}, d.A_FAN_ONLY),
        ({"filter_clean": True}, d.A_FILTER),
        ({"eye": "1h"}, d.A_EYE),
        ({"beep": "loud"}, d.A_BEEP),
        ({"light": "off"}, d.A_LIGHT),
        ({"off_timer_enabled": True, "off_timer": 780}, d.A_OFF_TIMER),
        ({"on_timer_mode": "comfort_sleep", "on_timer": 780}, d.A_CANCEL),
        ({"sleep": True}, d.A_SLEEP),
        # Ventilation has no known announce id and no button on this model — silent.
        ({"fresh_air": "on"}, d.A_DISABLE),
        ({"fresh_air": "high"}, d.A_DISABLE),
        ({}, d.A_DISABLE),
    ],
)
def test_announce_follows_the_change(changes, expected):
    assert PROTOCOL.apply(BASE, changes).announce_item == expected


def test_swing_h_alone_does_not_borrow_the_sensor_announce():
    """Setting a vane axis to auto is a plain swing change — the sensor airflow
    feature has its own select. swing_h to auto while swing_v already sits on
    auto still announces as a horizontal-swing change (capture: "swing_h auto
    (swing_v not auto)")."""
    already_auto = dataclasses.replace(BASE, swing_v="auto")
    state = PROTOCOL.apply(already_auto, {"swing_h": "auto"})
    assert state.announce_item == d.A_SWING_H
    capture = _capture("swing_h auto (swing_v not auto)")
    assert state.announce_item == capture.AnnounceItem


def test_fan_only_and_streamer_share_one_announce_id():
    """0x1A is the fan_only/streamer button, not a phrase. Captures of entering
    fan_only, turning streamer off, and toggling streamer in cool mode all carry
    0x1A, so the protocol has no way to ask for one spoken phrase over another."""
    for label in (
        "fan_only from off",
        "streamer off (in fan_only)",
        "streamer on",
        "streamer off",
    ):
        assert _capture(label).AnnounceItem == d.A_FAN_ONLY, label

    fan_only = dataclasses.replace(BASE, mode="fan_only", streamer=True)
    assert PROTOCOL.apply(fan_only, {"streamer": False}).announce_item == d.A_FAN_ONLY
    assert PROTOCOL.apply(BASE, {"mode": "fan_only"}).announce_item == d.A_FAN_ONLY


def test_the_unit_picks_the_phrase_from_its_own_state_not_the_frame():
    """Entering fan_only and switching streamer off announce differently on the
    unit ("fan only" vs "streamer off"), yet the two captures are the same frame apart
    from the timestamp the remote stamps into every code. So the spoken phrase
    is the unit diffing against its own state — nothing this encoder emits can
    select it, and no announce-priority change can either."""
    entering = _capture("fan_only from off")
    streamer_off = _capture("streamer off (in fan_only)")
    differing = [
        i for i in range(len(entering.raw)) if entering.raw[i] != streamer_off.raw[i]
    ]
    # raw[5] is CurrentTime's low byte; raw[19] is section 1's checksum.
    assert differing == [5, 19]
    assert entering.CurrentTime != streamer_off.CurrentTime


def test_sensor_airflow_forces_both_vanes_to_auto():
    state = PROTOCOL.apply(
        dataclasses.replace(BASE, swing_v="position_3", swing_h="left"),
        {"sensor_airflow": "area"},
    )
    assert (state.swing_v, state.swing_h) == ("auto", "auto")
    assert state.announce_item == d.A_SWING_SENSOR
    assert PROTOCOL.pack(state).SensorAirflow == d.SENSOR_AIRFLOW["area"]


def test_manual_vane_pick_cancels_sensor_airflow():
    on = dataclasses.replace(
        BASE, sensor_airflow="spot", swing_v="auto", swing_h="auto"
    )
    state = PROTOCOL.apply(on, {"swing_v": "position_2"})
    assert state.sensor_airflow == "off"
    assert state.announce_item == d.A_SWING_V
    assert PROTOCOL.pack(state).SensorAirflow == 0


@pytest.mark.parametrize(
    ("value", "on_bit", "high_bit"),
    [("off", 0, 0), ("on", 1, 0), ("high", 1, 1)],
)
def test_fresh_air_select_drives_both_bits(value, on_bit, high_bit):
    """off/on/high -> raw[8] bit0 (on) + bit7 (stronger airflow). Unverified: no
    capture, the S40TTAXP-W has no button for it. high sets both, off clears both."""
    frame = PROTOCOL.pack(dataclasses.replace(BASE, fresh_air=value))
    assert (frame.FreshAir, frame.FreshAirHigh) == (on_bit, high_bit)


def test_capture_announce_items_match_their_recorded_label():
    for entry in CAPTURES:
        frame = d.Daikin312Raw(bytes(int(b, 16) for b in entry["raw"]))
        assert frame.AnnounceItem == entry["announce_item"], entry["label"]


def test_announce_switch_silences_everything():
    silent = dataclasses.replace(BASE, announce_enabled=False)
    state = PROTOCOL.apply(silent, {"temp": 27.0})
    assert state.announce_item == d.A_DISABLE
    assert PROTOCOL.pack(state).Announce == 0


def test_announce_toggle_sends_announce_item_both_directions():
    """Real captures: toggling voice response always sends AnnounceItem=A_ANNOUNCE;
    only the Announce enable bit differs between on and off."""
    off = PROTOCOL.apply(BASE, {"announce_enabled": False})
    assert off.announce_item == d.A_ANNOUNCE
    assert PROTOCOL.pack(off).Announce == 0

    muted = dataclasses.replace(BASE, announce_enabled=False)
    on = PROTOCOL.apply(muted, {"announce_enabled": True})
    assert on.announce_item == d.A_ANNOUNCE
    assert PROTOCOL.pack(on).Announce == 1


def test_power_is_mirrored_in_both_bits():
    on = PROTOCOL.pack(dataclasses.replace(BASE, power=True))
    off = PROTOCOL.pack(dataclasses.replace(BASE, power=False))
    assert (on.Power, on.Power2) == (1, 0)
    assert (off.Power, off.Power2) == (0, 1)


def test_state_survives_a_dict_round_trip():
    state = PROTOCOL.apply(BASE, {"mode": "heat", "temp": 23.5, "fan": "level_2"})
    assert PROTOCOL.from_dict(PROTOCOL.to_dict(state)) == state
