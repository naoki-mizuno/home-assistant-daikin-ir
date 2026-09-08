<p align="center">
  <img src="brands/icon.png" width="96" alt="">
</p>

# Daikin IR

Home Assistant integration for Daikin air conditioners driven over infrared,
through supported MQTT-connected IR blaster.

It is meant to replace SmartIR's Daikin climate: instead of replaying a fixed
list of learned codes, it builds each frame from the protocol, so everything the
remote can do is available, including the parts a code list cannot express,
such as humidity setpoints, timers, beep/light settings etc.

Set up can be done from the UI. Add one entry per AC unit, since each one
usually has its own blaster in its own room.

## Controls and Sensors

- `climate` entity: power, mode, target temperature, target humidity, fan
  speed, vertical and horizontal swing.
- Separate entities for everything else the remote has: Powerful, Flash Streamer
  air purifying, Auto filter clean, High-temperature airflow, Sensor airflow
  (area/spot), Auto off, Auto mold proof, the on/off/sleep timers, Display
  brightness, Sound volume and Voice response ([Japanese terms](#japanese-terms)).
- Optional temperature, humidity and power sensors.

No `hvac_action` is reported. IR is write-only, so any "heating"/"idle" state
would be a guess, and a guess in the history graph is worse than nothing.

## Requirements

- Home Assistant 2025.3 or newer (for `swing_horizontal_modes`).
- The MQTT integration, and an IR blaster that accepts codes over MQTT —
  a Zigbee2MQTT Tuya IR blaster, a Broadlink bridge, or anything similar.

## Installation

HACS → three-dot menu → _Custom repositories_ → add this repository as an
_Integration_, then install and restart Home Assistant. Or copy
`custom_components/daikin_ir` into your `config/custom_components/`.

Then _Settings → Devices & services → Add integration → Daikin IR_.

| Setting           | Meaning                                                                                                          |
| ----------------- | ---------------------------------------------------------------------------------------------------------------- |
| Protocol          | Match your remote. Currently Daikin 312-bit (ARC472A43).                                                         |
| Output format     | What your blaster accepts: Tuya/Zigbee2MQTT or Broadlink base64.                                                 |
| MQTT topic        | Where the code is published, e.g. `zigbee2mqtt/UFO-R11/set`.                                                     |
| Payload key       | JSON key the code goes under. Empty uses the format's default (`ir_code_to_send` for Tuya, `b64` for Broadlink). |
| Send delay        | Window for coalescing multiple (burst of) commands. Empty uses 0.1 s, 0 sends every change on its own.           |
| Temp / hum sensor | Shown as the current temperature and humidity.                                                                   |
| Power sensor      | Corrects the assumed power state when something else turns the unit off.                                         |

All of them can be changed later from the entry's _Configure_ dialog.

## Untested controls

These bits are described by IRremoteESP8266's header but were never confirmed
against a real remote capture, so they are exposed and labelled _(untested)_:

- Outdoor unit quiet
- Air purifying
- Fresh air supply ventilation
- Fresh air supply ventilation, high.

If you can confirm one works (or does nothing), please open an issue.

## Supported hardware

Developed against an S40TTAXP-W with an ARC472A43 remote. Other Daikin models
that use the same 312-bit protocol should work.

IR blasters: Tuya UFO-R11, Tuya UFO-R4Z (both tuya format), and HOBEIAN ZG-IR01 (broadlink b64)

## Adding a protocol or an output format

Both are single files.

- A protocol is a module under `custom_components/daikin_ir/lib/` that
  subclasses `Protocol`, declares its `Capabilities` and `Control`s, and calls
  `register()`. The entities are built from that declaration, so no platform
  code changes.
- An output format is a module under `lib/codecs/` with
  `encode(timings, freq) -> str`, registered in `lib/codecs/__init__.py`.

Nothing under `lib/` imports Home Assistant, so it can be tested (or reused
from a script) on its own:

```console
$ python -m pytest
```

The tests check the generated frames against 59 frames dumped from a build of
IRremoteESP8266 and against 16 frames captured from a real remote.

## Japanese terms

The remote is Japanese-only, so the English names are Daikin's own, taken from
the English manuals for remotes that speak the same 312-bit protocol:

- [FTXZ-N (ARC477A1) operation manual, `3P338603-1G`](https://www.daikin.eu/content/dam/document-library/operation-manuals/ac/split/ftxz-n/FTXZ-N_3P338603-1G_Operation%20manual_English.pdf)
  — the Ururu Sarara, same feature set as the S40TTAXP, and its English text is
  the original the other languages are translated from.
- [CTXM-R / FTXM-R (ARC466A67) user reference guide, `4P518786-5F`](https://www.daikin.eu/content/dam/document-library/user%20reference%20guide/ac/Split/CTXM-R,FTXM-R_4PEN518786-5F_User%20reference%20guide_English.pdf)
- [Daikin's web manual for the ARC466A63](https://web-manual.dit-daikin.com/ra/en/remote_controller/)

| English (this integration)          | Japanese                                 |
| ----------------------------------- | ---------------------------------------- |
| Powerful                            | パワフル                                 |
| Flash Streamer air purifying        | ストリーマ空気清浄                       |
| Auto filter clean                   | フィルター自動掃除                       |
| Sensor airflow — Area / Spot        | センサー風向 — エリア送風 / スポット送風 |
| Auto off                            | 留守エコ                                 |
| Auto mold proof                     | 自動内部クリーン                         |
| Outdoor unit quiet                  | 室外ユニット静音                         |
| Air purifying                       | 空気清浄                                 |
| Fresh air supply ventilation        | 換気                                     |
| Display brightness — High, Low, Off | 表示明るさ — 明暗切                      |
| Sound volume                        | 音量                                     |
| Comfort sleep timer                 | おやすみ                                 |
| Indoor unit quiet (airflow rate)    | しずか                                   |
| Airflow rate 1-5                    | 風量1〜5                                 |
| Level 1-6 (vertical airflow)        | 1〜6段階目                               |
| Circulation airflow                 | サーキュレーション風向                   |
| Breeze airflow                      | ゆらぎ                                   |
| Wide                                | ワイド                                   |
| Front blowing                       | 正面吹き                                 |
| To the left / To the right          | 左寄り / 右寄り                          |

Three features appear Japanese-market only and couldn't be found in
any English Daikin manual, so their names here are made up:
**Comfort Auto** (快適自動), **High-temperature airflow** (高温風)
and **Voice response** (音声応答).

### Features with similar names

Below is a list of features that I personally found confusing due to their
names being similar.

- フィルター自動掃除 (Auto filter clean): mechanical. Little brush/vacuum sweeps dust off
  the intake filter into a dust box, so you skip manual filter washing. Doesn't touch
  room air. Same physical button, held 2s, does two different things depending on
  whether the unit is running or stopped: running toggles this persisted auto setting
  (what this integration exposes); stopped runs the cleaning cycle once, right now
  (フィルター掃除, not yet exposed — see the module docstring in `daikin312.py`).
- 自動内部クリーン (Auto mold proof): after cool/dry, runs fan (sometimes low heat) to dry
  out the internal heat exchanger, stops mold growing inside the unit. Hygiene for the
  unit, not the room. Same button/running-vs-stopped split as auto filter clean above
  (内部クリーン is the one-shot form, not yet exposed).
- ストリーマ空気清浄 (Flash Streamer air purifying): Daikin's "Streamer" plasma discharge tech, decomposes
  odor/allergens/bacteria on the filter and exchanger. The premium active-purify
  feature.
- 空気清浄 (Air purifying): plain air purification, filters/circulates room air without the
  Streamer discharge. The base version of the same idea.

### Features not present in Japanese models

- Comfort sleep timer): dual-use of the "on timer time" field.
  Not supported on Japanese models, but possible on FTXZ-N.
  Labelled 快適おやすみタイマー for feature-completeness.
- Quiet: FTXZ-N documents a feature called OUTDOOR UNIT QUIET, which reduces
  the noise produced by the outdoor unit. No button or
  menu path on any Japanese-market remote I checked (S40WTRXP-W, S40TTAXP-W).
  Labelled 室外ユニット静音 here for feature-completeness.
- ECONO: lives on that same ECONO/QUIET button.
  Caps power draw during a running session. Note that it is unrelated to AUTO OFF (留守エコ), which is a stop timer for nobody-home.
  Not exposed as its own control since bit field conflicts with sensor auto feature. Need real captures with ECONO on/off to verify bit field location.

## Credits

- [IRremoteESP8266](https://github.com/crankyoldgit/IRremoteESP8266) — the
  protocol documentation this is built on.
- [SmartIR](https://github.com/litinoveweedle/SmartIR) — the integration this
  aims to replace, and the source of the sensor-linking idea.
- [mildsunrise's Tuya IR notes](https://gist.github.com/mildsunrise/1d576669b63a260d2cff35fda63ec0b5)
  — the FastLZ code format.

## License

MIT (see [LICENSE](LICENSE))

Daikin is a trademark of Daikin Industries, Ltd., and this project is not affiliated with them.

## Author

Naoki Mizuno (naoki.mizuno.256@gmail.com) with Claude
