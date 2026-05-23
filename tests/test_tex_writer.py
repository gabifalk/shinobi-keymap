# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Gabi Falk

"""Tests for the Keymap -> .TEX writer."""

from __future__ import annotations

from pathlib import Path

import pytest

from shinobi_keymap import tex_reader
from shinobi_keymap import tex_writer
from shinobi_keymap import yaml_reader
from shinobi_keymap import yaml_writer
from shinobi_keymap.models import (
    KeyBinding,
    Keymap,
    MacroAction,
    MacroEvent,
    fill_defaults,
    keyaction_from_name,
    keyinfo_from_name,
)


FIXTURES = Path(__file__).parent / "fixtures" / "tex_files"

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


def _keymaps_equal(a: Keymap, b: Keymap) -> bool:
    return a.layout == b.layout and a.bindings == b.bindings and a.macros == b.macros


# ----------------------------------------------------------- header invariants

def test_dumps_starts_with_magic():
    km = Keymap(layout="ANSI")
    out = tex_writer.dumps(km)
    assert out[:6] == b"CYFI\x00\x00"


def test_dumps_empty_keymap_has_three_profile_descriptors():
    km = Keymap(layout="ANSI")
    out = tex_writer.dumps(km)
    section_count = int.from_bytes(out[6:8], "little")
    assert section_count == 3
    # All descriptors should be profiles (kind=0x00) with ids 1, 2, 3.
    for i, expected_id in enumerate((1, 2, 3)):
        base = 8 + i * 8
        assert out[base] == 0x00
        assert out[base + 1] == expected_id


def test_dumps_minimum_size():
    # Empty keymap: clean ``max(8192, 8N)`` rule pads the 56-byte body
    # (header + 3 descriptors + 3 empty profiles) up to the 8 KB minimum.
    km = Keymap(layout="ANSI")
    out = tex_writer.dumps(km)
    assert len(out) == 8192
    assert out[:8 + 24 + 24] != b"\xff" * (8 + 24 + 24)  # structure preserved
    assert out.endswith(b"\xff" * 8)  # trailing 0xff padding


# --------------------------------------------------- round-trip every fixture

@pytest.mark.parametrize("name,layout", ALL_FIXTURES)
def test_round_trip_preserves_semantics(name, layout):
    km1 = tex_reader.read(FIXTURES / f"{name}.TEX", layout)
    raw = tex_writer.dumps(km1)
    km2 = tex_reader.loads(raw, layout)
    assert _keymaps_equal(km1, km2)


