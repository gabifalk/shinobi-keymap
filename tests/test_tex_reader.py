# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Gabi Falk

"""Tests for the .TEX -> Keymap reader."""

from __future__ import annotations

from pathlib import Path

import pytest

from shinobi_keymap import tex_reader
from shinobi_keymap.models import (
    KeyAction,
    KeyBinding,
    MacroAction,
    keyaction_from_name,
    keyinfo_from_name,
)


FIXTURES = Path(__file__).parent / "fixtures" / "tex_files"


# All fixtures, with the layout they should be read as.
ALL_FIXTURES = [
    ("KEYMAP", "ANSI"),
    ("KEYMAP_DEFAULT_ANSI", "ANSI"),
    ("KEYMAP_DEFAULT_ISO", "ISO"),
    ("KEYMAP_DEFAULT_JIS", "JIS"),
    ("KEYMAP_EMPTY", "ANSI"),
    ("KEYMAP_FN_TEST", "ANSI"),
    ("KEYMAP_GABI", "ANSI"),
    ("KEYMAP_KLETSKOVG", "ANSI"),
    ("KEYMAP_MACRO_FN_OVERRIDE", "ANSI"),
    ("KEYMAP_MAX_MACROS", "ANSI"),
    ("KEYMAP_TOUCHED", "ANSI"),
    ("KEYMAP_WEB_COMPLEX", "ANSI"),
    ("KEYMAP_WEB_WITH_MACROS", "ANSI"),
    ("KEYMAP_WITH_MACRO", "ANSI"),
]


@pytest.mark.parametrize("name,layout", ALL_FIXTURES)
def test_every_fixture_parses(name, layout):
    km = tex_reader.read(FIXTURES / f"{name}.TEX", layout)
    assert km.layout == layout
    assert isinstance(km.bindings, dict)
    assert isinstance(km.macros, dict)


# ---------------------------------------------------------- header validation

def test_bad_magic_raises():
    with pytest.raises(ValueError, match="bad magic"):
        tex_reader.loads(b"NOPE\x00\x00\x00\x00", "ANSI")


def test_unknown_section_kind_raises():
    # Header says 1 section, but kind byte is unknown.
    data = b"CYFI\x00\x00\x01\x00" + b"\x99\x01\x00\x00\x10\x00\x00\x00"
    with pytest.raises(ValueError, match="unknown section kind"):
        tex_reader.loads(data, "ANSI")


# ---------------------------------------------------------- KEYMAP_FN_TEST

# A hand-authored fixture: profile1 has three different fn modifiers and overlay
# mappings on A/S; profile2/3 just have a single fn1 trigger.

@pytest.fixture
def fn_test_keymap():
    return tex_reader.read(FIXTURES / "KEYMAP_FN_TEST.TEX", "ANSI")


def test_fn_test_profile1_fn_triggers(fn_test_keymap):
    g12 = fn_test_keymap.bindings[keyinfo_from_name("G12")]
    end = fn_test_keymap.bindings[keyinfo_from_name("END")]
    pgdn = fn_test_keymap.bindings[keyinfo_from_name("PGDN")]
    assert g12[1].fn_role == 1
    assert end[1].fn_role == 2
    assert pgdn[1].fn_role == 3


def test_fn_test_profile1_a_overlays(fn_test_keymap):
    a = fn_test_keymap.bindings[keyinfo_from_name("A")][1]
    assert a.fn_role is None
    assert a.fn1 == keyaction_from_name("F1")
    assert a.fn2 == keyaction_from_name("F2")
    assert a.fn3 == keyaction_from_name("F3")


def test_fn_test_profile1_s_overlays(fn_test_keymap):
    s = fn_test_keymap.bindings[keyinfo_from_name("S")][1]
    assert s.fn1 == keyaction_from_name("F11")
    assert s.fn2 == keyaction_from_name("F12")
    assert s.fn3 == keyaction_from_name("F13")


def test_fn_test_profile2_only_g12_is_fn(fn_test_keymap):
    # In profiles 2 and 3, only G12 is fn-trigger; END and PGDN are normal keys.
    end_p2 = fn_test_keymap.bindings[keyinfo_from_name("END")][2]
    pgdn_p2 = fn_test_keymap.bindings[keyinfo_from_name("PGDN")][2]
    assert end_p2.fn_role is None
    assert pgdn_p2.fn_role is None
    assert fn_test_keymap.bindings[keyinfo_from_name("G12")][2].fn_role == 1


def test_fn_role_keys_have_no_layer_slots(fn_test_keymap):
    # The invariant: if fn_role is set, layer slots are all None.
    for per_profile in fn_test_keymap.bindings.values():
        for binding in per_profile.values():
            if binding.fn_role is not None:
                assert binding.base is None
                assert binding.fn1 is None
                assert binding.fn2 is None
                assert binding.fn3 is None


