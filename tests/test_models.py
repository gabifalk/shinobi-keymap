# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Gabi Falk

"""Tests for the format-agnostic keymap types."""

from __future__ import annotations

import pytest

from shinobi_keymap.constants import KEYCODE_TO_NAME, KEYCODES
from shinobi_keymap.models import (
    KeyAction,
    KeyBinding,
    KeyInfo,
    Keymap,
    MacroAction,
    MacroEvent,
    default_keymap,
    fill_defaults,
    keyaction_from_id,
    keyaction_from_name,
    keyinfo_from_id,
    keyinfo_from_name,
    keyinfo_from_phys,
)


# ---------------------------------------------------------------- KeyInfo

def test_keyinfo_three_factories_produce_equal_value():
    by_name = keyinfo_from_name("A")
    by_id = keyinfo_from_id(4)
    by_phys = keyinfo_from_phys("ANSI", 6, 4)
    assert by_name == by_id == by_phys
    assert hash(by_name) == hash(by_id) == hash(by_phys)


def test_keyinfo_repr_uses_name():
    assert repr(keyinfo_from_name("A")) == "KeyInfo('A')"


def test_keyinfo_enter_unifies_across_layouts():
    ansi = keyinfo_from_phys("ANSI", 1, 2)
    iso = keyinfo_from_phys("ISO", 4, 4)
    jis = keyinfo_from_phys("JIS", 4, 4)
    assert ansi == iso == jis == keyinfo_from_name("ENTER")


def test_keyinfo_backslash_unifies_across_layouts():
    ansi = keyinfo_from_phys("ANSI", 4, 4)
    iso = keyinfo_from_phys("ISO", 1, 2)
    assert ansi == iso == keyinfo_from_name("BACKSLASH")


def test_keyinfo_from_phys_rejects_position_not_on_layout():
    # CODE45 is ISO-only; CODE56 is JIS-only.
    with pytest.raises(KeyError):
        keyinfo_from_phys("ANSI", 3, 2)        # CODE45 position
    with pytest.raises(KeyError):
        keyinfo_from_phys("ANSI", 7, 1)        # CODE56 position
    with pytest.raises(KeyError):
        keyinfo_from_phys("ANSI", 13, 6)       # CODE133 position


def test_keyinfo_rejects_action_only_names():
    for name in ("FN1", "FN2", "FN3", "NO", "NUM_LOCK", "TP_SPEED1", "BAD_ESC"):
        with pytest.raises(ValueError, match="not a physical key"):
            keyinfo_from_name(name)


def test_keyinfo_rejects_action_only_keycodes():
    for keycode in (0, 232, 220, 222, 305, 397, 317):
        with pytest.raises(ValueError, match="not a physical key"):
            keyinfo_from_id(keycode)


def test_keyinfo_unknown_name_raises_value_error():
    with pytest.raises(ValueError, match="not a known .TEX keycode name"):
        keyinfo_from_name("DEFINITELY_NOT_A_KEY")


# ---------------------------------------------------------------- KeyAction

def test_keyaction_accepts_action_only_codes():
    fn1 = keyaction_from_name("FN1")
    assert fn1.keycode == 232
    assert fn1.name == "FN1"


def test_keyaction_accepts_physical_keycodes_too():
    # A keycode is fine on the action side (e.g. CAPS_LOCK -> ESC remap).
    esc = keyaction_from_name("ESC")
    assert esc.keycode == 41
    assert esc == keyaction_from_id(41)


def test_keyaction_rejects_unknown_keycode():
    with pytest.raises(ValueError, match="not a known .TEX keycode"):
        keyaction_from_id(999)


def test_keyaction_repr_uses_name():
    assert repr(keyaction_from_name("F1")) == "KeyAction('F1')"


# -------------------------------------------------- cross-type interactions

def test_keyinfo_and_keyaction_not_equal_for_same_keycode():
    info = keyinfo_from_name("A")
    action = keyaction_from_name("A")
    assert info.keycode == action.keycode
    assert info != action
    assert action != info


