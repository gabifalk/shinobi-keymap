# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Gabi Falk

"""Dump a TEX Shinobi .TEX firmware file as human-readable annotated text.

This is intentionally a separate parser from ``tex_reader``: the dumper walks
the file linearly from byte zero and labels every 8-byte (or 4-byte, inside
a macro block) row -- including paddings and inter-section separators that
the structured reader would skip.  The byte-0 dispatch is:

    0x00  profile pointer  (in the pointer table)
    0x01  macro pointer    (in the pointer table)
    0x02  key binding      (KEY / FN_POS / MACRO_BINDING -- inside profiles)
    0xFF  padding row

Inside a macro block we switch to 4-byte events terminated by the
``00 FC C8 00`` sentinel; the block locations come from the macro pointers
in the pointer table.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, TextIO

from .constants import KEYCODE_TO_MATRIX, KEYCODE_TO_NAME


MAGIC = b"CYFI\x00\x00"
HEADER_SIZE = 8
ENTRY_SIZE = 8
MACRO_EVENT_SIZE = 4

ENTRY_TYPE_PROFILE_TABLE = 0x00
ENTRY_TYPE_MACRO_TABLE = 0x01
ENTRY_TYPE_KEY = 0x02

MARKER_KEY = 0x20
MARKER_FN_MACRO_BINDING = 0x18

FN_LOCATION_MARKERS = {0x94: "fn1", 0x95: "fn2", 0x96: "fn3"}
MACRO_LAYER_CODES = {0x3C: "base", 0x3D: "fn1", 0x3E: "fn2", 0x3F: "fn3"}
LAYER_NAMES = {0: "base", 1: "fn1", 2: "fn2", 3: "fn3"}

MACRO_SENTINEL = b"\x00\xfc\xc8\x00"
MACRO_ACTION_MASK = 0xFC
MACRO_ACTION_PRESS = 0x3C
MACRO_ACTION_RELEASE = 0x5C
MACRO_KEYCODE_EXT_MASK = 0x03

DEFAULT_LAYOUT = "ANSI"


# ---------------------------------------------------- name lookups

def _matrix_by_layout(layout: str) -> dict:
    """matrix index (``hi*8 + lo``) -> default key name on this layout."""
    return {
        hi * 8 + lo: KEYCODE_TO_NAME[kc]
        for kc, (hi, lo) in KEYCODE_TO_MATRIX[layout].items()
    }


def _physical_name(layout: str, key_id: int) -> str:
    # Byte 2 of a 0x20 entry (and byte 4 of a 0x18 entry) is a physical key
    # id (= keycode).  If the key is physical on this layout, render its
    # name; otherwise render KEY_<id> so it's clear it's not a real key on
    # the keyboard being dumped.
    if key_id in KEYCODE_TO_MATRIX[layout]:
        return KEYCODE_TO_NAME[key_id]
    return f"KEY_{key_id}"


def _action_name(kc: int) -> str:
    return KEYCODE_TO_NAME.get(kc, f"KEY_{kc}")


def _layer_name(layer_id: int) -> str:
    return LAYER_NAMES.get(layer_id, f"layer{layer_id}")


# ---------------------------------------------------- formatting helpers

def _magic_repr(magic: bytes) -> str:
    parts = [chr(b) if 32 <= b < 127 else f"\\{b:o}" for b in magic]
    return "'" + "".join(parts) + "'"


def _hex_line(hex_str: str, label: str, width: int = 16) -> str:
    return f"{hex_str:<{width}}  {label}"


# ---------------------------------------------------- pointer table

class _Pointer:
    __slots__ = ("kind", "profile_id", "slot", "offset")

    def __init__(self, kind: int, profile_id: int, slot: int, offset: int) -> None:
        self.kind = kind
        self.profile_id = profile_id
        self.slot = slot
        self.offset = offset


def _parse_pointer(rec: bytes) -> _Pointer:
    return _Pointer(
        kind=rec[0],
        profile_id=rec[1],
        slot=rec[2],
        offset=int.from_bytes(rec[4:8], "little"),
    )


def _pointer_label(ptr: _Pointer) -> str:
    if ptr.kind == ENTRY_TYPE_PROFILE_TABLE:
        return f"PROFILE_PTR id={ptr.profile_id} offset=0x{ptr.offset:04X}"
    if ptr.kind == ENTRY_TYPE_MACRO_TABLE:
        return (
            f"MACRO_PTR profile{ptr.profile_id} "
            f"id=M{ptr.slot + 1}({ptr.slot}) -> 0x{ptr.offset:04X}"
        )
    return f"UNKNOWN_PTR kind=0x{ptr.kind:02x}"


# ---------------------------------------------------- record decoders

def _decode_key_record(rec: bytes, layout: str, matrix: dict) -> str:
    if rec == b"\x00" * ENTRY_SIZE:
        return "SEPARATOR"
    if rec[0] != ENTRY_TYPE_KEY:
        return f"UNKNOWN type=0x{rec[0]:02x} marker=0x{rec[1]:02x}"

    _type, marker, b2, b3, b4, b5, _b6, _b7 = rec

    if marker == MARKER_KEY:
        action = b4 | (b5 << 8)
        return (
            f"KEY {_layer_name(b3)}(0x{b3:02x}): "
            f"key[{_physical_name(layout, b2)}({b2})] -> "
            f"action[{_action_name(action)}({action})]"
        )

    if marker in FN_LOCATION_MARKERS:
        fn = FN_LOCATION_MARKERS[marker]
        count = b2
        positions = list(rec[4:4 + count])
        parts = []
        for p in positions:
            if p in matrix:
                parts.append(f"{matrix[p]}({p // 8},{p % 8})={p}")
            else:
                parts.append(f"NULL({p})")
        return f"FN_POS {fn}(0x{marker:02x}): count={count} [{', '.join(parts)}]"

    if marker == MARKER_FN_MACRO_BINDING:
        fn = MACRO_LAYER_CODES.get(b5, f"0x{b5:02x}")
        return (
            f"MACRO_BINDING {fn}: "
            f"key[{_physical_name(layout, b4)}({b4})] -> "
            f"action[M{b2 + 1}]"
        )

    return f"UNKNOWN type=0x{rec[0]:02x} marker=0x{marker:02x}"


def _decode_macro_event(ev: bytes) -> str:
    if ev == MACRO_SENTINEL:
        return "END"
    keycode_lo, action_byte, delay_lo, delay_hi = ev
    keycode = keycode_lo | ((action_byte & MACRO_KEYCODE_EXT_MASK) << 8)
    delay = delay_lo | (delay_hi << 8)
    action_high = action_byte & MACRO_ACTION_MASK
    if action_high == MACRO_ACTION_PRESS:
        action = "PRESS"
    elif action_high == MACRO_ACTION_RELEASE:
        action = "RELEASE"
    else:
        return f"UNKNOWN action=0x{action_byte:02x}"
    return f"{action} {_action_name(keycode)} delay={delay}ms"


# ---------------------------------------------------- top-level walk

def dump(data: bytes, layout: str = DEFAULT_LAYOUT, with_addresses: bool = False) -> str:
    """Return the dump text for ``data``.

    With ``with_addresses=True`` each row is prefixed with its file offset.
    The ``File:`` / ``Size:`` lines are written by ``dump_hex`` when given a
    file path -- they're not derivable from ``data`` alone.
    """
    layout = layout.upper()
    matrix = _matrix_by_layout(layout)

    if len(data) < HEADER_SIZE:
        raise ValueError(f"file too small for header: {len(data)} bytes")
    if data[:6] != MAGIC:
        raise ValueError(f"bad magic: {data[:6]!r}")
    ptr_count = int.from_bytes(data[6:8], "little")
    if len(data) < HEADER_SIZE + ptr_count * ENTRY_SIZE:
        raise ValueError(
            f"pointer table extends past end of file: "
            f"need {HEADER_SIZE + ptr_count * ENTRY_SIZE} bytes, "
            f"have {len(data)}"
        )

    lines: list = []

    def addr(off: int) -> str:
        return f"0x{off:04X}  " if with_addresses else ""

    # --- Header ---
    lines += ["Header:", "-" * 80]
    lines.append(addr(0) + _hex_line(data[:6].hex(), f"magic={_magic_repr(data[:6])}"))
    lines.append(addr(6) + _hex_line(data[6:8].hex(), f"ptr_entry_count={ptr_count}"))
    lines.append("")

    # --- Pointer table ---
    lines += ["Pointers:", "-" * 80]
    pointers: list = []
    for i in range(ptr_count):
        rec_off = HEADER_SIZE + i * ENTRY_SIZE
        rec = data[rec_off:rec_off + ENTRY_SIZE]
        ptr = _parse_pointer(rec)
        pointers.append(ptr)
        lines.append(addr(rec_off) + _hex_line(rec.hex(), _pointer_label(ptr)))

    # --- Walk the rest of the file linearly ---
    profile_at = {
        p.offset: p for p in pointers if p.kind == ENTRY_TYPE_PROFILE_TABLE
    }
    macro_at = {
        p.offset: p for p in pointers if p.kind == ENTRY_TYPE_MACRO_TABLE
    }

    offset = HEADER_SIZE + ptr_count * ENTRY_SIZE
    current_profile: Optional[int] = None
    current_section: Optional[str] = None

    def begin_section(name: str) -> None:
        nonlocal current_section
        if current_section == name:
            return
        blanks = 2 if current_section in ("Entries", "Macros") else 1
        lines.extend([""] * blanks)
        lines.append(f"{name}:")
        lines.append("-" * 80)
        current_section = name

    while offset + ENTRY_SIZE <= len(data):
        # Macro block start: walk 4-byte events until sentinel or 0xFF run.
        if offset in macro_at:
            mp = macro_at[offset]
            begin_section("Macros")
            ev_offset = offset
            while ev_offset + MACRO_EVENT_SIZE <= len(data):
                ev = data[ev_offset:ev_offset + MACRO_EVENT_SIZE]
                if ev == b"\xff" * MACRO_EVENT_SIZE:
                    break
                lines.append(
                    f"[profile{mp.profile_id}] [M{mp.slot + 1}] "
                    + addr(ev_offset)
                    + _hex_line(ev.hex(), _decode_macro_event(ev), width=8)
                )
                ev_offset += MACRO_EVENT_SIZE
                if ev == MACRO_SENTINEL:
                    break
            offset = ev_offset
            continue

        # A macro slot may start mid-row after a 4-byte padding tail.  Skip
        # the few filler bytes and jump straight to the slot.
        overlap = next(
            (s for s in macro_at if offset < s < offset + ENTRY_SIZE),
            None,
        )
        if overlap is not None:
            offset = overlap
            continue

        rec = data[offset:offset + ENTRY_SIZE]
        if rec == b"\xff" * ENTRY_SIZE:
            begin_section("Padding")
            lines.append(addr(offset) + _hex_line(rec.hex(), "PADDING"))
            offset += ENTRY_SIZE
            continue

        if offset in profile_at:
            new_profile = profile_at[offset].profile_id
            if (
                current_section == "Entries"
                and current_profile is not None
                and current_profile != new_profile
            ):
                lines.append("")
            current_profile = new_profile
        begin_section("Entries")
        lines.append(
            f"[profile{current_profile}] "
            + addr(offset)
            + _hex_line(rec.hex(), _decode_key_record(rec, layout, matrix))
        )
        offset += ENTRY_SIZE

    return "\n".join(lines) + "\n"


def dump_hex(
    path: str | Path,
    layout: str = DEFAULT_LAYOUT,
    no_addresses: bool = False,
    output: Optional[TextIO] = None,
) -> None:
    """Walk a .TEX file and write an annotated hex dump.

    Without ``no_addresses``, prefixes ``File:`` / ``Size:`` lines and offset
    columns on every row (the format used for inspection).  With it, omits
    them so two dumps diff cleanly.
    """
    out = output or sys.stdout
    data = Path(path).read_bytes()
    if not no_addresses:
        out.write(f"File: {path}\n")
        out.write(f"Size: {len(data)} bytes\n\n")
    out.write(dump(data, layout=layout, with_addresses=not no_addresses))
