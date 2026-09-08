"""Daikin 312-bit (39 byte) protocol: ARC472A43 remotes, e.g. S40TTAXP-W.

The byte/bit layout mirrors `union Daikin312Protocol` in IRremoteESP8266's
`ir_Daikin.h`, which stays the readable spec for this file.

Where captures from a real ARC472A43 remote disagree with that header, the
capture wins and the field carries a note. Confirmed by capture:

* raw[14] bit4: streamer air purifying (the header calls this `Clean`/AirCleanMode).
* raw[14] bit7: cleaning filter, absent from the header; announces as Filter.
* raw[36] bits 0-2: sensor airflow mode — 0 off / 0b011 area / 0b100 spot
  The header calls bit2 `Econo`; captures of the "sensor auto" button
  (bits 0-1 set) vs "spot" (bit2 set) show this is a 3-state select,
  not one flag. Both area/spot also force SwingV=auto + SwingH=auto.
  The header's `Econo`/`Eye`/`EyeAuto` bits (36:2/1/3) sit right where this
  select lives, which reads like the header is wrong about bit2 for this
  remote, not that a real Econo flag hides nearby. Since ECONO and QUIET are
  International-only feature, help is needed to expose these features.
* raw[36] bit7: set in every capture ever taken, in every mode, never cleared.
  Reproduced by `_RESET`, along with every other constant the remote holds fixed.
  On its own it is not what the unit wants: frames sent by hand with bit7 set and
  the other constants left as `stateReset()` has them were still ignored (below).
* raw[7] bits6-7: auto-off ("AUTO OFF") duration: 0=off, 1=1hr, 2=3hr. No
  separate enable bit was ever observed, so this select *is* the feature's
  on/off. It is a different feature from ECONO.
* raw[8] bit4: high-temperature airflow (heat high), matches the header's HeatHigh.
* raw[33] bit2: comfort sleep (sleep mode), absent from the header. Distinct from
  raw[36] bit5, the header's unverified international Comfort Sleep Timer,
  which this JP unit's remote has no button for.
* raw[26] in comfort-auto mode: 0xC0 | 5-bit two's-complement half-degree offset,
  and raw[27] = 0x80. Not in the header at all.

raw[9] (AnnounceItem) names the button pressed. 0x1A covers the whole fan-only /
streamer button: entering fan-only mode, and switching streamer either way, in
fan-only and in cool alike. The unit picks its wording by diffing the frame
against the state it is already in — captures of "entering fan only" and
"streamer off" are the same 39 bytes apart from the timestamp in raw[5], yet are
announced as "fan only" and "streamer off" respectively. So which of these a
change is announced as cannot be chosen from here, and the streamer bit we send
along with a mode change is what decides it: arriving in fan-only mode with
raw[14] bit4 set is heard as the streamer phrase. The remote's own fan-only
press from off sends that bit clear.

`stateReset()`'s constants are not this remote's, and the unit does not ignore
that. It holds bytes 10, 11, 15, 17, 35 and 37, plus raw[14] bit1, raw[34] bit1
and raw[36] bit7, at values `stateReset()` disagrees with in all 30 captures, and
never sets raw[6] bit5, which `stateReset()` does. A frame that gets those wrong
is still accepted for temperature, mode, fan and the rest, but raw[36] is dropped
whole: sending our own area and spot frames made the unit re-announce the sensor
mode it was already in ("cancelled" after a cancel, "area" after an area press),
while replaying a capture byte for byte announced area and spot correctly, and
those two captures differ in nothing but raw[36] bits 0-2. Which of the wrong
bytes was the gate was not bisected further; `_RESET` now matches the remote on
all of them, since a value the remote never sends is not one to defend.

Still unidentified, and left as they are: raw[6] bit6 and raw[14] bit6, which the
remote does vary but in patterns the captures do not explain, and raw[34] bit5,
which is set in exactly the two off-timer captures and may be a second off-timer
enable we do not send.

Ranges and option lists come from the S40TTAXP-W manual (3P420060-1C) where it
is narrower than the header, since the header covers every Daikin312 model.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from .bitfield import Field, RawState
from .protocol import (
    MODE_AUTO,
    MODE_COOL,
    MODE_DRY,
    MODE_FAN_ONLY,
    MODE_HEAT,
    MODE_HEAT_COOL,
    NUMBER,
    SELECT,
    SWITCH,
    TIME,
    Capabilities,
    Control,
    Protocol,
    register,
)

# ── Signal timing (µs) ───────────────────────────────────────────────────────

FREQ = 36700
LEADER_MARK = 10024
LEADER_SPACE = 25180
HDR_MARK = 3518
HDR_SPACE = 1688
BIT_MARK = 453
ONE_SPACE = 1275
ZERO_SPACE = 414
SECTION_GAP = 35512
SECTION1_LENGTH = 20
STATE_LENGTH = 39

# ── Value tables ─────────────────────────────────────────────────────────────

MODES: dict[str, int] = {
    MODE_AUTO: 0b000,
    MODE_DRY: 0b010,
    MODE_COOL: 0b011,
    MODE_HEAT: 0b100,
    MODE_FAN_ONLY: 0b110,
}
FANS: dict[str, int] = {
    "auto": 0xA,
    "quiet": 0xB,
    "level_1": 3,
    "level_2": 4,
    "level_3": 5,
    "level_4": 6,
    "level_5": 7,
}
# Vertical airflow direction (flaps): levels 1-6 plus auto / swing / breeze /
# circulation.
SWING_V: dict[str, int] = {
    "off": 0x0,
    "auto": 0xE,
    "swing": 0xF,
    "position_1": 0x1,
    "position_2": 0x2,
    "position_3": 0x3,
    "position_4": 0x4,
    "position_5": 0x5,
    "position_6": 0x6,
    "breeze": 0xC,
    "circulate": 0xD,
}
# Horizontal airflow direction (louvres): which of the eight fixed positions the
# remote offers depends on its room-shape setting, so all of them are exposed.
SWING_H: dict[str, int] = {
    "off": 0x00,
    "auto": 0x1E,
    "swing": 0x1F,
    "wide": 0x01,
    "left_max": 0x08,
    "left": 0x09,
    "middle_left": 0x0A,
    "middle": 0x0B,
    "middle_right": 0x0C,
    "right": 0x0D,
    "right_max": 0x0E,
}
# Sensor airflow: off / area / spot, in raw[36] bits 0-2. Area is bits 0+1, spot
# is bit 2 (the header's `Econo`). Both drive the flaps and louvres to auto.
SENSOR_AIRFLOW: dict[str, int] = {"off": 0x0, "area": 0x3, "spot": 0x4}
BEEPS: dict[str, int] = {"normal": 0, "quiet": 1, "loud": 2, "off": 3}
LIGHTS: dict[str, int] = {"bright": 1, "dim": 2, "off": 3}
EYE: dict[str, int] = {"off": 0, "1h": 1, "3h": 2}
# Fresh-air ventilation: off / on / high. On the S40WTRXP-W only; the S40TTAXP-W
# has no button for it, so the bits are unverified: header FreshAir is raw[8]
# bit0 (feature on), FreshAirHigh raw[8] bit7 (stronger airflow). high sets both.
FRESH_AIR = ("off", "on", "high")

# Humidity percentages the unit accepts, per mode (manual p.13). Lowering the
# humidity in cool is what puts the unit into dehumidifying cool. The header also
# lists 40/45/50 for heat, which belongs to the humidifying models — this one
# says humidity is not adjustable in heat, so it is not offered.
HUMIDITY_PERCENTS = (50, 55, 60)
HUMIDITY_STEPS: dict[str, tuple[int, ...]] = {
    MODE_COOL: HUMIDITY_PERCENTS,
    MODE_DRY: HUMIDITY_PERCENTS,
}
HUMIDITY_AUTO = 0xFF  # continuous: keep dehumidifying
# The set points are options in their own right rather than a separate "manual"
# option plus a slider: the unit only speaks the mode aloud when the humidity
# setting changes in the same frame, so the select has to carry the value.
HUMIDITY_MODES = ("off", "continuous", *(str(p) for p in HUMIDITY_PERCENTS))
HUMIDITY_OFF = 0x00
# In comfort-auto mode the remote parks a non-percentage value here.
HUMIDITY_COMFORT = 0x80

# Settable temperature per mode (manual p.13). Dry and streamer air purifying
# have no setting of their own; the byte still has to carry something sane.
TEMP_RANGES: dict[str, tuple[float, float]] = {
    MODE_COOL: (18.0, 32.0),
    MODE_HEAT: (14.0, 30.0),
}
DEFAULT_TEMP_RANGE = (18.0, 32.0)
MAX_TEMP = 32.0
TEMP_STEP = 0.5
# raw[26] bit 6, always sent with HumidOn (bit 7) — together they mark the byte
# as "no absolute set point". The low bits then mean nothing (dry) or carry the
# comfort-auto offset, so a frame with this marker never states a temperature.
TEMP_NONE = 0x40
# Largest comfort-auto offset seen from the remote (0xD6 == -5.0 °C).
MAX_AUTO_OFFSET = 5.0

UNUSED_TIME = 0x600  # what the remote parks in On/OffTime when disabled

# ── Announce items (raw[9]) ──────────────────────────────────────────────────

A_DISABLE = 0x00
A_POWER = 0x02
A_TEMP = 0x03
A_OFF_TIMER = 0x04
A_SWING_V = 0x06
A_FAN = 0x07
A_CANCEL = 0x0C
A_AUTO = 0x0D
A_COOL = 0x0E
A_DRY = 0x0F
A_HEAT = 0x10
A_HEAT_HIGH = 0x12
A_HUMIDITY = 0x13
A_CIRCULATION = 0x14
A_SWING_SENSOR = 0x15
A_SWING_H = 0x16
A_FILTER = 0x17
A_POWERFUL = 0x19
A_FAN_ONLY = 0x1A
A_EYE = 0x24
A_SLEEP = 0x2F
A_LIGHT = 0x30
A_BEEP = 0x31
A_ANNOUNCE = 0x32

_MODE_ANNOUNCE = {
    MODE_AUTO: A_AUTO,
    MODE_COOL: A_COOL,
    MODE_DRY: A_DRY,
    MODE_HEAT: A_HEAT,
    MODE_FAN_ONLY: A_FAN_ONLY,
}

# Checked in order, so the first field that changed wins the announcement.
_ANNOUNCE_PRIORITY: tuple[tuple[str, int], ...] = (
    ("power", A_POWER),
    ("mode", -1),  # resolved via _MODE_ANNOUNCE / heat_high
    ("heat_high", A_HEAT_HIGH),
    ("temp", A_TEMP),
    ("auto_offset", A_TEMP),
    ("humidity", A_HUMIDITY),
    ("humidity_mode", A_HUMIDITY),
    ("fan", A_FAN),
    ("sensor_airflow", A_SWING_SENSOR),  # sensor airflow; ahead of the flap/louvre axes
    ("swing_v", -2),  # circulate/breeze announce differently
    ("swing_h", -2),
    ("powerful", A_POWERFUL),
    ("streamer", A_FAN_ONLY),
    ("filter_clean", A_FILTER),
    ("eye", A_EYE),
    ("sleep", A_SLEEP),
    ("on_timer_mode", -3),
    ("on_timer", -3),
    ("off_timer_enabled", -4),
    ("off_timer", -4),
    ("light", A_LIGHT),
    ("beep", A_BEEP),
    # announce_enabled is handled ahead of this table, in _announce_for.
)

# ── Raw frame ────────────────────────────────────────────────────────────────

# Byte template: IRDaikin312::stateReset() with every byte that a real ARC472A43
# holds constant corrected to what the remote actually sends. stateReset() covers
# the whole Daikin312 family, and its constants are not this remote's; the unit
# quietly drops raw[36] when they are wrong (see the module docstring).
_RESET = bytes(
    [
        0x11, 0xDA, 0x27, 0x00, 0x02,  # 0-4   fixed preamble
        0x58, 0x44,                    # 5-6   CurrentTime + Power2; 6:5 cleared
        0x00,                          # 7     auto-off timer
        0x20,                          # 8     bit5 always set by the remote
        0x00,                          # 9     announce item
        0x82, 0x30,                    # 10-11 constant in every capture
        0x01,                          # 12    light/beep/swingv
        0x00,                          # 13    swingh
        0x02,                          # 14    bit1; streamer/filter ride on top
        0x04, 0x00, 0x24,              # 15-17 15 and 17 constant, 16 unused
        0x00,                          # 18
        0x00,                          # 19    checksum #1
        0x11, 0xDA, 0x27, 0x00, 0x00,  # 20-24 fixed preamble
        0x08,                          # 25    power/timers/mode
        0x2C,                          # 26    temp
        0x00,                          # 27    humidity
        0x00, 0x00,                    # 28-29 fan
        0x00, 0x06, 0x60,              # 30-32 on/off timer times (disabled)
        0x00,                          # 33    powerful/quiet
        0x02, 0xC4,                    # 34-35 34:1 + 35 constant, 34:3 announce
        0x80,                          # 36    bit7; sensor airflow / purify below
        0x24,                          # 37    constant in every capture
        0x00,                          # 38    checksum #2
    ]
)


class Daikin312Raw(RawState):
    """Bit-accurate view of the 39 byte frame (mirrors union Daikin312Protocol)."""

    LENGTH = STATE_LENGTH

    CurrentTime   = Field(5, 0, 12)   # clock, minutes past midnight
    Power2        = Field(6, 7)       # inverse of Power
    EyeTimer      = Field(7, 6, 2)    # auto off: 0 off / 1 1hr / 2 3hr
    FreshAir      = Field(8, 0)       # fresh-air ventilation on; unverified
    Mold          = Field(8, 3)       # mold proof
    HeatHigh      = Field(8, 4)       # high-temperature airflow
    FreshAirHigh  = Field(8, 7)       # fresh-air ventilation, stronger; unverified
    AnnounceItem  = Field(9, 0, 8)    # A_* announce id
    Light         = Field(12, 0, 2)   # LIGHTS index
    Beep          = Field(12, 2, 2)   # BEEPS index
    SwingV        = Field(12, 4, 4)   # SWING_V index
    SwingH        = Field(13, 0, 8)   # SWING_H index
    Streamer      = Field(14, 4)      # streamer air purifying (header: Clean)
    FilterClean   = Field(14, 7)      # cleaning filter (absent from header)
    Sum1          = Field(19, 0, 8)   # section 1 checksum
    Power         = Field(25, 0)      # main power
    OnTimer       = Field(25, 1)      # on-timer enabled
    OffTimer      = Field(25, 2)      # off-timer enabled
    Mode          = Field(25, 4, 3)   # MODES index
    Temp          = Field(26, 0, 7)   # target temp, or comfort-auto offset
    HumidOn       = Field(26, 7)      # humidity mode enabled
    Humidity      = Field(27, 0, 8)   # target humidity %, see HUMIDITY_*
    Fan           = Field(28, 4, 4)   # FANS index
    OnTime        = Field(30, 0, 12)  # on-timer time, minutes past midnight
    OffTime       = Field(31, 4, 12)  # off-timer time, minutes past midnight
    Powerful      = Field(33, 0)      # powerful
    Sleep         = Field(33, 2)      # comfort sleep; capture-confirmed, not in header
    Quiet         = Field(33, 5)      # unverified; makes outdoor unit quiet; intl-only
    Announce      = Field(34, 3)      # enable bit, gates AnnounceItem
    SensorAirflow = Field(36, 0, 3)  # sensor airflow: off/area/spot; hdr bit2=Econo
    Purify        = Field(36, 4)      # unverified
    ComfortSleep  = Field(36, 5)      # on_timer_mode == comfort_sleep; unverified intl
                                      # feature, never observed on this JP-market unit
    Sum2          = Field(38, 0, 8)   # section 2 checksum

    def __init__(self, raw: bytes | bytearray | None = None) -> None:
        super().__init__(raw if raw is not None else _RESET)

    def checksum(self) -> None:
        """Set both section checksums (plain byte sums)."""
        self.raw[SECTION1_LENGTH - 1] = sum(self.raw[: SECTION1_LENGTH - 1]) & 0xFF
        self.raw[-1] = sum(self.raw[SECTION1_LENGTH:-1]) & 0xFF

    def valid_checksum(self) -> bool:
        return (
            self.raw[SECTION1_LENGTH - 1] == sum(self.raw[: SECTION1_LENGTH - 1]) & 0xFF
            and self.raw[-1] == sum(self.raw[SECTION1_LENGTH:-1]) & 0xFF
        )

    def timings(self) -> list[int]:
        """Render the frame as raw µs durations: leader, then two LSB-first sections."""
        out = [LEADER_MARK, LEADER_SPACE]
        for section in (self.raw[:SECTION1_LENGTH], self.raw[SECTION1_LENGTH:]):
            out += [HDR_MARK, HDR_SPACE]
            for byte in section:
                for bit in range(8):
                    out += [BIT_MARK, ONE_SPACE if byte >> bit & 1 else ZERO_SPACE]
            out += [BIT_MARK, SECTION_GAP]
        return out


# ── User-facing state ────────────────────────────────────────────────────────


@dataclasses.dataclass(frozen=True, slots=True)
class Daikin312State:
    """Everything the integration can set, in human units."""

    power: bool = False
    mode: str = MODE_COOL
    temp: float = 26.0
    auto_offset: float = 0.0  # comfort-auto mode only
    fan: str = "auto"
    swing_v: str = "auto"
    swing_h: str = "auto"
    sensor_airflow: str = "off"  # sensor airflow: off | area | spot
    humidity_mode: str = "off"  # off | continuous | specified %
    humidity: int = 50
    heat_high: bool = False  # high-temperature airflow
    powerful: bool = False  # powerful
    quiet: bool = False  # outdoor unit quiet; unverified, see README
    streamer: bool = False  # streamer air purifying
    filter_clean: bool = False  # cleaning filter
    eye: str = "off"  # auto off: off | 1h | 3h
    mold: bool = False  # mold proof; unverified
    purify: bool = False  # unverified; not in menu, see Control list comment
    fresh_air: str = "off"  # ventilation: off | on | high; unverified, S40WTRXP-W only
    beep: str = "quiet"
    light: str = "bright"
    announce_enabled: bool = True
    sleep: bool = False  # comfort sleep; confirmed by capture
    on_timer_mode: str = "none"  # none | on_timer | comfort_sleep (they share one slot)
    on_timer: int = 0  # minutes past midnight
    off_timer_enabled: bool = False
    off_timer: int = 0  # minutes past midnight
    clock: int = 720  # minutes past midnight; stamped at send time
    announce_item: int = A_DISABLE  # resolved by apply(); not user-set


# ── Protocol ─────────────────────────────────────────────────────────────────


class Daikin312Protocol(Protocol):
    name = "daikin312"
    label = "Daikin 312-bit"
    freq = FREQ

    # Comfort Auto is the unit's only automatic mode; HA offers two names for it.
    mode_aliases = {MODE_HEAT_COOL: MODE_AUTO}

    capabilities = Capabilities(
        hvac_modes=(MODE_AUTO, MODE_COOL, MODE_HEAT, MODE_DRY, MODE_FAN_ONLY),
        fan_modes=tuple(FANS),
        swing_modes=tuple(SWING_V),
        swing_horizontal_modes=tuple(SWING_H),
        humidity_modes=HUMIDITY_MODES,
        temp_step=TEMP_STEP,
    )

    controls = (
        Control(
            "auto_offset",
            NUMBER,
            min=-MAX_AUTO_OFFSET,
            max=MAX_AUTO_OFFSET,
            step=TEMP_STEP,
            unit="°C",
            modes=(MODE_AUTO,),
            category=None,
            icon="mdi:thermometer-plus",
        ),
        Control(
            "humidity_mode",
            SELECT,
            options=HUMIDITY_MODES,
            modes=tuple(HUMIDITY_STEPS),
            category=None,
            icon="mdi:water-percent",
        ),
        Control(
            "powerful",
            SWITCH,
            icon="mdi:rocket-launch",
        ),
        Control(
            "heat_high",
            SWITCH,
            modes=(MODE_HEAT,),
            category=None,
            icon="mdi:fire",
        ),
        Control(
            "sensor_airflow",
            SELECT,
            options=tuple(SENSOR_AIRFLOW),
            icon="mdi:motion-sensor",
        ),
        Control(
            "streamer",
            SWITCH,
            category=None,
            icon="mdi:air-filter",
        ),
        Control(
            "eye",
            SELECT,
            options=tuple(EYE),
            icon="mdi:home-account",
        ),
        Control(
            "filter_clean",
            SWITCH,
            icon="mdi:broom",
        ),
        Control(
            "mold",
            SWITCH,
            icon="mdi:snowflake-melt",
        ),
        Control(
            "quiet",
            SWITCH,
            icon="mdi:volume-low",
        ),
        # purify (raw[36] bit4) dropped from the menu: no button or menu item
        # named "air purifying" in the S40WTRXP-W, S40TTAXP-W, or FTXZ-N manuals
        # beyond streamer air purifying (already `streamer`, raw[14] bit4). No known
        # trigger to capture. State field kept below so we can still decode/send
        # it if a future capture ever turns up a real source for the bit.
        Control(
            "fresh_air",
            SELECT,
            options=FRESH_AIR,
            icon="mdi:weather-windy",
        ),
        Control(
            "beep",
            SELECT,
            options=tuple(BEEPS),
            icon="mdi:volume-high",
        ),
        Control(
            "light",
            SELECT,
            options=tuple(LIGHTS),
            icon="mdi:lightbulb",
        ),
        Control(
            "announce_enabled",
            SWITCH,
            icon="mdi:bullhorn",
        ),
        Control(
            "sleep",
            SWITCH,
            icon="mdi:sleep",
        ),
        Control(
            "on_timer_mode",
            SELECT,
            options=("none", "on_timer", "comfort_sleep"),
            icon="mdi:timer-outline",
        ),
        Control(
            "on_timer",
            TIME,
            icon="mdi:timer-play-outline",
        ),
        Control(
            "off_timer_enabled",
            SWITCH,
            category=None,
            icon="mdi:timer-off-outline",
        ),
        Control(
            "off_timer",
            TIME,
            category=None,
            icon="mdi:timer-stop-outline",
        ),
    )

    def new_state(self) -> Daikin312State:
        return Daikin312State()

    def from_dict(self, data: dict[str, Any]) -> Daikin312State:
        state = super().from_dict(data)
        if state.humidity_mode in HUMIDITY_MODES:
            return state
        # An install from before the set points became options of their own
        # stored humidity_mode="manual" alongside the percentage; fold the two
        # back into the one field that now carries both.
        percent = min(HUMIDITY_PERCENTS, key=lambda p: abs(p - state.humidity))
        return dataclasses.replace(state, humidity_mode=str(percent), humidity=percent)

    # ── validation ───────────────────────────────────────────────────────────

    def temp_range(self, state: Daikin312State) -> tuple[float, float]:
        return TEMP_RANGES.get(state.mode, DEFAULT_TEMP_RANGE)

    def humidity_range(self, state: Daikin312State) -> tuple[int, int]:
        if steps := HUMIDITY_STEPS.get(state.mode):
            return steps[0], steps[-1]
        # Humidification is heat/dry only, but the slider still needs bounds.
        every = sorted({v for s in HUMIDITY_STEPS.values() for v in s})
        return every[0], every[-1]

    def settable(self, state: Daikin312State) -> frozenset[str]:
        # Auto drives the temperature itself (auto_offset is the only handle),
        # and dry and fan-only have no temperature setting at all.
        fields = set()
        if state.mode in TEMP_RANGES:
            fields.add("temp")
        if state.mode in HUMIDITY_STEPS:
            fields.add("humidity")
        return frozenset(fields)

    def options_for(self, control: Control, state: Daikin312State) -> tuple[str, ...]:
        if control.key == "humidity_mode" and state.mode == MODE_DRY:
            return tuple(o for o in control.options if o != "off")
        return control.options

    def apply(self, state: Daikin312State, changes: dict[str, Any]) -> Daikin312State:
        """Merge changes, clamp them to what the unit accepts, pick the announcement."""
        new = dataclasses.replace(state, **changes)
        changed = {k for k, v in changes.items() if getattr(state, k, None) != v}
        if "mode" in changes and changes.get("power"):
            # The state keeps its mode while the unit is off, so switching on
            # into the mode it was last left in diffs to a power change alone
            # and the mode never reaches the announcement rules below. Count
            # it as changed: the mode was asked for, whatever it was before.
            changed = changed | {"mode"}

        low, high = self.temp_range(new)
        temp = min(high, max(low, round(new.temp / TEMP_STEP) * TEMP_STEP))
        offset = min(
            MAX_AUTO_OFFSET,
            max(-MAX_AUTO_OFFSET, round(new.auto_offset / TEMP_STEP) * TEMP_STEP),
        )

        steps = HUMIDITY_STEPS.get(new.mode)
        humidity_mode, humidity = new.humidity_mode, new.humidity
        if steps and "humidity" in changed:
            # The climate slider picks a set point; keep the select showing it.
            humidity = min(steps, key=lambda s: abs(s - humidity))
            humidity_mode = str(humidity)
        elif humidity_mode.isdigit():
            humidity = int(humidity_mode)

        picked = {"humidity", "humidity_mode"} & changed
        if not steps:
            humidity_mode = "off"
        elif "mode" in changed and not picked:
            # Arriving in a mode resets humidity control. Cool starts with it
            # off, because a set point there puts the unit into cooling with
            # dehumidification; dry starts continuous, since it has no off.
            humidity_mode = "off" if new.mode == MODE_COOL else "continuous"
        elif new.mode == MODE_DRY and humidity_mode == "off":
            # Turning it off in dry makes the unit fall back to cool, which
            # would leave the assumed state lying about the mode.
            humidity_mode = "continuous"

        # Powerful and quiet are mutually exclusive on the unit.
        powerful, quiet = new.powerful, new.quiet
        if powerful and quiet:
            quiet = "quiet" not in changed

        # Sensor airflow (area/spot) drives the flaps and louvres to auto;
        # conversely, picking a flap or louvre position directly cancels it — the
        # way the remote's buttons interact. The flap/louvre→off half is inferred
        # from that behaviour, not from a capture of a flap or louvre button
        # pressed while area/spot is on.
        sensor_airflow, swing_v, swing_h = (
            new.sensor_airflow, new.swing_v, new.swing_h
        )
        if "sensor_airflow" in changed and sensor_airflow != "off":
            swing_v = swing_h = "auto"
        elif ("swing_v" in changed or "swing_h" in changed) and sensor_airflow != "off":
            sensor_airflow = "off"

        new = dataclasses.replace(
            new,
            temp=temp,
            auto_offset=offset,
            humidity_mode=humidity_mode,
            humidity=humidity,
            powerful=powerful,
            quiet=quiet and not powerful,
            sensor_airflow=sensor_airflow,
            swing_v=swing_v,
            swing_h=swing_h,
        )
        item = self._announce_for(new, changed)
        new = dataclasses.replace(
            new, announce_item=A_DISABLE if item is None else item
        )
        return new

    def _announce_for(self, state: Daikin312State, changed: set[str]) -> int | None:
        """Pick what the unit should read aloud, or None to send nothing.

        The mute toggle itself is exempt from the mute guard below: a real
        remote always sends AnnounceItem=A_ANNOUNCE for both directions of
        that button — only the Announce enable bit (derived from
        announce_enabled in pack()) flips. Muting it like any other change
        would send AnnounceItem=A_DISABLE when turning voice off, which real
        captures never show and the unit may not register as a press at all.
        """
        if "announce_enabled" in changed:
            return A_ANNOUNCE
        if not state.announce_enabled:
            return None
        if {"power", "mode"} <= changed and state.power:
            # Switching on straight into a mode is one button on the remote and
            # is announced as the mode, not as power (capture: "dry from off").
            # Switching off still announces as power, whatever else rides along.
            changed = changed - {"power"}
        for key, item in _ANNOUNCE_PRIORITY:
            if key not in changed:
                continue
            if item >= 0:
                return item
            if item == -1:  # mode
                if state.mode == MODE_HEAT and state.heat_high:
                    return A_HEAT_HIGH
                return _MODE_ANNOUNCE.get(state.mode)
            if item == -2:  # swing
                # Setting a flap or louvre axis to auto by itself is a plain swing
                # change, never the sensor-airflow feature — that has its own
                # select above, and apply() turns it off when a flap or louvre
                # axis is picked directly.
                value = state.swing_v if key == "swing_v" else state.swing_h
                if value in ("breeze", "circulate"):
                    return A_CIRCULATION
                return A_SWING_V if key == "swing_v" else A_SWING_H
            if item == -3:  # on timer slot: on_timer and comfort_sleep both unverified
                return None if state.on_timer_mode == "none" else A_CANCEL
            if item == -4:  # off timer
                return A_OFF_TIMER if state.off_timer_enabled else A_CANCEL
        return None

    # ── rendering ────────────────────────────────────────────────────────────

    def pack(self, state: Daikin312State) -> Daikin312Raw:
        """Render the state into the 39 byte frame, checksums included."""
        f = Daikin312Raw()

        f.CurrentTime = state.clock
        f.Power = state.power
        f.Power2 = not state.power
        f.Mode = MODES[state.mode]
        f.Fan = FANS[state.fan]
        f.SwingV = SWING_V[state.swing_v]
        f.SwingH = SWING_H[state.swing_h]
        f.SensorAirflow = SENSOR_AIRFLOW[state.sensor_airflow]
        if state.sensor_airflow != "off":
            # Area/spot always ride with the flaps and louvres on auto (captures).
            f.SwingV = SWING_V["auto"]
            f.SwingH = SWING_H["auto"]

        if state.mode == MODE_AUTO:
            # Comfort Auto: the temperature byte carries a signed half-degree offset.
            f.Temp = TEMP_NONE | (int(state.auto_offset * 2) & 0x1F)
            f.HumidOn = 1
            f.Humidity = HUMIDITY_COMFORT
        else:
            humidity = HUMIDITY_OFF
            if state.mode in HUMIDITY_STEPS:
                if state.humidity_mode == "continuous":
                    humidity = HUMIDITY_AUTO
                elif state.humidity_mode.isdigit():
                    humidity = int(state.humidity_mode)
            f.Humidity = humidity
            if humidity != HUMIDITY_OFF and state.mode == MODE_DRY:
                # Dry has no temperature of its own, so the remote sends the
                # "no set point" marker instead of a value (captures "dry from
                # off", "dry + humidity 50").
                f.HumidOn, f.Temp = 1, TEMP_NONE
            else:
                low, high = self.temp_range(state)
                f.Temp = int(min(high, max(low, state.temp)) * 2)
                if humidity != HUMIDITY_OFF:
                    # Dehumidified cooling is not a mode of its own: picking a
                    # humidity in cool makes the remote send *dry* carrying a
                    # real temperature, and that temperature is the only thing
                    # telling the unit this is not plain dry (capture "cool ->
                    # set humidity to 60%").
                    f.Mode = MODES[MODE_DRY]

        f.HeatHigh = state.heat_high and state.mode == MODE_HEAT
        f.Powerful = state.powerful
        f.Quiet = state.quiet
        f.Streamer = state.streamer
        f.FilterClean = state.filter_clean
        f.EyeTimer = EYE[state.eye]
        f.Mold = state.mold
        f.Purify = state.purify
        f.FreshAir = state.fresh_air != "off"
        f.FreshAirHigh = state.fresh_air == "high"
        f.Beep = BEEPS[state.beep]
        f.Light = LIGHTS[state.light]

        f.OnTime = state.on_timer if state.on_timer_mode != "none" else UNUSED_TIME
        f.OnTimer = state.on_timer_mode == "on_timer"
        f.ComfortSleep = state.on_timer_mode == "comfort_sleep"
        f.Sleep = state.sleep
        f.OffTime = state.off_timer if state.off_timer_enabled else UNUSED_TIME
        f.OffTimer = state.off_timer_enabled

        f.AnnounceItem = state.announce_item
        f.Announce = state.announce_item != A_DISABLE and state.announce_enabled

        f.checksum()
        return f

    def timings(self, state: Daikin312State) -> list[int]:
        return self.pack(state).timings()


PROTOCOL = register(Daikin312Protocol())