def test_keyinfo_works_as_dict_key_across_factory_forms():
    d = {keyinfo_from_name("A"): "from-name"}
    assert d[keyinfo_from_id(4)] == "from-name"
    assert d[keyinfo_from_phys("ANSI", 6, 4)] == "from-name"


# ---------------------------------------------------------------- MacroAction

def test_macroaction_equality_by_name():
    assert MacroAction("copy") == MacroAction("copy")
    assert MacroAction("copy") != MacroAction("paste")


def test_macroaction_repr():
    assert repr(MacroAction("copy")) == "MacroAction('copy')"


# ---------------------------------------------------------------- KeyBinding

def test_keybinding_defaults_all_none():
    b = KeyBinding()
    assert b.fn_role is None
    assert b.base is None
    assert b.fn1 is None
    assert b.fn2 is None
    assert b.fn3 is None


def test_keybinding_repr_fn_role():
    assert repr(KeyBinding(fn_role=1)) == "KeyBinding(fn_role=1)"


def test_keybinding_repr_skips_none_slots():
    b = KeyBinding(base=keyaction_from_name("ESC"), fn1=keyaction_from_name("F1"))
    assert repr(b) == "KeyBinding(base=KeyAction('ESC'), fn1=KeyAction('F1'))"


def test_keybinding_accepts_macro_action_in_layer_slot():
    b = KeyBinding(base=MacroAction("copy"))
    assert b.base == MacroAction("copy")
    assert "MacroAction" in repr(b)


def test_keybinding_equality():
    a = KeyBinding(base=keyaction_from_name("ESC"), fn1=keyaction_from_name("F1"))
    b = KeyBinding(base=keyaction_from_name("ESC"), fn1=keyaction_from_name("F1"))
    c = KeyBinding(base=keyaction_from_name("ESC"))
    d = KeyBinding(fn_role=1)
    e = KeyBinding(fn_role=1)
    assert a == b
    assert a != c
    assert d == e
    assert a != d


# ---------------------------------------------------------------- MacroEvent

def test_macroevent_construction_and_repr():
    e = MacroEvent("press", keyaction_from_name("C"), 50)
    assert e.action == "press"
    assert e.key.name == "C"
    assert e.delay == 50
    assert repr(e) == "MacroEvent('press', KeyAction('C'), delay=50)"


def test_macroevent_equality():
    a = MacroEvent("press", keyaction_from_name("C"), 50)
    b = MacroEvent("press", keyaction_from_name("C"), 50)
    c = MacroEvent("release", keyaction_from_name("C"), 50)
    d = MacroEvent("press", keyaction_from_name("C"), 0)
    assert a == b
    assert a != c
    assert a != d


def test_macro_lists_compare_element_wise():
    a = [
        MacroEvent("press", keyaction_from_name("L_CTRL"), 0),
        MacroEvent("press", keyaction_from_name("C"), 50),
    ]
    b = [
        MacroEvent("press", keyaction_from_name("L_CTRL"), 0),
        MacroEvent("press", keyaction_from_name("C"), 50),
    ]
    assert a == b


# ---------------------------------------------------------------- Keymap

def test_keymap_defaults_to_empty_independent_dicts():
    a = Keymap(layout="ANSI")
    b = Keymap(layout="ISO")
    assert a.bindings == {}
    assert a.macros == {}
    a.bindings[keyinfo_from_name("A")] = {}
    assert b.bindings == {}  # not shared


def test_keymap_end_to_end_lookup():
    km = Keymap(layout="ANSI")
    key = keyinfo_from_name("CAPS_LOCK")
    km.bindings[key] = {1: KeyBinding(base=keyaction_from_name("ESC"))}

    # Look up via a different factory form.
    same_key = keyinfo_from_phys("ANSI", 5, 4)
    assert km.bindings[same_key][1].base == keyaction_from_name("ESC")


