# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Gabi Falk

"""Tests for the Keymap emulator."""

from __future__ import annotations

from pathlib import Path

import pytest

from shinobi_keymap import yaml_reader
from shinobi_keymap.emulator import (
    Emulator,
    Event,
    KeyNotHeldError,
    UnknownKeyError,
)
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


def _empty_keymap(layout: str = "ANSI") -> Keymap:
    km = Keymap(layout=layout)
    fill_defaults(km)
    return km


# ---------------------------------------------------------- basic press/release

def test_tap_a_emits_press_then_release():
    e = Emulator(_empty_keymap())
    assert e.tap("A") == [Event("PRESS", "A"), Event("RELEASE", "A")]


def test_press_tracks_held_keys():
    e = Emulator(_empty_keymap())
    e.press("A")
    assert e.held_keys == ["A"]
    e.press("B")
    assert e.held_keys == ["A", "B"]
    e.release("A")
    assert e.held_keys == ["B"]


def test_release_unheld_key_raises():
    e = Emulator(_empty_keymap())
    with pytest.raises(KeyNotHeldError):
        e.release("A")


def test_unknown_key_raises():
    e = Emulator(_empty_keymap())
    with pytest.raises(UnknownKeyError):
        e.press("NOPE")


def test_reset_clears_state():
    e = Emulator(_empty_keymap())
    e.press("A")
    e.press("G12")
    assert e.active_layer == "fn1"
    assert e.held_keys == ["A", "G12"]
    e.reset()
    assert e.active_layer == "base"
    assert e.held_keys == []


# ---------------------------------------------------------- fn-trigger behavior

def test_default_g12_activates_fn1():
    e = Emulator(_empty_keymap())
    assert e.press("G12") == []
    assert e.active_layer == "fn1"


def test_releasing_active_fn_returns_to_base():
    e = Emulator(_empty_keymap())
    e.press("G12")
    e.release("G12")
    assert e.active_layer == "base"


def test_pressing_a_while_fn1_held_emits_layer_specific_default():
    # Default fn1.1 is TP_SPEED1.
    e = Emulator(_empty_keymap())
    e.press("G12")
    assert e.tap("1") == [Event("PRESS", "TP_SPEED1"), Event("RELEASE", "TP_SPEED1")]


def test_only_first_fn_trigger_activates():
    # Demote G12 from fn1 and bind END as fn2 in profile 1 to set up two
    # competing fn-triggers in the same profile.
    km = Keymap(layout="ANSI")
    km.bindings[keyinfo_from_name("G12")] = {1: KeyBinding(fn_role=1)}
    km.bindings[keyinfo_from_name("END")] = {1: KeyBinding(fn_role=2)}
    fill_defaults(km)
    e = Emulator(km, profile_id=1)
    e.press("G12")
    assert e.active_layer == "fn1"
    e.press("END")
    assert e.active_layer == "fn1"  # FN2 ignored while FN1 still held
    e.release("G12")
    assert e.active_layer == "base"


# ---------------------------------------------------------- overrides

def test_overridden_base_action_is_emitted():
    km = _empty_keymap()
    km.bindings[keyinfo_from_name("CAPS_LOCK")][1].base = keyaction_from_name("ESC")
    e = Emulator(km)
    assert e.tap("CAPS_LOCK") == [Event("PRESS", "ESC"), Event("RELEASE", "ESC")]


def test_overridden_fn1_action_is_emitted():
    km = _empty_keymap()
    km.bindings[keyinfo_from_name("A")][1].fn1 = keyaction_from_name("F1")
    e = Emulator(km)
    e.press("G12")  # activates fn1
    assert e.tap("A") == [Event("PRESS", "F1"), Event("RELEASE", "F1")]


def test_no_keycode_silenced():
    km = _empty_keymap()
    km.bindings[keyinfo_from_name("CAPS_LOCK")][1].base = keyaction_from_name("NO")
    e = Emulator(km)
    assert e.tap("CAPS_LOCK") == []


# ---------------------------------------------------------- macros

def test_macro_binding_expands_on_press():
    km = _empty_keymap()
    km.macros["copy"] = [
        MacroEvent("press", keyaction_from_name("L_CTRL"), 0),
        MacroEvent("press", keyaction_from_name("C"), 50),
        MacroEvent("release", keyaction_from_name("C"), 0),
        MacroEvent("release", keyaction_from_name("L_CTRL"), 0),
    ]
    km.bindings[keyinfo_from_name("CAPS_LOCK")][1].base = MacroAction("copy")
    e = Emulator(km)
    events = e.press("CAPS_LOCK")
    assert events == [
        Event("PRESS", "L_CTRL", delay_ms=0),
        Event("PRESS", "C", delay_ms=50),
        Event("RELEASE", "C", delay_ms=0),
        Event("RELEASE", "L_CTRL", delay_ms=0),
    ]
    # Releasing a macro-bound key emits no events.
    assert e.release("CAPS_LOCK") == []


def test_unknown_macro_reference_silently_empty():
    km = _empty_keymap()
    km.bindings[keyinfo_from_name("A")][1].base = MacroAction("ghost")
    e = Emulator(km)
    assert e.press("A") == []


# ---------------------------------------------------------- profile selection

def test_profile_id_selects_which_profile():
    km = Keymap(layout="ANSI")
    km.bindings[keyinfo_from_name("A")] = {
        1: KeyBinding(base=keyaction_from_name("ESC")),
        2: KeyBinding(base=keyaction_from_name("F1")),
    }
    fill_defaults(km)
    e1 = Emulator(km, profile_id=1)
    e2 = Emulator(km, profile_id=2)
    assert e1.press("A") == [Event("PRESS", "ESC")]
    assert e2.press("A") == [Event("PRESS", "F1")]


def test_invalid_profile_id_raises():
    with pytest.raises(ValueError):
        Emulator(_empty_keymap(), profile_id=4)


# ---------------------------------------------------------- fixture-driven

def test_fn_test_fixture_overlays():
    km = yaml_reader.read(FIXTURES_YAML / "KEYMAP_FN_TEST.yaml")
    e = Emulator(km, profile_id=1)
    # Profile 1: G12=FN1, END=FN2, PGDN=FN3; A.fn1=F1, A.fn2=F2, A.fn3=F3.
    e.press("G12")
    assert e.tap("A") == [Event("PRESS", "F1"), Event("RELEASE", "F1")]
    e.release("G12")
    e.press("END")
    assert e.tap("A") == [Event("PRESS", "F2"), Event("RELEASE", "F2")]
    e.release("END")
    e.press("PGDN")
    assert e.tap("A") == [Event("PRESS", "F3"), Event("RELEASE", "F3")]


def test_keys_not_on_layout_are_silent():
    # CODE45 is ISO-only; in an ANSI keymap, pressing it produces nothing.
    km = _empty_keymap("ANSI")
    e = Emulator(km)
    assert e.press(keyinfo_from_name("CODE45")) == []
    assert e.release(keyinfo_from_name("CODE45")) == []
