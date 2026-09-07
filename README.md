<img src="brands/icon.png" width="96" align="right" alt="">

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
  air purifying, Cleaning filter, High-temperature airflow, Sensor airflow
  (area/spot), Auto off, Mold proof, the on/off/sleep timers, Display
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
| Temp / hum sensor | Shown as the current temperature and humidity.                                                                   |
| Power sensor      | Corrects the assumed power state when something else turns the unit off.                                         |

All of them can be changed later from the entry's _Configure_ dialog.

## Untested controls

These bits are described by IRremoteESP8266's header but were never confirmed
against a real remote capture, so they are exposed and labelled _(untested)_:

- Mold proof
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
| Cleaning filter                     | フィルター掃除                           |
| Sensor airflow — Area / Spot        | センサー風向 — エリア送風 / スポット送風 |
| Auto off                            | 留守エコ                                 |
| Mold proof                          | 内部クリーン                             |
| Outdoor unit quiet                  | 静か運転                                 |
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

- フィルター掃除 (Cleaning filter): mechanical. Little brush/vacuum sweeps dust off the
  intake filter into a dust box, so you skip manual filter washing. Doesn't touch room
  air.
- 内部クリーン (Mold proof): after cool/dry, runs fan (sometimes low heat) to dry out the
  internal heat exchanger, stops mold growing inside the unit. Hygiene for the unit, not
  the room.
- ストリーマ空気清浄 (Flash Streamer air purifying): Daikin's "Streamer" plasma discharge tech, decomposes
  odor/allergens/bacteria on the filter and exchanger. The premium active-purify
  feature.
- 空気清浄 (Air purifying): plain air purification, filters/circulates room air without the
  Streamer discharge. The base version of the same idea.

Also, the "on timer time" is dual-use: on timer and comfort sleep timer.
Comfort sleep timer is not supported in Japanese models, but is possible for FTXZ-N.
It is labelled 快適おやすみタイマー in Japanese for the sake of feature-completeness.

Similarly, the `quiet` switch (raw[33] bit5) has no button or menu path on any
Japanese-market remote I checked (S40WTRXP-W, S40TTAXP-W). FTXZ-N's manual has
a matching feature, OUTDOOR UNIT QUIET (lowers outdoor unit noise), triggered
by an ECONO/QUIET button that JP remotes don't have. Labelled 室外ユニット静音
here for feature-completeness; state unconfirmed by capture on a JP unit.

ECONO on that same button is itself unrelated to auto off (留守エコ, raw[7]
bits6-7, `eye`): ECONO caps power draw during a running session, Auto off is
a stop timer armed when nobody's home. Different sections of the manual,
different bits. A batch of capture fixtures once carried "econo\_\*" source
labels for Auto off captures — fixed, but noted here in case it resurfaces.

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