def test_keymap_macro_plumbing():
    km = Keymap(layout="ANSI")
    km.macros["copy"] = [
        MacroEvent("press", keyaction_from_name("L_CTRL"), 0),
        MacroEvent("press", keyaction_from_name("C"), 50),
        MacroEvent("release", keyaction_from_name("C"), 0),
        MacroEvent("release", keyaction_from_name("L_CTRL"), 0),
    ]
    km.bindings[keyinfo_from_name("B")] = {1: KeyBinding(base=MacroAction("copy"))}

    binding = km.bindings[keyinfo_from_name("B")][1]
    assert isinstance(binding.base, MacroAction)
    assert binding.base.name == "copy"
    assert binding.base.name in km.macros
    assert len(km.macros[binding.base.name]) == 4


# ---------------------------------------------------- default bindings

def test_default_keymap_self_mapping_for_most_keys():
    dk = default_keymap("ANSI")
    a = dk.bindings[keyinfo_from_name("A")][1]
    assert a.base == keyaction_from_name("A")
    assert a.fn1 == keyaction_from_name("A")
    assert a.fn2 == keyaction_from_name("A")
    assert a.fn3 == keyaction_from_name("A")


def test_default_keymap_g12_is_fn1_trigger():
    dk = default_keymap("ANSI")
    for pid in (1, 2, 3):
        binding = dk.bindings[keyinfo_from_name("G12")][pid]
        assert binding.fn_role == 1
        assert binding.base is None
        assert binding.fn1 is None


def test_default_keymap_fn1_layer_has_trackpoint_speeds():
    dk = default_keymap("ANSI")
    for n in range(1, 10):
        binding = dk.bindings[keyinfo_from_name(str(n))][1]
        assert binding.fn1 == keyaction_from_name(f"TP_SPEED{n}")
        # base/fn2/fn3 stay as self-mapping
        assert binding.base == keyaction_from_name(str(n))


def test_default_keymap_fn1_layer_has_media_arrows():
    dk = default_keymap("ANSI")
    pairs = {
        "R_ARROW": "NEXT_TRACK",
        "L_ARROW": "PRE_TRACK",
        "DN_ARROW": "PLAY_PAUSE",
        "UP_ARROW": "STOP",
    }
    for key_name, action_name in pairs.items():
        binding = dk.bindings[keyinfo_from_name(key_name)][1]
        assert binding.fn1 == keyaction_from_name(action_name)


def test_default_keymap_only_includes_layout_specific_keys():
    # CODE45 is ISO-only.
    dk = default_keymap("ANSI")
    assert keyinfo_from_name("CODE45") not in dk.bindings
    dk = default_keymap("ISO")
    assert keyinfo_from_name("CODE45") in dk.bindings
    # CODE56 is JIS-only.
    dk = default_keymap("ANSI")
    assert keyinfo_from_name("CODE56") not in dk.bindings
    dk = default_keymap("JIS")
    assert keyinfo_from_name("CODE56") in dk.bindings


def test_fill_defaults_populates_every_physical_key():
    km = Keymap(layout="ANSI")
    fill_defaults(km)
    a = km.bindings[keyinfo_from_name("A")]
    for pid in (1, 2, 3):
        assert a[pid].base == keyaction_from_name("A")


def test_fill_defaults_preserves_existing_overrides():
    km = Keymap(layout="ANSI")
    caps = keyinfo_from_name("CAPS_LOCK")
    km.bindings[caps] = {1: KeyBinding(base=keyaction_from_name("ESC"))}
    fill_defaults(km)
    # The override survives, and -- since CAPS_LOCK has no fn-layer-specific
    # default -- it cascades to all the fn layers in this profile.
    assert km.bindings[caps][1].base == keyaction_from_name("ESC")
    assert km.bindings[caps][1].fn1 == keyaction_from_name("ESC")
    assert km.bindings[caps][1].fn2 == keyaction_from_name("ESC")
    assert km.bindings[caps][1].fn3 == keyaction_from_name("ESC")
    # The other profiles weren't touched by the override, so they get the
    # plain self-mapping default.
    assert km.bindings[caps][2].base == keyaction_from_name("CAPS_LOCK")
    assert km.bindings[caps][2].fn1 == keyaction_from_name("CAPS_LOCK")