# Fixtures known to byte-equal round-trip after the compat_fn_ghost +
# compat_tex_padding + compat_touched fixes.  Other fixtures still need
# null_fn_positions handling or have ordering quirks; see the audit in
# the commit message.
BYTE_EQUAL_FIXTURES = [
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


@pytest.mark.parametrize("name,layout", BYTE_EQUAL_FIXTURES)
def test_round_trip_is_byte_equal(name, layout):
    src = (FIXTURES / f"{name}.TEX").read_bytes()
    km = tex_reader.read(FIXTURES / f"{name}.TEX", layout)
    assert tex_writer.dumps(km) == src


@pytest.mark.parametrize("name,layout", BYTE_EQUAL_FIXTURES)
def test_yaml_round_trip_is_byte_equal(name, layout):
    src = (FIXTURES / f"{name}.TEX").read_bytes()
    km1 = tex_reader.read(FIXTURES / f"{name}.TEX", layout)
    yaml_text = yaml_writer.dumps(km1)
    km2 = yaml_reader.loads(yaml_text)
    assert tex_writer.dumps(km2) == src


# ---------------------------------------------------------- output invariants

@pytest.mark.parametrize("name,layout", ALL_FIXTURES)
def test_output_is_8_byte_aligned(name, layout):
    km = tex_reader.read(FIXTURES / f"{name}.TEX", layout)
    assert len(tex_writer.dumps(km)) % 8 == 0


def test_synthetic_keymap_output_is_8_byte_aligned():
    # Fresh Keymap with one binding -- exercises the non-fixture path.
    km = Keymap(layout="ANSI")
    km.bindings[keyinfo_from_name("A")] = {1: KeyBinding(base=keyaction_from_name("F1"))}
    assert len(tex_writer.dumps(km)) % 8 == 0


def test_padding_bytes_are_all_0xff():
    # KEYMAP_DEFAULT_ANSI pads up; the bytes past the meaningful data
    # should all be 0xFF.
    km = tex_reader.read(FIXTURES / "KEYMAP_DEFAULT_ANSI.TEX", "ANSI")
    out = tex_writer.dumps(km)
    # Walk backwards while bytes are 0xFF; expect a substantial tail.
    tail = 0
    while tail < len(out) and out[-(tail + 1)] == 0xFF:
        tail += 1
    assert tail > 1000  # KEYMAP_DEFAULT_ANSI pads from ~9.2 KB up to 12792


def test_fresh_keymap_compat_tex_padding_is_false():
    # tex_reader sets compat_tex_padding=True for any TEX input; a fresh
    # Keymap defaults to False (clean formula).
    assert Keymap(layout="ANSI").compat_tex_padding is False


# -------------------------------------------------------- hand-built fixtures

def test_tex_padding_round_trips_keymap_empty_byte_equal():
    # KEYMAP_EMPTY has no profile content and no macros, so the only
    # source of size mismatch was TEX's web configurator's 0xFF trail-padding.
    # With compat_tex_padding the round-trip is byte-for-byte.
    src = (FIXTURES / "KEYMAP_EMPTY.TEX").read_bytes()
    km = tex_reader.read(FIXTURES / "KEYMAP_EMPTY.TEX", "ANSI")
    assert km.compat_tex_padding is True
    out = tex_writer.dumps(km)
    assert out == src


def test_tex_padding_disabled_uses_clean_8kb_minimum():
    # Without compat_tex_padding, the writer uses the clean ``max(8192, 8N)``
    # rule instead of the buggy formula in TEX's web configurator.  KEYMAP_EMPTY's
    # entry data is tiny, so it pads up to the 8 KB minimum.
    km = tex_reader.read(FIXTURES / "KEYMAP_EMPTY.TEX", "ANSI")
    km.compat_tex_padding = False
    out = tex_writer.dumps(km)
    assert len(out) == 8192


def test_compat_touched_round_trips_byte_equal_through_writer():
    # KEYMAP_TOUCHED has a 17-entry fn1 priority block (TEX's web
    # configurator's template defaults), an empty fn2 priority block, and
    # a 4-entry fn3 priority block (A, D, F, S).  Reading then writing
    # should reproduce the binary up to the first "ineffective fn-trigger
    # entry" at byte position 87 -- where TEX's web configurator emits a
    # 0x20 row for each fn-trigger key on every layer, an unrelated compat
    # gap we don't handle yet.
    src = (FIXTURES / "KEYMAP_TOUCHED.TEX").read_bytes()
    km = tex_reader.read(FIXTURES / "KEYMAP_TOUCHED.TEX", "ANSI")

    assert km.compat_touched[(1, 1)] == {
        30, 31, 32, 33, 34, 35, 36, 37, 38, 41, 79, 80, 81, 82, 244, 245, 246,
    }
    assert (1, 2) not in km.compat_touched  # fn2 untouched
    assert km.compat_touched[(1, 3)] == {4, 7, 9, 22}  # A, D, F, S

    out = tex_writer.dumps(km)

    # Walk the first 87 profile1 entries; they must match byte-for-byte.
    p1_off = int.from_bytes(src[12:16], "little")
    out_p1_off = int.from_bytes(out[12:16], "little")
    for i in range(87):
        s = src[p1_off + i * 8: p1_off + (i + 1) * 8]
        o = out[out_p1_off + i * 8: out_p1_off + (i + 1) * 8]
        assert s == o, f"entry {i}: src={s.hex()} out={o.hex()}"


def test_layers_emitted_in_compat_order():
    # TEX's web configurator orders profile-section entries layer-major:
    # all fn1 entries first, then fn2, then fn3, then base.
    km = Keymap(layout="ANSI")
    fill_defaults(km)
    # Override one key on each layer of profile 1.
    a = keyinfo_from_name("A")
    km.bindings[a][1] = KeyBinding(
        base=keyaction_from_name("F1"),
        fn1=keyaction_from_name("F2"),
        fn2=keyaction_from_name("F3"),
        fn3=keyaction_from_name("F4"),
    )
    out = tex_writer.dumps(km)
    # Profile 1's first entry is in profile1_offset; walk and record layer ids.
    p1_off = int.from_bytes(out[12:16], "little")
    seen_layer_ids: list[int] = []
    pos = p1_off
    while out[pos] == 0x02:
        if out[pos + 1] == 0x20:
            seen_layer_ids.append(out[pos + 3])
        pos += 8
        if len(seen_layer_ids) > 400:
            break
    # The first transition tells us the layer order: 1, 2, 3, 0.
    transitions = []
    for layer_id in seen_layer_ids:
        if not transitions or transitions[-1] != layer_id:
            transitions.append(layer_id)
    assert transitions == [1, 2, 3, 0]


def test_normal_key_entry_byte_layout():
    # CAPS_LOCK -> ESC on base layer of profile 1.
    km = Keymap(layout="ANSI")
    km.bindings[keyinfo_from_name("CAPS_LOCK")] = {1: KeyBinding(base=keyaction_from_name("ESC"))}
    out = tex_writer.dumps(km)

    # Profile 1 descriptor's offset:
    p1_off = int.from_bytes(out[12:16], "little")
    entry = out[p1_off:p1_off + 8]
    # type=0x02, marker=0x20, key=CAPS_LOCK (57), layer=0, kc=ESC (41), reserved 0
    assert entry == bytes([0x02, 0x20, 57, 0, 41, 0, 0, 0])


def test_fn_role_emits_position_record_not_normal_entry():
    km = Keymap(layout="ANSI")
    km.bindings[keyinfo_from_name("G12")] = {1: KeyBinding(fn_role=1)}
    out = tex_writer.dumps(km)

    p1_off = int.from_bytes(out[12:16], "little")
    # First (and only) entry: an 0x94 fn1-position record with G12's matrix index.
    entry = out[p1_off:p1_off + 8]
    assert entry[0] == 0x02 and entry[1] == 0x94
    count = int.from_bytes(entry[2:4], "little")
    assert count == 1
    # G12 is at matrix (6, 0) -> idx = 48.
    assert entry[4] == 48
    assert entry[5:8] == b"\xff\xff\xff"


def test_profile_section_ends_with_zero_row():
    km = Keymap(layout="ANSI")
    km.bindings[keyinfo_from_name("A")] = {1: KeyBinding(base=keyaction_from_name("F1"))}
    out = tex_writer.dumps(km)

    p2_off = int.from_bytes(out[20:24], "little")
    # The 8 bytes immediately before profile 2 must be the terminator zeros.
    assert out[p2_off - 8:p2_off] == b"\x00" * 8


def test_macro_section_has_correct_size_and_sentinel():
    km = Keymap(layout="ANSI")
    km.macros["M1"] = [
        MacroEvent("press", keyaction_from_name("L_CTRL"), 0),
        MacroEvent("press", keyaction_from_name("C"), 50),
        MacroEvent("release", keyaction_from_name("C"), 0),
        MacroEvent("release", keyaction_from_name("L_CTRL"), 0),
    ]
    out = tex_writer.dumps(km)

    # 3 profiles + 3 macro descriptors (one M1 emitted per profile).
    section_count = int.from_bytes(out[6:8], "little")
    assert section_count == 6

    # The first macro descriptor is at index 3.
    macro_desc_base = 8 + 3 * 8
    assert out[macro_desc_base] == 0x01
    assert out[macro_desc_base + 1] == 1
    assert int.from_bytes(out[macro_desc_base + 2:macro_desc_base + 4], "little") == 0

    macro_off = int.from_bytes(out[macro_desc_base + 4:macro_desc_base + 8], "little")
    macro_section = out[macro_off:macro_off + tex_writer.MACRO_SECTION_SIZE]
    assert len(macro_section) == tex_writer.MACRO_SECTION_SIZE

    # First event: L_CTRL (224) press, delay 0.
    assert macro_section[:4] == bytes([0xE0, 0x3C, 0x00, 0x00])
    # Second event: C (6) press, delay 50.
    assert macro_section[4:8] == bytes([0x06, 0x3C, 0x32, 0x00])
    # Sentinel after 4*4 = 16 bytes of events.
    assert macro_section[16:20] == tex_writer.MACRO_SENTINEL
    assert all(b == 0xFF for b in macro_section[20:])


def test_every_macro_emitted_once_per_profile():
    km = Keymap(layout="ANSI")
    km.macros["M1"] = [MacroEvent("press", keyaction_from_name("A"), 0)]
    km.macros["M2"] = [MacroEvent("press", keyaction_from_name("B"), 0)]
    # Bindings don't change the emission: every macro is emitted per profile.
    km.bindings[keyinfo_from_name("A")] = {1: KeyBinding(base=MacroAction("M1"))}
    out = tex_writer.dumps(km)

    section_count = int.from_bytes(out[6:8], "little")
    assert section_count == 3 + 3 * 2  # 3 profiles + 3 profiles * 2 macros

    descs = []
    for i in range(3, 3 + 6):
        base = 8 + i * 8
        assert out[base] == 0x01
        pid = out[base + 1]
        slot = int.from_bytes(out[base + 2:base + 4], "little")
        descs.append((pid, slot))
    assert descs == [(1, 0), (1, 1), (2, 0), (2, 1), (3, 0), (3, 1)]


def test_macro_binding_emits_0x18_entry():
    km = Keymap(layout="ANSI")
    km.macros["M1"] = [MacroEvent("press", keyaction_from_name("A"), 0)]
    km.bindings[keyinfo_from_name("B")] = {1: KeyBinding(base=MacroAction("M1"))}
    out = tex_writer.dumps(km)

    # type=0x02, marker=0x18, macro_slot=0, key=B (5), layer_marker=0x3C (base), reserved 0x0001.
    expected = bytes([0x02, 0x18, 0, 0, 5, 0x3C, 0x01, 0x00])
    p1_off = int.from_bytes(out[12:16], "little")
    # Base-macro keys emit a NO ghost row on fn1/fn2/fn3 before the base
    # macro binding, so the 0x18 entry isn't necessarily at offset 0.
    assert expected in out[p1_off:p1_off + 64]


def test_action_keycode_extended_in_macro():
    # BAD_ESC (397 = 0x18D) requires 9-bit encoding: low byte 0x8D, hi bit 0x01.
    km = Keymap(layout="ANSI")
    km.macros["M1"] = [MacroEvent("press", keyaction_from_name("BAD_ESC"), 0)]
    km.bindings[keyinfo_from_name("A")] = {1: KeyBinding(base=MacroAction("M1"))}
    out = tex_writer.dumps(km)

    macro_off = int.from_bytes(out[8 + 3 * 8 + 4:8 + 3 * 8 + 8], "little")
    event = out[macro_off:macro_off + 4]
    # 0x8D = 141 low byte, 0x3D = 0x3C | 0x01 (press + keycode bit 8).
    assert event == bytes([0x8D, 0x3D, 0x00, 0x00])


# -------------------------------------------------------------- error paths

def test_too_many_macros_raises():
    km = Keymap(layout="ANSI")
    keys = "ABCDEFGHIJKLM"  # 13 physical keys
    for i, key_name in enumerate(keys):
        name = f"M{i + 1}"
        km.macros[name] = [MacroEvent("press", keyaction_from_name("A"), 0)]
        km.bindings[keyinfo_from_name(key_name)] = {1: KeyBinding(base=MacroAction(name))}
    with pytest.raises(ValueError, match="too many macros"):
        tex_writer.dumps(km)


def test_too_many_fn_trigger_keys_raises():
    km = Keymap(layout="ANSI")
    for name in ("G9", "G10", "G11", "G12", "L_CTRL"):
        km.bindings[keyinfo_from_name(name)] = {1: KeyBinding(fn_role=1)}
    with pytest.raises(ValueError, match="slots; max is 4"):
        tex_writer.dumps(km)


def test_dump_writes_to_disk(tmp_path):
    km = Keymap(layout="ANSI")
    km.bindings[keyinfo_from_name("A")] = {1: KeyBinding(base=keyaction_from_name("F1"))}
    target = tmp_path / "out.TEX"
    tex_writer.dump(km, target)
    assert target.read_bytes() == tex_writer.dumps(km)
