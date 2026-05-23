# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Gabi Falk

"""Tests for the .TEX dumper."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from shinobi_keymap import tex_dump


FIXTURES_TEX = Path(__file__).parent / "fixtures" / "tex_files"
FIXTURES_DUMP = Path(__file__).parent / "fixtures" / "dump_expected"


def _layout_for(name: str) -> str:
    if name.endswith("_ISO"):
        return "ISO"
    if name.endswith("_JIS"):
        return "JIS"
    return "ANSI"


_FIXTURE_BASES = [
    "KEYMAP",
    "KEYMAP_DEFAULT_ANSI",
    "KEYMAP_DEFAULT_ISO",
    "KEYMAP_DEFAULT_JIS",
    "KEYMAP_EMPTY",
    "KEYMAP_GABI",
    "KEYMAP_KLETSKOVG",
    "KEYMAP_WEB_COMPLEX",
    "KEYMAP_WEB_WITH_MACROS",
]


# ---------------------------------------------------------- header validation

def test_bad_magic_raises():
    with pytest.raises(ValueError, match="bad magic"):
        tex_dump.dump(b"NOPE\x00\x00\x00\x00", layout="ANSI")


def test_too_small_raises():
    with pytest.raises(ValueError, match="too small"):
        tex_dump.dump(b"CYFI\x00", layout="ANSI")


def test_truncated_pointer_table_raises():
    # Header claims 5 sections but file only has room for the header itself.
    bad = b"CYFI\x00\x00\x05\x00"
    with pytest.raises(ValueError, match="extends past end"):
        tex_dump.dump(bad, layout="ANSI")


# ---------------------------------------------------------- fixture round-trip

@pytest.mark.parametrize("name", _FIXTURE_BASES)
def test_dump_matches_fixture(name):
    layout = _layout_for(name)
    data = (FIXTURES_TEX / f"{name}.TEX").read_bytes()
    got = tex_dump.dump(data, layout=layout)
    expected = (FIXTURES_DUMP / f"{name}.txt").read_text()
    assert got == expected


@pytest.mark.parametrize("name", _FIXTURE_BASES)
def test_dump_hex_with_addresses_matches_fixture(name):
    layout = _layout_for(name)
    # The fixtures record paths relative to the repo root.
    tex_path = Path(f"tests/fixtures/tex_files/{name}.TEX")
    buf = io.StringIO()
    tex_dump.dump_hex(tex_path, layout=layout, output=buf)
    expected = (FIXTURES_DUMP / f"{name}_with_addresses.txt").read_text()
    assert buf.getvalue() == expected


# ---------------------------------------------------------- shape checks

def test_dump_includes_header_section():
    data = (FIXTURES_TEX / "KEYMAP_EMPTY.TEX").read_bytes()
    out = tex_dump.dump(data, layout="ANSI")
    assert out.startswith("Header:\n")
    assert "Pointers:" in out
    assert "Entries:" in out
    assert "Padding:" in out


def test_dump_with_addresses_prefixes_offsets():
    data = (FIXTURES_TEX / "KEYMAP_EMPTY.TEX").read_bytes()
    out = tex_dump.dump(data, layout="ANSI", with_addresses=True)
    # The very first hex row should carry "0x0000" as its offset prefix.
    assert "0x0000  4359464900" in out


def test_dump_hex_writes_file_size_header(tmp_path):
    src = FIXTURES_TEX / "KEYMAP_EMPTY.TEX"
    buf = io.StringIO()
    tex_dump.dump_hex(src, layout="ANSI", output=buf)
    text = buf.getvalue()
    assert "File:" in text
    assert f"Size: {src.stat().st_size} bytes" in text


def test_dump_hex_diffable_omits_file_size():
    buf = io.StringIO()
    tex_dump.dump_hex(
        FIXTURES_TEX / "KEYMAP_EMPTY.TEX",
        layout="ANSI",
        no_addresses=True,
        output=buf,
    )
    text = buf.getvalue()
    assert "File:" not in text
    assert "Size:" not in text
    # And no offset column on data rows.
    assert "0x0000" not in text


# ---------------------------------------------------------- macro decoding

def test_macro_block_emits_press_release_events():
    data = (FIXTURES_TEX / "KEYMAP_WITH_MACRO.TEX").read_bytes()
    out = tex_dump.dump(data, layout="ANSI")
    assert "[M1]" in out
    # The macro section closes with the END sentinel.
    assert "END" in out
    # And contains PRESS/RELEASE events.
    assert "PRESS" in out or "RELEASE" in out


# ---------------------------------------------------------- layout sensitivity

def test_iso_dump_renders_code45_name():
    out = tex_dump.dump(
        (FIXTURES_TEX / "KEYMAP_DEFAULT_ISO.TEX").read_bytes(),
        layout="ISO",
    )
    assert "CODE45" in out


def test_iso_dump_renders_unknown_key_as_KEY_id():
    # CODE56 is JIS-only; rendering an ISO file with layout=ISO never sees
    # CODE56 anyway, but if it did, the dumper would render it as KEY_135.
    # Use a file with a key not on the layout: KEYMAP_DEFAULT_JIS dumped as
    # ANSI -- 135 (CODE56) appears as KEY_135.
    out = tex_dump.dump(
        (FIXTURES_TEX / "KEYMAP_DEFAULT_JIS.TEX").read_bytes(),
        layout="ANSI",
    )
    assert "KEY_135" in out