def test_fill_defaults_skips_fn_role_keys():
    km = Keymap(layout="ANSI")
    g12 = keyinfo_from_name("G12")
    km.bindings[g12] = {1: KeyBinding(fn_role=2)}  # explicit user override
    fill_defaults(km)
    binding = km.bindings[g12][1]
    assert binding.fn_role == 2
    assert binding.base is None


def test_fill_defaults_demotes_g12_when_user_sets_a_slot():
    # User overrides G12.base.  The default fn_role=1 is dropped; the other
    # layers cascade from the resolved base (no fn-layer-specific default
    # for G12) -- so they all become L_CTRL as well.
    km = Keymap(layout="ANSI")
    g12 = keyinfo_from_name("G12")
    km.bindings[g12] = {1: KeyBinding(base=keyaction_from_name("L_CTRL"))}
    fill_defaults(km)
    binding = km.bindings[g12][1]
    assert binding.fn_role is None
    assert binding.base == keyaction_from_name("L_CTRL")
    assert binding.fn1 == keyaction_from_name("L_CTRL")
    assert binding.fn2 == keyaction_from_name("L_CTRL")
    assert binding.fn3 == keyaction_from_name("L_CTRL")


def test_fill_defaults_g12_default_is_fn1():
    # No user override: G12 should end up with fn_role=1 across all profiles.
    km = Keymap(layout="ANSI")
    fill_defaults(km)
    for pid in (1, 2, 3):
        assert km.bindings[keyinfo_from_name("G12")][pid].fn_role == 1


def test_fill_defaults_fn1_number_row_is_trackpoint_speed():
    km = Keymap(layout="ANSI")
    fill_defaults(km)
    one = km.bindings[keyinfo_from_name("1")][1]
    assert one.fn1 == keyaction_from_name("TP_SPEED1")
    assert one.base == keyaction_from_name("1")


def test_fill_defaults_base_override_cascades_to_fn_layers():
    # PGUP has no fn-layer-specific defaults, so a base override propagates
    # through fn1/fn2/fn3.
    km = Keymap(layout="ANSI")
    pgup = keyinfo_from_name("PGUP")
    km.bindings[pgup] = {1: KeyBinding(base=keyaction_from_name("END"))}
    fill_defaults(km)
    binding = km.bindings[pgup][1]
    assert binding.base == keyaction_from_name("END")
    assert binding.fn1 == keyaction_from_name("END")
    assert binding.fn2 == keyaction_from_name("END")
    assert binding.fn3 == keyaction_from_name("END")


def test_fill_defaults_base_override_does_not_overwrite_layer_specific_default():
    # The "1" key has a fn1-specific default (TP_SPEED1) that survives a
    # base override.  Other fn layers (no layer-specific default) cascade.
    km = Keymap(layout="ANSI")
    one = keyinfo_from_name("1")
    km.bindings[one] = {1: KeyBinding(base=keyaction_from_name("ESC"))}
    fill_defaults(km)
    binding = km.bindings[one][1]
    assert binding.base == keyaction_from_name("ESC")
    assert binding.fn1 == keyaction_from_name("TP_SPEED1")  # layer-specific, unchanged
    assert binding.fn2 == keyaction_from_name("ESC")  # cascade
    assert binding.fn3 == keyaction_from_name("ESC")


# ---------------------------------------------------- constants sanity checks

def test_every_physical_key_has_known_name():
    from shinobi_keymap.constants import PHYSICAL_KEYCODES

    for keycode in PHYSICAL_KEYCODES:
        assert keycode in KEYCODE_TO_NAME, keycode


def test_every_tex_keycode_round_trips():
    for name, keycode in KEYCODES.items():
        assert KEYCODE_TO_NAME[keycode] == name


def test_matrix_tables_are_consistent():
    from shinobi_keymap.constants import KEYCODE_TO_MATRIX, LAYOUTS, MATRIX_TO_KEYCODE

    for layout in LAYOUTS:
        for (hi, lo), keycode in MATRIX_TO_KEYCODE[layout].items():
            assert KEYCODE_TO_MATRIX[layout][keycode] == (hi, lo)
