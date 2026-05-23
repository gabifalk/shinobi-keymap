# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Gabi Falk

"""Tests for the Keymap -> YAML writer."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from shinobi_keymap import yaml_reader
from shinobi_keymap import yaml_writer
from shinobi_keymap.models import (
    KeyBinding,
    Keymap,
    MacroAction,
    MacroEvent,
    keyaction_from_name,
    keyinfo_from_name,
)


FIXTURES_YAML = Path(__file__).parent / "fixtures" / "yaml_expected"


# ---------------------------------------------------------- header & shape

def test_dumps_minimal_keymap():
    # An empty Keymap is "missing" every default key.  Each absent key is
    # emitted as ``NONE`` on base so the round-trip preserves the absence;
    # keys with layer-specific defaults (e.g. ``1``'s fn1 -> TP_SPEED1) also
    # emit ``NONE`` on those layers because NO diverges from the layer default.
    km = Keymap(layout="ANSI")
    text = yaml_writer.dumps(km)
    doc = yaml.safe_load(text)
    assert doc["version"] == 1
    assert doc["layout"] == "ANSI"
    for pid_name in ("profile1", "profile2", "profile3"):
        for layer, entries in doc["profiles"][pid_name].items():
            assert set(entries.values()) == {"NONE"}


def test_compat_tex_padding_emitted_when_true():
    km = Keymap(layout="ANSI", compat_tex_padding=True)
    doc = yaml.safe_load(yaml_writer.dumps(km))
    assert doc["compat"] == {"tex_padding": True}


def test_compat_block_omitted_when_all_defaults():
    km = Keymap(layout="ANSI")
    doc = yaml.safe_load(yaml_writer.dumps(km))
    assert "compat" not in doc


def test_dumps_always_emits_three_profiles():
    km = Keymap(layout="ANSI")
    km.bindings[keyinfo_from_name("A")] = {1: KeyBinding(base=keyaction_from_name("F1"))}
    text = yaml_writer.dumps(km)
    doc = yaml.safe_load(text)
    assert set(doc["profiles"]) == {"profile1", "profile2", "profile3"}
    # Profile 1 has the explicit override plus NONE for the other keys; 2/3
    # are wholly absent from bindings -> NONE on base for every default key.
    assert doc["profiles"]["profile1"]["base"]["A"] == "F1"
    assert set(doc["profiles"]["profile2"]["base"].values()) == {"NONE"}
    assert set(doc["profiles"]["profile3"]["base"].values()) == {"NONE"}


# ---------------------------------------------------------- per-key emission

def test_fn_role_emits_as_fn_keyword_on_base():
    km = Keymap(layout="ANSI")
    # G12: FN1 is the default and would be stripped; use non-default fn-trigger keys.
    km.bindings[keyinfo_from_name("L_CTRL")] = {1: KeyBinding(fn_role=1)}
    km.bindings[keyinfo_from_name("END")] = {1: KeyBinding(fn_role=2)}
    km.bindings[keyinfo_from_name("PGDN")] = {1: KeyBinding(fn_role=3)}
    base = yaml.safe_load(yaml_writer.dumps(km))["profiles"]["profile1"]["base"]
    assert base["L_CTRL"] == "FN1"
    assert base["END"] == "FN2"
    assert base["PGDN"] == "FN3"


def test_layer_slot_emits_as_action_name():
    km = Keymap(layout="ANSI")
    km.bindings[keyinfo_from_name("A")] = {
        1: KeyBinding(
            base=keyaction_from_name("ESC"),
            fn1=keyaction_from_name("F1"),
            fn2=keyaction_from_name("F2"),
        )
    }
    profile1 = yaml.safe_load(yaml_writer.dumps(km))["profiles"]["profile1"]
    assert profile1["base"]["A"] == "ESC"
    assert profile1["fn1"]["A"] == "F1"
    assert profile1["fn2"]["A"] == "F2"
    # fn3 of A is unset -- emitted as NONE so the absence survives round-trip.
    assert profile1["fn3"]["A"] == "NONE"


def test_macro_action_emits_with_m_prefix():
    km = Keymap(layout="ANSI")
    km.macros["copy"] = [MacroEvent("press", keyaction_from_name("A"), 0)]
    km.bindings[keyinfo_from_name("A")] = {1: KeyBinding(base=MacroAction("copy"))}
    base = yaml.safe_load(yaml_writer.dumps(km))["profiles"]["profile1"]["base"]
    assert base["A"] == "M_copy"


def test_no_keycode_emits_as_none():
    km = Keymap(layout="ANSI")
    km.bindings[keyinfo_from_name("G12")] = {1: KeyBinding(base=keyaction_from_name("NO"))}
    base = yaml.safe_load(yaml_writer.dumps(km))["profiles"]["profile1"]["base"]
    assert base["G12"] == "NONE"


def test_bindings_sorted_by_keycode():
    km = Keymap(layout="ANSI")
    # Add in non-keycode order; output should be sorted by keycode.
    km.bindings[keyinfo_from_name("W3FORWARD")] = {1: KeyBinding(base=keyaction_from_name("ESC"))}
    km.bindings[keyinfo_from_name("A")] = {1: KeyBinding(base=keyaction_from_name("ESC"))}
    km.bindings[keyinfo_from_name("PGUP")] = {1: KeyBinding(base=keyaction_from_name("ESC"))}
    text = yaml_writer.dumps(km)
    # Look at the raw lines for "<KEY>: ESC" entries to check order.
    lines = [line.strip() for line in text.splitlines() if ": ESC" in line]
    assert lines == ["A: ESC", "PGUP: ESC", "W3FORWARD: ESC"]


# ---------------------------------------------------------- macro emission

def test_macro_events_with_default_delay_omit_delay_key():
    km = Keymap(layout="ANSI")
    km.macros["m1"] = [MacroEvent("press", keyaction_from_name("A"), 0)]
    # Force the macro to be referenced so it round-trips through any consumer.
    km.bindings[keyinfo_from_name("A")] = {1: KeyBinding(base=MacroAction("m1"))}
    doc = yaml.safe_load(yaml_writer.dumps(km))
    event = doc["macros"]["m1"][0]
    assert event == {"action": "press", "key": "A"}


def test_macro_events_keep_non_zero_delay():
    km = Keymap(layout="ANSI")
    km.macros["m1"] = [MacroEvent("press", keyaction_from_name("A"), 125)]
    doc = yaml.safe_load(yaml_writer.dumps(km))
    event = doc["macros"]["m1"][0]
    assert event == {"action": "press", "key": "A", "delay": 125}


def test_macros_section_omitted_when_empty():
    km = Keymap(layout="ANSI")
    doc = yaml.safe_load(yaml_writer.dumps(km))
    assert "macros" not in doc


# ---------------------------------------------------------- round-trip

@pytest.mark.parametrize("name", [
    "KEYMAP_DEFAULT_ANSI", "KEYMAP_DEFAULT_ISO", "KEYMAP_DEFAULT_JIS",
    "KEYMAP_FN_TEST", "KEYMAP_GABI",
])
def test_round_trip_through_writer_preserves_semantics(name):
    km1 = yaml_reader.read(FIXTURES_YAML / f"{name}.yaml")
    out = yaml_writer.dumps(km1)
    km2 = yaml_reader.loads(out)
    assert km1.layout == km2.layout
    assert km1.bindings == km2.bindings
    assert km1.macros == km2.macros


def test_round_trip_macro_test_fixture():
    src = Path(__file__).parent / "fixtures" / "yaml" / "macro_test.yaml"
    km1 = yaml_reader.read(src)
    out = yaml_writer.dumps(km1)
    km2 = yaml_reader.loads(out)
    assert km1.bindings == km2.bindings
    assert km1.macros == km2.macros


def test_digit_key_round_trips():
    # PyYAML parses unquoted digit keys as ints; the reader normalises to str
    # and the writer should produce something the reader can read back.
    text = (
        "version: 1\n"
        "layout: ANSI\n"
        "profiles:\n"
        "  profile1:\n"
        "    fn1:\n"
        "      1: TP_SPEED1\n"
        "      2: TP_SPEED2\n"
    )
    km1 = yaml_reader.loads(text)
    out = yaml_writer.dumps(km1)
    km2 = yaml_reader.loads(out)
    assert km1.bindings == km2.bindings


def test_self_mapping_is_omitted_as_default():
    km = Keymap(layout="ANSI")
    # A -> A is the default; CAPS_LOCK -> ESC is an override.
    km.bindings[keyinfo_from_name("A")] = {1: KeyBinding(base=keyaction_from_name("A"))}
    km.bindings[keyinfo_from_name("CAPS_LOCK")] = {
        1: KeyBinding(base=keyaction_from_name("ESC")),
    }
    doc = yaml.safe_load(yaml_writer.dumps(km))
    base = doc["profiles"]["profile1"].get("base", {})
    assert "A" not in base
    assert base["CAPS_LOCK"] == "ESC"


def test_dense_keymap_emits_only_overrides():
    from shinobi_keymap.models import fill_defaults
    km = Keymap(layout="ANSI")
    fill_defaults(km)
    # Now add one override.
    km.bindings[keyinfo_from_name("CAPS_LOCK")][1].base = keyaction_from_name("ESC")
    doc = yaml.safe_load(yaml_writer.dumps(km))
    # Every profile slot is non-default in profile1.base, none in 2/3.
    assert doc["profiles"]["profile1"]["base"] == {"CAPS_LOCK": "ESC"}
    assert doc["profiles"]["profile2"] == {}
    assert doc["profiles"]["profile3"] == {}


def test_fn_layer_matching_base_is_omitted():
    # If fn1/fn2/fn3 hold the same value as base for a given key, only base
    # is emitted (the others cascade in on read).
    from shinobi_keymap.models import fill_defaults
    km = Keymap(layout="ANSI")
    pgup = keyinfo_from_name("PGUP")
    km.bindings[pgup] = {1: KeyBinding(base=keyaction_from_name("END"))}
    fill_defaults(km)  # cascade END through fn1/fn2/fn3
    doc = yaml.safe_load(yaml_writer.dumps(km))
    profile1 = doc["profiles"]["profile1"]
    assert profile1["base"] == {"PGUP": "END"}
    assert "fn1" not in profile1
    assert "fn2" not in profile1
    assert "fn3" not in profile1


def test_layer_specific_default_is_omitted_when_matched():
    # ``1`` on fn1 defaults to TP_SPEED1.  If the keymap has that value
    # there, the writer omits it.
    from shinobi_keymap.models import fill_defaults
    km = Keymap(layout="ANSI")
    fill_defaults(km)
    doc = yaml.safe_load(yaml_writer.dumps(km))
    # No overrides anywhere -> every profile body is empty.
    for pid_name in ("profile1", "profile2", "profile3"):
        assert doc["profiles"][pid_name] == {}


def test_demotion_signal_is_emitted_when_all_slots_match_self():
    # Manually demote G12 to all-self mapping.  The writer emits ``G12: G12``
    # on base as the demotion signal.
    km = Keymap(layout="ANSI")
    g12 = keyinfo_from_name("G12")
    km.bindings[g12] = {
        1: KeyBinding(
            base=keyaction_from_name("G12"),
            fn1=keyaction_from_name("G12"),
            fn2=keyaction_from_name("G12"),
            fn3=keyaction_from_name("G12"),
        )
    }
    base = yaml.safe_load(yaml_writer.dumps(km))["profiles"]["profile1"]["base"]
    assert base["G12"] == "G12"


def test_dump_writes_to_disk(tmp_path):
    km = Keymap(layout="ANSI")
    km.bindings[keyinfo_from_name("A")] = {1: KeyBinding(base=keyaction_from_name("F1"))}
    target = tmp_path / "out.yaml"
    yaml_writer.dump(km, target)
    assert target.read_text() == yaml_writer.dumps(km)
