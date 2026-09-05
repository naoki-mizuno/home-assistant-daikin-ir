"""Daikin 312-bit (39 byte) protocol: ARC472A43 remotes, e.g. S40TTAXP-W.

The byte/bit layout mirrors `union Daikin312Protocol` in IRremoteESP8266's
`ir_Daikin.h`, which stays the readable spec for this file.

Where captures from a real ARC472A43 remote disagree with that header, the
capture wins and the field carries a note. Confirmed by capture:

* raw[14] bit4: ストリーマ空清 (the header calls this `Clean`/AirCleanMode).
* raw[14] bit7: フィルター掃除, absent from the header; announces as Filter.
* raw[36] bit2: センサー風向 flag, set with SwingH/SwingV sensor-auto
  (the header calls this `Econo`).
* raw[7] bits6-7: 留守エコ duration: 0=off, 1=1hr, 2=3hr. No separate enable
  bit was ever observed, so this select *is* the feature's on/off.
* raw[8] bit4: 高温風 (heat high), matching the header's HeatHigh comment.
* raw[26] in 快適自動: 0xC0 | 5-bit two's-complement half-degree offset, and
  raw[27] = 0x80. Not in the header at all.

Still unidentified: raw[14] bits 1 and 6, which the remote sets in patterns the
captures do not explain. Codes generated without them work, so they are left
clear.

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
# 風向上下: 1～6段階目 plus 自動 / スイング / ゆらぎ / サーキュレーション風向.
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
# 風向左右: which of the eight fixed positions the remote offers depends on its
# 部屋形状設定, so all of them are exposed.
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
BEEPS: dict[str, int] = {"normal": 0, "quiet": 1, "loud": 2, "off": 3}
LIGHTS: dict[str, int] = {"bright": 1, "dim": 2, "off": 3}
EYE: dict[str, int] = {"off": 0, "1h": 1, "3h": 2}

# Humidity percentages the unit accepts, per mode (manual p.13). Lowering the
# humidity in 冷房 is what puts the unit into 除湿冷房. The header also lists
# 40/45/50 for 暖房, which belongs to the humidifying (うるる) models — this one
# says 「湿度は変えられません」 in heat, so it is not offered.
HUMIDITY_STEPS: dict[str, tuple[int, ...]] = {
    MODE_COOL: (50, 55, 60),
    MODE_DRY: (50, 55, 60),
}
HUMIDITY_AUTO = 0xFF  # 連続: keep dehumidifying
HUMIDITY_MODES = ("off", "continuous", "manual")
HUMIDITY_OFF = 0x00
# In 快適自動 the remote parks a non-percentage value here.
HUMIDITY_COMFORT = 0x80

# Settable temperature per mode (manual p.13). 除湿 and ストリーマ空気清浄 have no
# setting of their own; the byte still has to carry something sane.
TEMP_RANGES: dict[str, tuple[float, float]] = {
    MODE_COOL: (18.0, 32.0),
    MODE_HEAT: (14.0, 30.0),
}
DEFAULT_TEMP_RANGE = (18.0, 32.0)
MAX_TEMP = 32.0
TEMP_STEP = 0.5
# Largest 快適自動 offset seen from the remote (0xD6 == -5.0 °C).
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
    ("swing_v", -2),  # circulate/breeze and sensor-auto announce differently
    ("swing_h", -2),
    ("powerful", A_POWERFUL),
    ("streamer", A_FAN_ONLY),
    ("filter_clean", A_FILTER),
    ("eye", A_EYE),
    ("on_timer_mode", -3),
    ("on_timer", -3),
    ("off_timer_enabled", -4),
    ("off_timer", -4),
    ("light", A_LIGHT),
    ("beep", A_BEEP),
    # announce_enabled is handled ahead of this table, in _announce_for.
)

# ── Raw frame ────────────────────────────────────────────────────────────────

# Byte template from IRDaikin312::stateReset(); every code generated from it has
# been confirmed working on an S40TTAXP-W.
_RESET = bytes(
    [
        0x11, 0xDA, 0x27, 0x00, 0x02,  # 0-4   fixed preamble
        0x58, 0x64,                    # 5-6   CurrentTime + Power2
        0x00,                          # 7     留守エコ timer
        0x20,                          # 8     bit5 always set by the remote
        0x00,                          # 9     announce item
        0x00, 0x00,                    # 10-11
        0x01,                          # 12    light/beep/swingv
        0x00,                          # 13    swingh
        0x00, 0x00, 0x00, 0x00, 0x00,  # 14-18
        0x00,                          # 19    checksum #1
        0x11, 0xDA, 0x27, 0x00, 0x00,  # 20-24 fixed preamble
        0x08,                          # 25    power/timers/mode
        0x2C,                          # 26    temp
        0x00,                          # 27    humidity
        0x00, 0x00,                    # 28-29 fan
        0x00, 0x06, 0x60,              # 30-32 on/off timer times (disabled)
        0x00,                          # 33    powerful/quiet
        0x00, 0xC5,                    # 34-35 announce enable
        0x00,                          # 36    sensor swing/eye/purify/sleep
        0x08,                          # 37
        0x00,                          # 38    checksum #2
    ]
)


class Daikin312Raw(RawState):
    """Bit-accurate view of the 39 byte frame (mirrors union Daikin312Protocol)."""

    LENGTH = STATE_LENGTH

    CurrentTime  = Field(5, 0, 12)   # clock, minutes past midnight
    Power2       = Field(6, 7)       # inverse of Power
    EyeTimer     = Field(7, 6, 2)    # 留守エコ: 0 off / 1 1hr / 2 3hr
    FreshAir     = Field(8, 0)       # unverified
    Mold         = Field(8, 3)       # 内部クリーン
    HeatHigh     = Field(8, 4)       # 高温風
    FreshAirHigh = Field(8, 7)       # unverified
    AnnounceItem = Field(9, 0, 8)    # A_* announce id
    Light        = Field(12, 0, 2)   # LIGHTS index
    Beep         = Field(12, 2, 2)   # BEEPS index
    SwingV       = Field(12, 4, 4)   # SWING_V index
    SwingH       = Field(13, 0, 8)   # SWING_H index
    Streamer     = Field(14, 4)      # ストリーマ空清 (header: Clean)
    FilterClean  = Field(14, 7)      # フィルター掃除 (absent from header)
    Sum1         = Field(19, 0, 8)   # section 1 checksum
    Power        = Field(25, 0)      # main power
    OnTimer      = Field(25, 1)      # on-timer enabled
    OffTimer     = Field(25, 2)      # off-timer enabled
    Mode         = Field(25, 4, 3)   # MODES index
    Temp         = Field(26, 0, 7)   # target temp, or 快適自動 offset
    HumidOn      = Field(26, 7)      # humidity mode enabled
    Humidity     = Field(27, 0, 8)   # target humidity %, see HUMIDITY_*
    Fan          = Field(28, 4, 4)   # FANS index
    OnTime       = Field(30, 0, 12)  # on-timer time, minutes past midnight
    OffTime      = Field(31, 4, 12)  # off-timer time, minutes past midnight
    Powerful     = Field(33, 0)      # パワフル
    Quiet        = Field(33, 5)      # 静か運転; unverified
    Announce     = Field(34, 3)      # enable bit, gates AnnounceItem
    Eye          = Field(36, 1)      # unverified
    SensorSwing  = Field(36, 2)      # センサー風向 (header: Econo)
    Purify       = Field(36, 4)      # unverified
    SleepTimer   = Field(36, 5)      # on_timer_mode == sleep
    Sum2         = Field(38, 0, 8)   # section 2 checksum

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
    auto_offset: float = 0.0  # 快適自動 only
    fan: str = "auto"
    swing_v: str = "auto"
    swing_h: str = "auto"
    humidity_mode: str = "off"  # 切 | 連続 | 指定%
    humidity: int = 50
    heat_high: bool = False  # 高温風
    powerful: bool = False  # パワフル
    quiet: bool = False  # 静か運転; unverified
    streamer: bool = False  # ストリーマ空清
    filter_clean: bool = False  # フィルター掃除
    eye: str = "off"  # 留守エコ: off | 1h | 3h
    mold: bool = False  # 内部クリーン; unverified
    purify: bool = False  # unverified
    fresh_air: bool = False  # unverified
    fresh_air_high: bool = False  # unverified
    beep: str = "quiet"
    light: str = "bright"
    announce_enabled: bool = True
    on_timer_mode: str = "off"  # off | on_timer | sleep (they share one slot)
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

    # 快適自動 is the unit's only automatic mode; HA offers two names for it.
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
        Control(
            "purify",
            SWITCH,
            icon="mdi:air-purifier",
        ),
        Control(
            "fresh_air",
            SWITCH,
            icon="mdi:weather-windy",
        ),
        Control(
            "fresh_air_high",
            SWITCH,
            icon="mdi:weather-windy-variant",
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
            "on_timer_mode",
            SELECT,
            options=("off", "on_timer", "sleep"),
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

    # ── validation ───────────────────────────────────────────────────────────

    def temp_range(self, state: Daikin312State) -> tuple[float, float]:
        return TEMP_RANGES.get(state.mode, DEFAULT_TEMP_RANGE)

    def humidity_range(self, state: Daikin312State) -> tuple[int, int]:
        if steps := HUMIDITY_STEPS.get(state.mode):
            return steps[0], steps[-1]
        # Humidification is heat/dry only, but the slider still needs bounds.
        every = sorted({v for s in HUMIDITY_STEPS.values() for v in s})
        return every[0], every[-1]

    def apply(self, state: Daikin312State, changes: dict[str, Any]) -> Daikin312State:
        """Merge changes, clamp them to what the unit accepts, pick the announcement."""
        new = dataclasses.replace(state, **changes)
        changed = {k for k, v in changes.items() if getattr(state, k, None) != v}

        low, high = self.temp_range(new)
        temp = min(high, max(low, round(new.temp / TEMP_STEP) * TEMP_STEP))
        offset = min(
            MAX_AUTO_OFFSET,
            max(-MAX_AUTO_OFFSET, round(new.auto_offset / TEMP_STEP) * TEMP_STEP),
        )

        steps = HUMIDITY_STEPS.get(new.mode)
        humidity_mode = new.humidity_mode if steps else "off"
        humidity = (
            min(steps, key=lambda s: abs(s - new.humidity)) if steps else new.humidity
        )

        # Powerful and quiet are mutually exclusive on the unit.
        powerful, quiet = new.powerful, new.quiet
        if powerful and quiet:
            quiet = "quiet" not in changed

        new = dataclasses.replace(
            new,
            temp=temp,
            auto_offset=offset,
            humidity_mode=humidity_mode,
            humidity=humidity,
            powerful=powerful,
            quiet=quiet and not powerful,
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
                if state.swing_v == "auto" and state.swing_h == "auto":
                    return A_SWING_SENSOR  # センサー風向
                value = state.swing_v if key == "swing_v" else state.swing_h
                if value in ("breeze", "circulate"):
                    return A_CIRCULATION
                return A_SWING_V if key == "swing_v" else A_SWING_H
            if item == -3:  # on timer slot
                if state.on_timer_mode == "sleep":
                    return A_SLEEP
                return None if state.on_timer_mode == "off" else A_CANCEL
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
        # センサー風向 is one button that puts both directions on 自動, and the
        # captures only ever show this bit set when both are.
        f.SensorSwing = state.swing_v == "auto" and state.swing_h == "auto"

        if state.mode == MODE_AUTO:
            # 快適自動: the temperature byte carries a signed half-degree offset.
            f.Temp = 0x40 | (int(state.auto_offset * 2) & 0x1F)
            f.HumidOn = 1
            f.Humidity = HUMIDITY_COMFORT
        else:
            humidity = HUMIDITY_OFF
            if state.mode in HUMIDITY_STEPS:
                if state.humidity_mode == "continuous":
                    humidity = HUMIDITY_AUTO
                elif state.humidity_mode == "manual":
                    humidity = state.humidity
            f.Humidity = humidity
            f.HumidOn = humidity != HUMIDITY_OFF
            # With humidification on, the unit pins the temperature to its max.
            low, high = self.temp_range(state)
            temp = MAX_TEMP if f.HumidOn else min(high, max(low, state.temp))
            f.Temp = int(temp * 2)

        f.HeatHigh = state.heat_high and state.mode == MODE_HEAT
        f.Powerful = state.powerful
        f.Quiet = state.quiet
        f.Streamer = state.streamer
        f.FilterClean = state.filter_clean
        f.EyeTimer = EYE[state.eye]
        f.Mold = state.mold
        f.Purify = state.purify
        f.FreshAir = state.fresh_air
        f.FreshAirHigh = state.fresh_air_high
        f.Beep = BEEPS[state.beep]
        f.Light = LIGHTS[state.light]

        f.OnTime = state.on_timer if state.on_timer_mode != "off" else UNUSED_TIME
        f.OnTimer = state.on_timer_mode == "on_timer"
        f.SleepTimer = state.on_timer_mode == "sleep"
        f.OffTime = state.off_timer if state.off_timer_enabled else UNUSED_TIME
        f.OffTimer = state.off_timer_enabled

        f.AnnounceItem = state.announce_item
        f.Announce = state.announce_item != A_DISABLE and state.announce_enabled

        f.checksum()
        return f

    def timings(self, state: Daikin312State) -> list[int]:
        return self.pack(state).timings()


PROTOCOL = register(Daikin312Protocol())
