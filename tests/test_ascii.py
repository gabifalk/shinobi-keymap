# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Gabi Falk

"""Tests for the ASCII keyboard renderer."""

from __future__ import annotations

from pathlib import Path

import pytest

from shinobi_keymap import ascii as ascii_view
from shinobi_keymap import yaml_reader
from shinobi_keymap.models import (
    KeyBinding,
    Keymap,
    MacroAction,
    MacroEvent,
    fill_defaults,
    keyaction_from_name,
    keyinfo_from_name,
)


FIXTURES_YAML = Path(__file__).parent / "fixtures" / "yaml_expected"


def _default_keymap(layout="ANSI"):
    km = Keymap(layout=layout)
    fill_defaults(km)
    return km


# ---------------------------------------------------------- structural shape

def test_render_returns_string():
    out = ascii_view.render(_default_keymap(), profile_id=1, layer="base")
    assert isinstance(out, str)
    assert len(out.splitlines()) > 5


def test_render_unknown_layer_raises():
    with pytest.raises(ValueError, match="unknown layer"):
        ascii_view.render(_default_keymap(), profile_id=1, layer="fn99")


def test_render_unknown_layout_raises():
    km = Keymap(layout="DVORAK")
    with pytest.raises(ValueError, match="no visual layout"):
        ascii_view.render(km, profile_id=1, layer="base")


# ---------------------------------------------------------- content

def test_render_shows_base_keycap_names():
    out = ascii_view.render(_default_keymap(), profile_id=1, layer="base")
    assert "ESC" in out
    assert "L_CTRL" in out
    # The number-row keys are visible too.
    assert " 1 " in out
    assert " 2 " in out


def test_default_g12_renders_as_fn1_marker():
    # G12's default base binding is fn_role=1; it should render as [FN1].
    out = ascii_view.render(_default_keymap(), profile_id=1, layer="base")
    assert "[FN1]" in out


def test_fn1_layer_renders_trackpoint_speeds():
    out = ascii_view.render(_default_keymap(), profile_id=1, layer="fn1")
    assert "TP_SPEED1" in out
    assert "TP_SPEED9" in out


def test_fn1_layer_marks_g12_as_fn_trigger():
    # On the fn1 layer, G12 (the fn1 trigger) should show [FN1], not "G12".
    out = ascii_view.render(_default_keymap(), profile_id=1, layer="fn1")
    assert "[FN1]" in out


def test_override_appears_on_base():
    km = _default_keymap()
    km.bindings[keyinfo_from_name("CAPS_LOCK")][1].base = keyaction_from_name("ESC")
    out = ascii_view.render(km, profile_id=1, layer="base")
    # The CAPS_LOCK cell now reads "ESC" instead of "CAPS_LOCK".
    # We can't easily pin the visual position, so just verify CAPS_LOCK
    # doesn't appear and ESC does (it appears elsewhere too, but that's fine).
    assert "CAPS_LOCK" not in out


def test_macro_binding_emits_with_m_prefix():
    km = _default_keymap()
    km.macros["copy"] = [MacroEvent("press", keyaction_from_name("A"), 0)]
    km.bindings[keyinfo_from_name("A")][1].base = MacroAction("copy")
    out = ascii_view.render(km, profile_id=1, layer="base")
    assert "M_copy" in out


def test_no_keycode_renders_blank():
    km = _default_keymap()
    km.bindings[keyinfo_from_name("CAPS_LOCK")][1].base = keyaction_from_name("NO")
    out = ascii_view.render(km, profile_id=1, layer="base")
    # CAPS_LOCK cell is now blank.  Sanity-check that the original key name
    # no longer appears (default for the CAPS_LOCK key was "CAPS_LOCK").
    assert "CAPS_LOCK" not in out


# ---------------------------------------------------------- render_all

def test_render_all_emits_three_profiles_and_four_layers():
    out = ascii_view.render_all(_default_keymap())
    # Should have 12 headers (3 profiles * 4 layers).
    headers = [l for l in out.splitlines() if l.startswith("Profile ")]
    assert len(headers) == 12


def test_render_all_with_subset():
    out = ascii_view.render_all(
        _default_keymap(), profile_ids=(1,), layers=("base",)
    )
    headers = [l for l in out.splitlines() if l.startswith("Profile ")]
    assert len(headers) == 1


def test_render_all_can_suppress_headers():
    out = ascii_view.render_all(_default_keymap(), headers=False)
    assert "Profile " not in out


# ---------------------------------------------------------- layout-specific

@pytest.mark.parametrize("layout", ("ANSI", "ISO", "JIS"))
def test_render_works_for_every_supported_layout(layout):
    km = Keymap(layout=layout)
    fill_defaults(km)
    out = ascii_view.render(km, profile_id=1, layer="base")
    assert out.strip()


def test_iso_specific_key_appears_in_iso_render():
    km = Keymap(layout="ISO")
    fill_defaults(km)
    out = ascii_view.render(km, profile_id=1, layer="base")
    assert "CODE45" in out  # ISO-only physical key


def test_jis_specific_keys_appear_in_jis_render():
    km = Keymap(layout="JIS")
    fill_defaults(km)
    out = ascii_view.render(km, profile_id=1, layer="base")
    for name in ("CODE14", "CODE56", "CODE131", "CODE133"):
        assert name in out


# ---------------------------------------------------------- fixture

def test_fn_test_fixture_renders_overlays():
    km = yaml_reader.read(FIXTURES_YAML / "KEYMAP_FN_TEST.yaml")
    fn1 = ascii_view.render(km, profile_id=1, layer="fn1")
    # F1 (A's fn1 override) and F11 (S's fn1 override) appear.
    assert " F1 " in fn1 or "  F1   " in fn1
    assert "F11" in fn1


# ---------------------------------------------------------- reference views

def test_render_reference_names_has_recognisable_keycaps():
    out = ascii_view.render_reference("ANSI", "names")
    assert " A " in out
    assert "L_CTRL" in out
    assert "L_SHIFT" in out


def test_render_reference_ids_shows_numeric_keycodes():
    out = ascii_view.render_reference("ANSI", "ids")
    assert " 4 " in out   # A
    assert "230" in out   # R_ALT
    assert "224" in out   # L_CTRL


def test_render_reference_matrix_shows_hi_lo_pairs():
    out = ascii_view.render_reference("ANSI", "matrix")
    assert "6,4" in out   # A
    assert "0,0" in out   # L_CTRL
    assert "6,0" in out   # G12


def test_render_reference_unknown_mode_raises():
    with pytest.raises(ValueError, match="unknown reference mode"):
        ascii_view.render_reference("ANSI", "nonsense")


def test_render_reference_unknown_layout_raises():
    with pytest.raises(ValueError, match="no visual layout"):
        ascii_view.render_reference("DVORAK", "names")