# ---------------------------------------------------------- KEYMAP_GABI

def test_gabi_null_fn_position_is_silently_skipped():
    # KEYMAP_GABI's profile 1 fn1 position record is [0xB4, 0x30].
    # 0xB4 is the null sentinel; 0x30 = (6, 0) = G12.
    # The reader should not raise, and only G12 should be fn-role.
    km = tex_reader.read(FIXTURES / "KEYMAP_GABI.TEX", "ANSI")
    fn_keys = [
        (key, pid, b.fn_role)
        for key, per_profile in km.bindings.items()
        for pid, b in per_profile.items()
        if b.fn_role is not None
    ]
    # Three profiles, one fn-trigger (G12) each.
    assert len(fn_keys) == 3
    assert all(key == keyinfo_from_name("G12") and role == 1 for key, _, role in fn_keys)


# ---------------------------------------------------------- KEYMAP_EMPTY

def test_empty_keymap_minimal_bindings():
    km = tex_reader.read(FIXTURES / "KEYMAP_EMPTY.TEX", "ANSI")
    # KEYMAP_EMPTY's profiles have only fn-triggers; no real overlay mappings.
    assert km.macros == {}
    # At least one fn-trigger exists.
    fn_count = sum(
        1 for v in km.bindings.values() for b in v.values() if b.fn_role is not None
    )
    assert fn_count > 0


# ---------------------------------------------------------- macros

def test_keymap_with_macro_has_one_macro():
    km = tex_reader.read(FIXTURES / "KEYMAP_WITH_MACRO.TEX", "ANSI")
    assert list(km.macros.keys()) == ["M1"]
    events = km.macros["M1"]
    assert len(events) > 0
    # Every event has a press or release action and a KeyAction key.
    for e in events:
        assert e.action in ("press", "release")
        assert isinstance(e.key, KeyAction)
        assert e.delay >= 0


def test_macro_binding_appears_in_bindings():
    # KEYMAP_WITH_MACRO has at least one 0x18 entry pointing to slot 0 (M1).
    km = tex_reader.read(FIXTURES / "KEYMAP_WITH_MACRO.TEX", "ANSI")
    macro_slot_actions = [
        (key, pid, layer)
        for key, per_profile in km.bindings.items()
        for pid, b in per_profile.items()
        for layer in ("base", "fn1", "fn2", "fn3")
        if isinstance(getattr(b, layer), MacroAction)
    ]
    assert len(macro_slot_actions) > 0
    # All macro references must resolve in keymap.macros.
    for key, pid, layer in macro_slot_actions:
        mref = getattr(km.bindings[key][pid], layer)
        assert mref.name in km.macros


def test_kletskovg_macros_count():
    # KEYMAP_KLETSKOVG has 3 user-defined macros.
    km = tex_reader.read(FIXTURES / "KEYMAP_KLETSKOVG.TEX", "ANSI")
    assert len(km.macros) == 3


# ---------------------------------------------------------- layout sensitivity

def test_iso_specific_key_resolves_with_iso_layout():
    # KEYMAP_DEFAULT_ISO contains a binding for CODE45 (matrix (3,2), ISO-only).
    km = tex_reader.read(FIXTURES / "KEYMAP_DEFAULT_ISO.TEX", "ISO")
    code45 = keyinfo_from_name("CODE45")
    assert code45 in km.bindings


def test_jis_specific_keys_resolve_with_jis_layout():
    km = tex_reader.read(FIXTURES / "KEYMAP_DEFAULT_JIS.TEX", "JIS")
    for name in ("CODE56", "CODE133", "CODE14", "CODE131"):
        assert keyinfo_from_name(name) in km.bindings


# ---------------------------------------------------------- shape checks

def test_bindings_dict_is_keyinfo_keyed():
    # Outer dict keys are KeyInfo, not raw ints or names.
    km = tex_reader.read(FIXTURES / "KEYMAP_FN_TEST.TEX", "ANSI")
    from shinobi_keymap.models import KeyInfo
    for key in km.bindings:
        assert isinstance(key, KeyInfo)


def test_inner_dict_is_int_profile_id_keyed():
    km = tex_reader.read(FIXTURES / "KEYMAP_FN_TEST.TEX", "ANSI")
    for per_profile in km.bindings.values():
        for pid in per_profile:
            assert isinstance(pid, int)
            assert pid in (1, 2, 3)


def test_layer_slots_are_keyaction_macroaction_or_none():
    km = tex_reader.read(FIXTURES / "KEYMAP_WITH_MACRO.TEX", "ANSI")
    for per_profile in km.bindings.values():
        for binding in per_profile.values():
            for layer in ("base", "fn1", "fn2", "fn3"):
                value = getattr(binding, layer)
                assert value is None or isinstance(value, (KeyAction, MacroAction))
