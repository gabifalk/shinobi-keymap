# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Gabi Falk

"""Read .TEX keymap binary files into Keymap instances.

See ``docs/TEX_FORMAT.md`` for the binary format.
"""

from __future__ import annotations

from pathlib import Path

from .models import (
    KeyAction,
    KeyBinding,
    KeyInfo,
    Keymap,
    MacroAction,
    MacroEvent,
    keyaction_from_id,
    keyinfo_from_id,
    keyinfo_from_phys,
)


MAGIC = b"CYFI\x00\x00"
MACRO_SENTINEL = b"\x00\xfc\xc8\x00"
MACRO_PADDING_WORD = b"\xff\xff\xff\xff"

# Profile-section footer markers (one per fn layer with bindings).
_FN_MARKERS = {0x94: 1, 0x95: 2, 0x96: 3}

# Sentinel byte TEX's web configurator writes into an fn-position slot when the slot
# is counted but has no key behind it.  Round-trips through the YAML
# ``null_fn_positions`` compat field.
FN_NULL_POSITION = 0xB4


def read(path: str | Path, layout: str) -> Keymap:
    """Read a .TEX keymap file into a Keymap."""
    return loads(Path(path).read_bytes(), layout)


def loads(data: bytes, layout: str) -> Keymap:
    """Parse .TEX binary data into a Keymap."""
    if data[:6] != MAGIC:
        raise ValueError("not a TEX file: bad magic")
    section_count = int.from_bytes(data[6:8], "little")

    keymap = Keymap(layout=layout)
    natural_end = 8 + section_count * 8
    for i in range(section_count):
        base = 8 + i * 8
        kind = data[base]
        ident = data[base + 1]
        slot = int.from_bytes(data[base + 2:base + 4], "little")
        offset = int.from_bytes(data[base + 4:base + 8], "little")

        if kind == 0x00:
            section_end = _read_profile(keymap, ident, data, offset, layout)
        elif kind == 0x01:
            _read_macro(keymap, slot, data, offset)
            section_end = offset + 0x280
        else:
            raise ValueError(f"unknown section kind 0x{kind:02X} at descriptor {i}")
        if section_end > natural_end:
            natural_end = section_end

    # Files emitted by TEX's web configurator pad up (or truncate down) past the natural
    # data end; files saved without that step land exactly at natural_end.
    keymap.compat_tex_padding = len(data) != natural_end
    return keymap


def _read_profile(keymap: Keymap, profile_id: int, data: bytes, offset: int, layout: str) -> int:
    """Walk 8-byte entries starting at ``offset`` until an all-zero row.

    Profile sections end with a zero-filled 8-byte row: after the last entry
    (which is the last fn-position record, if any) the bytes up to the next
    section descriptor are zero-filled.

    While walking, watch each fn layer for its priority block: entries before
    the first keycode descent on that layer are "touched" by the user in the
    TEX's web configurator UI and end up in ``keymap.compat_touched[(profile_id, layer_id)]``.

    Returns the position immediately after the terminator (i.e. the natural
    end of the section in the file), used by the caller to detect padding.
    """
    pos = offset
    # Per fn layer (1, 2, 3): (last keycode seen, still inside the priority block)
    last_kc: dict[int, int] = {1: -1, 2: -1, 3: -1}
    in_priority: dict[int, bool] = {1: True, 2: True, 3: True}

    while pos + 8 <= len(data):
        entry = data[pos:pos + 8]
        if entry == b"\x00" * 8:
            break  # section ended -- zero-filled row
        if entry[0] != 0x02:
            raise ValueError(f"bad entry type 0x{entry[0]:02X} at {pos:#x}")

        marker = entry[1]
        if marker == 0x20:
            _record_priority(keymap, profile_id, entry[3], entry[2], last_kc, in_priority)
            _apply_normal_entry(keymap, profile_id, entry)
        elif marker == 0x18:
            _record_priority(
                keymap, profile_id, entry[5] - 0x3C, entry[4], last_kc, in_priority,
            )
            _apply_macro_binding(keymap, profile_id, entry)
        elif marker in _FN_MARKERS:
            _apply_fn_position(keymap, profile_id, entry, layout, _FN_MARKERS[marker])
        else:
            raise ValueError(f"unknown marker 0x{marker:02X} at {pos:#x}")
        pos += 8

    # If a layer's entries were entirely in keycode order, we never saw the
    # descent that marks the priority/tail boundary -- the binary is genuinely
    # ambiguous between "everything is touched" and "nothing is touched."
    # Default to the more common case: nothing touched.
    for layer_id in (1, 2, 3):
        if in_priority[layer_id]:
            keymap.compat_touched.pop((profile_id, layer_id), None)

    return pos + 8  # past the terminator


def _record_priority(
    keymap: Keymap,
    profile_id: int,
    layer_id: int,
    keycode: int,
    last_kc: dict,
    in_priority: dict,
) -> None:
    """Track per-(profile, fn-layer) priority-block membership.

    Called once per ``0x20``/``0x18`` entry as we walk a profile section in
    file order.  As long as keycodes on a given fn layer are strictly
    ascending, we're inside its priority block; the first keycode descent
    flips us out of it.
    """
    if layer_id not in (1, 2, 3) or not in_priority[layer_id]:
        return
    if keycode < last_kc[layer_id]:
        in_priority[layer_id] = False
        return
    keymap.compat_touched.setdefault((profile_id, layer_id), set()).add(keycode)
    last_kc[layer_id] = keycode


