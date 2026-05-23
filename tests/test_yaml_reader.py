# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Gabi Falk

"""Tests for the YAML -> Keymap reader."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from shinobi_keymap import yaml_reader
from shinobi_keymap.models import (
    KeyAction,
    MacroAction,
    keyaction_from_name,
    keyinfo_from_name,
)


FIXTURES_YAML = Path(__file__).parent / "fixtures" / "yaml_expected"


# ---------------------------------------------------------- header validation

def test_unsupported_version_raises():
    with pytest.raises(ValueError, match="unsupported YAML version"):
        yaml_reader.loads("version: 2\nlayout: ANSI\n")


def test_unsupported_layout_raises():
    with pytest.raises(ValueError, match="unsupported layout"):
        yaml_reader.loads("version: 1\nlayout: DVORAK\n")


def test_invalid_profile_name_raises():
    text = dedent("""\
        version: 1
        layout: ANSI
        profiles:
          banana: {}
    """)
    with pytest.raises(ValueError, match="invalid profile name"):
        yaml_reader.loads(text)


def test_unknown_layer_raises():
    text = dedent("""\
        version: 1
        layout: ANSI
        profiles:
          profile1:
            mystery: {}
    """)
    with pytest.raises(ValueError, match="unknown layer"):
        yaml_reader.loads(text)


# ---------------------------------------------------------- minimal parsing

def test_minimal_keymap_has_defaults_filled_in():
    km = yaml_reader.loads("version: 1\nlayout: ANSI\n")
    assert km.layout == "ANSI"
    assert km.macros == {}
    # Defaults populate every physical key with self-mappings on all 4 layers,
    # across all 3 profiles.
    a = km.bindings[keyinfo_from_name("A")]
    for pid in (1, 2, 3):
        assert a[pid].base == keyaction_from_name("A")
        assert a[pid].fn1 == keyaction_from_name("A")
        assert a[pid].fn2 == keyaction_from_name("A")
        assert a[pid].fn3 == keyaction_from_name("A")


def test_empty_profiles_get_defaults_too():
    text = dedent("""\
        version: 1
        layout: ANSI
        profiles:
          profile1: {}
          profile2: {}
          profile3: {}
    """)
    km = yaml_reader.loads(text)
    # G12 default is fn_role=1; A defaults to self.
    g12 = km.bindings[keyinfo_from_name("G12")]
    for pid in (1, 2, 3):
        assert g12[pid].fn_role == 1
    a = km.bindings[keyinfo_from_name("A")]
    for pid in (1, 2, 3):
        assert a[pid].base == keyaction_from_name("A")


# ---------------------------------------------------------- base-layer mapping

def test_base_layer_keycode_mapping():
    text = dedent("""\
        version: 1
        layout: ANSI
        profiles:
          profile1:
            base:
              CAPS_LOCK: ESC
    """)
    km = yaml_reader.loads(text)
    key = keyinfo_from_name("CAPS_LOCK")
    assert km.bindings[key][1].base == keyaction_from_name("ESC")


def test_none_aliases_to_no():
    text = dedent("""\
        version: 1
        layout: ANSI
        profiles:
          profile1:
            base:
              G12: NONE
    """)
    km = yaml_reader.loads(text)
    binding = km.bindings[keyinfo_from_name("G12")][1]
    assert binding.base == keyaction_from_name("NO")


# ---------------------------------------------------------- fn_role detection

def test_fn1_keycode_on_base_sets_fn_role():
    text = dedent("""\
        version: 1
        layout: ANSI
        profiles:
          profile1:
            base:
              G12: FN1
              END: FN2
              PGDN: FN3
    """)
    km = yaml_reader.loads(text)
    assert km.bindings[keyinfo_from_name("G12")][1].fn_role == 1
    assert km.bindings[keyinfo_from_name("END")][1].fn_role == 2
    assert km.bindings[keyinfo_from_name("PGDN")][1].fn_role == 3


def test_fn_role_clears_layer_slots():
    # Defined fn1 first, then base: FN1 should still wipe the fn1 slot.
    text = dedent("""\
        version: 1
        layout: ANSI
        profiles:
          profile1:
            fn1:
              G12: F1
            base:
              G12: FN1
    """)
    km = yaml_reader.loads(text)
    binding = km.bindings[keyinfo_from_name("G12")][1]
    assert binding.fn_role == 1
    assert binding.base is None
    assert binding.fn1 is None
    assert binding.fn2 is None
    assert binding.fn3 is None


def test_layer_slot_for_fn_role_key_is_ignored():
    # Order reversed: base FN1 first, then fn1 entry for the same key.
    text = dedent("""\
        version: 1
        layout: ANSI
        profiles:
          profile1:
            base:
              G12: FN1
            fn1:
              G12: F1
    """)
    km = yaml_reader.loads(text)
    binding = km.bindings[keyinfo_from_name("G12")][1]
    assert binding.fn_role == 1
    assert binding.fn1 is None


# ---------------------------------------------------------- macros

def test_macro_reference_in_layer():
    text = dedent("""\
        version: 1
        layout: ANSI
        profiles:
          profile1:
            base:
              A: M_copy
        macros:
          copy:
            - action: press
              key: L_CTRL
            - action: press
              key: C
            - action: release
              key: C
            - action: release
              key: L_CTRL
    """)
    km = yaml_reader.loads(text)
    binding = km.bindings[keyinfo_from_name("A")][1]
    assert binding.base == MacroAction("copy")
    assert "copy" in km.macros
    assert len(km.macros["copy"]) == 4
    assert km.macros["copy"][1].action == "press"
    assert km.macros["copy"][1].key == keyaction_from_name("C")
    assert km.macros["copy"][1].delay == 0


def test_macro_event_with_explicit_delay():
    text = dedent("""\
        version: 1
        layout: ANSI
        macros:
          m1:
            - action: press
              key: A
              delay: 100
    """)
    km = yaml_reader.loads(text)
    assert km.macros["m1"][0].delay == 100


def test_macro_event_invalid_action_raises():
    text = dedent("""\
        version: 1
        layout: ANSI
        macros:
          m1:
            - action: bounce
              key: A
    """)
    with pytest.raises(ValueError, match="unknown action"):
        yaml_reader.loads(text)


# ---------------------------------------------------------- rejection of bad input

def test_action_only_keycode_as_key_raises():
    # Try to put an action-only keycode (FN1 = 232) on the *key* side.
    text = dedent("""\
        version: 1
        layout: ANSI
        profiles:
          profile1:
            base:
              FN1: ESC
    """)
    with pytest.raises(ValueError, match="not a physical key"):
        yaml_reader.loads(text)


def test_non_string_action_raises():
    text = dedent("""\
        version: 1
        layout: ANSI
        profiles:
          profile1:
            base:
              A: 42
    """)
    with pytest.raises(ValueError, match="must be a string"):
        yaml_reader.loads(text)


# ---------------------------------------------------------- fixture round-trip

@pytest.mark.parametrize("name", [
    "KEYMAP_DEFAULT_ANSI", "KEYMAP_DEFAULT_ISO", "KEYMAP_DEFAULT_JIS",
    "KEYMAP_FN_TEST", "KEYMAP_GABI",
])
def test_every_yaml_fixture_parses(name):
    path = FIXTURES_YAML / f"{name}.yaml"
    km = yaml_reader.read(path)
    assert km.layout in ("ANSI", "ISO", "JIS")
    assert isinstance(km.bindings, dict)


def test_fn_test_fixture_semantics():
    km = yaml_reader.read(FIXTURES_YAML / "KEYMAP_FN_TEST.yaml")
    # Profile 1: G12 is FN1, END is FN2, PGDN is FN3.
    assert km.bindings[keyinfo_from_name("G12")][1].fn_role == 1
    assert km.bindings[keyinfo_from_name("END")][1].fn_role == 2
    assert km.bindings[keyinfo_from_name("PGDN")][1].fn_role == 3
    # Profile 1 overlays on A and S.
    a = km.bindings[keyinfo_from_name("A")][1]
    assert a.fn1 == keyaction_from_name("F1")
    assert a.fn2 == keyaction_from_name("F2")
    assert a.fn3 == keyaction_from_name("F3")
    # Profile 2 and 3 only have G12 as fn-trigger.
    assert km.bindings[keyinfo_from_name("G12")][2].fn_role == 1
    assert km.bindings[keyinfo_from_name("G12")][3].fn_role == 1


def test_macro_test_fixture():
    km = yaml_reader.read(Path(__file__).parent / "fixtures" / "yaml" / "macro_test.yaml")
    assert km.layout == "ANSI"
    assert list(km.macros.keys()) == ["test"]
    a = km.bindings[keyinfo_from_name("A")][1]
    assert a.base == MacroAction("test")


def test_compat_tex_padding_round_trips_through_yaml():
    text = dedent("""\
        version: 1
        layout: ANSI
        compat:
          tex_padding: true
        profiles:
          profile1: {}
          profile2: {}
          profile3: {}
    """)
    km = yaml_reader.loads(text)
    assert km.compat_tex_padding is True


def test_compat_tex_padding_defaults_false_when_absent():
    text = dedent("""\
        version: 1
        layout: ANSI
        profiles:
          profile1: {}
    """)
    km = yaml_reader.loads(text)
    assert km.compat_tex_padding is False


def test_website_compat_is_ignored_silently():
    # Stock-emitted YAML has a website_compat block; we don't parse it yet,
    # but it shouldn't cause the reader to fail.
    text = dedent("""\
        version: 1
        layout: ANSI
        website_compat:
          tex_padding: true
          fn_order:
            profile1:
              fn1: [L_CTRL]
        profiles:
          profile1:
            base:
              L_CTRL: FN1
    """)
    km = yaml_reader.loads(text)
    assert km.bindings[keyinfo_from_name("L_CTRL")][1].fn_role == 1
