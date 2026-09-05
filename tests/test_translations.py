"""Every control and option must have a name in every language."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib import daikin312 as d

COMPONENT = Path(__file__).parents[1] / "custom_components" / "daikin_ir"
LANGUAGES = {
    path.stem: json.loads(path.read_text())
    for path in (COMPONENT / "translations").glob("*.json")
}
STRINGS = json.loads((COMPONENT / "strings.json").read_text())


def _keys(node, prefix=""):
    """Every leaf path in a nested dict, so two languages can be compared."""
    if not isinstance(node, dict):
        return {prefix}
    return {k for key, value in node.items() for k in _keys(value, f"{prefix}.{key}")}


def test_english_translation_matches_strings():
    assert LANGUAGES["en"] == STRINGS


@pytest.mark.parametrize("language", sorted(LANGUAGES))
def test_no_language_is_missing_keys(language):
    assert _keys(LANGUAGES[language]) == _keys(STRINGS)


@pytest.mark.parametrize("language", sorted(LANGUAGES))
def test_every_control_is_named(language):
    entity = LANGUAGES[language]["entity"]
    for control in d.PROTOCOL.controls:
        section = entity[control.kind]
        assert control.key in section, control.key
        assert section[control.key]["name"]
        for option in control.options:
            assert option in section[control.key]["state"], (control.key, option)


@pytest.mark.parametrize("language", sorted(LANGUAGES))
def test_every_climate_option_is_named(language):
    attributes = LANGUAGES[language]["entity"]["climate"]["daikin_ir"][
        "state_attributes"
    ]
    caps = d.PROTOCOL.capabilities
    for attribute, options in (
        ("fan_mode", caps.fan_modes),
        ("swing_mode", caps.swing_modes),
        ("swing_horizontal_mode", caps.swing_horizontal_modes),
    ):
        assert set(attributes[attribute]["state"]) == set(options), attribute