def _apply_normal_entry(keymap: Keymap, profile_id: int, entry: bytes) -> None:
    key_keycode = entry[2]
    layer_id = entry[3]
    action_keycode = int.from_bytes(entry[4:6], "little")

    if action_keycode == 0:
        # TEX's web configurator ghost: an "action = NO" row on fn1/fn2/fn3 paired with
        # a base-layer macro binding for the same key.  The firmware ignores
        # these; tex_writer re-derives them from the base macro on emit.
        return

    key = keyinfo_from_id(key_keycode)
    binding = _get_binding(keymap, key, profile_id)
    if binding.fn_role is not None:
        return

    _set_slot(binding, layer_id, keyaction_from_id(action_keycode))


def _apply_macro_binding(keymap: Keymap, profile_id: int, entry: bytes) -> None:
    macro_slot = int.from_bytes(entry[2:4], "little")
    key_keycode = entry[4]
    layer_marker = entry[5]
    layer_id = layer_marker - 0x3C
    if not 0 <= layer_id <= 3:
        raise ValueError(f"bad layer marker 0x{layer_marker:02X}")

    key = keyinfo_from_id(key_keycode)
    binding = _get_binding(keymap, key, profile_id)
    if binding.fn_role is not None:
        return

    _set_slot(binding, layer_id, MacroAction(f"M{macro_slot + 1}"))


def _apply_fn_position(
    keymap: Keymap, profile_id: int, entry: bytes, layout: str, fn_role: int
) -> None:
    """Position records encode fn-trigger key positions as ``hi * 8 + lo`` bytes.

    Within the first ``count`` slots, a slot may hold either a real matrix index
    or the ``FN_NULL_POSITION`` sentinel.
    """
    count = int.from_bytes(entry[2:4], "little")
    slot_list: list[int | None] = []
    for i in range(count):
        idx = entry[4 + i]
        if idx == FN_NULL_POSITION:
            slot_list.append(None)
            continue
        slot_list.append(idx)
        key = keyinfo_from_phys(layout, idx // 8, idx % 8)
        binding = _get_binding(keymap, key, profile_id)
        # Any 0x20/0x18 entries we already absorbed into this binding are the
        # "ghost" actions TEX's web configurator emits for this fn-trigger -- the firmware
        # ignores them, but we need to reproduce them on write.
        if (binding.base is not None or binding.fn1 is not None
                or binding.fn2 is not None or binding.fn3 is not None):
            keymap.compat_fn_ghost[(profile_id, key.keycode)] = KeyBinding(
                base=binding.base, fn1=binding.fn1,
                fn2=binding.fn2, fn3=binding.fn3,
            )
        binding.fn_role = fn_role
        binding.base = None
        binding.fn1 = None
        binding.fn2 = None
        binding.fn3 = None
    keymap.compat_fn_position_slots[(profile_id, fn_role)] = slot_list


def _get_binding(keymap: Keymap, key: KeyInfo, profile_id: int) -> KeyBinding:
    per_profile = keymap.bindings.setdefault(key, {})
    binding = per_profile.get(profile_id)
    if binding is None:
        binding = KeyBinding()
        per_profile[profile_id] = binding
    return binding


def _set_slot(binding: KeyBinding, layer_id: int, value: KeyAction | MacroAction) -> None:
    if layer_id == 0:
        binding.base = value
    elif layer_id == 1:
        binding.fn1 = value
    elif layer_id == 2:
        binding.fn2 = value
    elif layer_id == 3:
        binding.fn3 = value
    else:
        raise ValueError(f"layer id {layer_id} out of range")


def _read_macro(keymap: Keymap, slot: int, data: bytes, offset: int) -> None:
    """Walk 4-byte events starting at ``offset`` until the sentinel."""
    macro_name = f"M{slot + 1}"
    if macro_name in keymap.macros:
        # TEX's web configurator duplicates each macro per profile; keep the first copy.
        return

    events = []
    pos = offset
    while pos + 4 <= len(data):
        event = data[pos:pos + 4]
        if event == MACRO_SENTINEL or event == MACRO_PADDING_WORD:
            break

        keycode_lo = event[0]
        action_byte = event[1]
        delay = int.from_bytes(event[2:4], "little")

        action_bits = action_byte & 0xFC
        keycode_hi_bits = action_byte & 0x03
        keycode = keycode_lo | (keycode_hi_bits << 8)

        if action_bits == 0x3C:
            action = "press"
        elif action_bits == 0x5C:
            action = "release"
        else:
            raise ValueError(f"unknown macro action 0x{action_bits:02X} at {pos:#x}")

        events.append(MacroEvent(action, keyaction_from_id(keycode), delay))
        pos += 4

    if events:
        keymap.macros[macro_name] = events
