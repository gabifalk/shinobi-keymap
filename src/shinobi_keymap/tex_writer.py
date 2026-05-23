# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Gabi Falk

"""Write Keymap instances out as .TEX binary files.

See ``docs/TEX_FORMAT.md`` for the binary format.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from .constants import KEYCODE_TO_MATRIX
from .models import KeyAction, KeyBinding, KeyInfo, Keymap, MacroAction


MAGIC = b"CYFI\x00\x00"
MACRO_SECTION_SIZE = 0x280
MACRO_SENTINEL = b"\x00\xfc\xc8\x00"

# Profile section terminator: an 8-byte all-zero row.
_PROFILE_TERMINATOR = b"\x00" * 8

# Default profile ids when the keymap has nothing in them.  The firmware
# convention is three profiles; we always emit all three so the file shape
# matches what stock firmware expects.
_DEFAULT_PROFILE_IDS = (1, 2, 3)


def dump(keymap: Keymap, path: str | Path) -> None:
    """Write ``keymap`` to ``path`` in .TEX binary format."""
    Path(path).write_bytes(dumps(keymap))


def dumps(keymap: Keymap) -> bytes:
    """Serialise ``keymap`` to .TEX binary data.

    Every macro defined in ``keymap.macros`` is emitted once per profile, the
    same way TEX's web configurator does it.  Each emitted section is a full
    duplicate of the macro's bytes -- we do not try to share one section
    between profiles (firmware behaviour with shared descriptors is untested).
    """
    profile_ids = _DEFAULT_PROFILE_IDS

    macro_slots = {name: i for i, name in enumerate(keymap.macros)}
    macro_descs = [
        (pid, slot, name)
        for pid in profile_ids
        for name, slot in macro_slots.items()
    ]

    if len(macro_slots) > 12:
        raise ValueError(
            f"too many macros ({len(macro_slots)}); TEX's web configurator supports 12"
        )

    profile_bodies = {pid: _render_profile(keymap, pid, macro_slots) for pid in profile_ids}
    macro_body = {name: _render_macro(keymap.macros[name]) for name in macro_slots}

    section_count = len(profile_ids) + len(macro_descs)

    # Lay out section offsets in the order they appear in the file.
    cursor = 8 + section_count * 8
    profile_offsets = {}
    for pid in profile_ids:
        profile_offsets[pid] = cursor
        cursor += len(profile_bodies[pid])

    macro_offsets = []  # parallel to macro_descs
    for _ in macro_descs:
        macro_offsets.append(cursor)
        cursor += MACRO_SECTION_SIZE

    out = bytearray()
    out += MAGIC
    out += section_count.to_bytes(2, "little")

    for pid in profile_ids:
        out += _descriptor(kind=0x00, ident=pid, slot=0, offset=profile_offsets[pid])
    for (pid, slot, _name), offset in zip(macro_descs, macro_offsets):
        out += _descriptor(kind=0x01, ident=pid, slot=slot, offset=offset)

    for pid in profile_ids:
        out += profile_bodies[pid]
    for _pid, _slot, name in macro_descs:
        out += macro_body[name]

    target = _target_size(
        len(out),
        num_macros=len(macro_descs),
        compat_quirks=keymap.compat_tex_padding,
    )
    if target > len(out):
        out += b"\xff" * (target - len(out))
    elif target < len(out):
        # ``entry_count * 8`` falls below the unpadded data when macro
        # sections are present (each contributes 8 bytes of "wasted" slot
        # beyond its 79 logical entries).  The cut lands inside the trailing
        # 0xFF of the last macro section -- sentinel and events stay intact.
        out = out[:target]

    return bytes(out)


def _target_size(data_size: int, num_macros: int, *, compat_quirks: bool) -> int:
    """File-size target (see docs/TEX_FORMAT.md "Padding and File Size").

    ``data_size`` is the unpadded total byte size of the file (magic +
    descriptors + section bodies).  Each macro section contributes 79
    entries instead of 80 (one 8-byte slot is subtracted per macro), so
    ``entry_count = (data_size - num_macros * 8) // 8``.

    With ``compat_quirks`` (i.e. ``compat_tex_padding``): faithfully
    reproduce the buggy ``max(8N, 8192 + 4N + odd_adj)`` formula TEX's
    web configurator emits, where the 4-per-entry growth and the
    odd-alignment patch look like halfword/byte unit confusion in its
    allocator.

    Without ``compat_quirks``: the clean intent ``max(8192, 8N)`` --
    at least one 8 KB block, otherwise just hold the entries.  Both branches
    truncate when ``entry_count * 8`` falls below the unpadded data; the
    cut only lands in the trailing 0xFF of the last macro section.
    """
    entry_count = (data_size - num_macros * 8) // 8
    if compat_quirks:
        formula_target = 8192 + entry_count * 4
        if entry_count % 2:
            formula_target += 4
    else:
        formula_target = 8192
    return max(formula_target, entry_count * 8)


def _descriptor(kind: int, ident: int, slot: int, offset: int) -> bytes:
    return bytes([kind, ident]) + slot.to_bytes(2, "little") + offset.to_bytes(4, "little")


def _render_profile(keymap: Keymap, profile_id: int, macro_slots: dict) -> bytes:
    """Render one profile section in the emission order TEX's web configurator uses.

    Each fn layer's section is a "priority block" (keys listed in
    ``keymap.compat_touched[(profile_id, layer)]``, in keycode order) followed
    by a "tail" (remaining keys, in keycode order).  TEX's web configurator
    chooses between two layouts depending on the priority sets:

      * "Per-layer": when all non-empty priority sets are identical (or only
        one fn layer has a priority block), each fn layer's prio+tail is
        emitted as one contiguous run -- ``fn1[prio+tail] -> fn2[prio+tail]
        -> fn3[prio+tail] -> base``.
      * "Cross-layer": when the priority sets differ across layers, all
        priority blocks come first (in fn1/fn2/fn3 order), then all tails --
        ``fn1[prio] -> fn2[prio] -> fn3[prio] -> fn1[tail] -> fn2[tail] ->
        fn3[tail] -> base``.

    The two layouts collapse to the same output whenever fn2 and fn3 have no
    priority sets, which is why most fixtures don't expose the distinction.
    """
    out = bytearray()
    fn_keys: dict[int, list] = {1: [], 2: [], 3: []}
    sorted_keys = sorted(keymap.bindings, key=lambda k: k.keycode)

    # Collect fn-trigger keys for the footer records, once.
    for key in sorted_keys:
        binding = keymap.bindings[key].get(profile_id)
        if binding is not None and binding.fn_role is not None:
            fn_keys[binding.fn_role].append(key)

    non_empty = [
        keymap.compat_touched[(profile_id, lid)]
        for lid in (1, 2, 3)
        if keymap.compat_touched.get((profile_id, lid))
    ]
    per_layer = len(non_empty) <= 1 or all(s == non_empty[0] for s in non_empty[1:])

    if per_layer:
        for layer_id in (1, 2, 3):
            touched = keymap.compat_touched.get((profile_id, layer_id), set())
            for key in sorted_keys:
                if key.keycode in touched:
                    _emit_layer_entry(out, keymap, profile_id, key, layer_id, macro_slots)
            for key in sorted_keys:
                if key.keycode not in touched:
                    _emit_layer_entry(out, keymap, profile_id, key, layer_id, macro_slots)
    else:
        for layer_id in (1, 2, 3):
            touched = keymap.compat_touched.get((profile_id, layer_id), set())
            for key in sorted_keys:
                if key.keycode in touched:
                    _emit_layer_entry(out, keymap, profile_id, key, layer_id, macro_slots)
        for layer_id in (1, 2, 3):
            touched = keymap.compat_touched.get((profile_id, layer_id), set())
            for key in sorted_keys:
                if key.keycode not in touched:
                    _emit_layer_entry(out, keymap, profile_id, key, layer_id, macro_slots)

    # Base layer last, plain keycode order.
    for key in sorted_keys:
        _emit_layer_entry(out, keymap, profile_id, key, 0, macro_slots)

    for fn_role in (1, 2, 3):
        compat_slots = keymap.compat_fn_position_slots.get((profile_id, fn_role))
        slot_list: Sequence[int | None]
        if compat_slots is not None:
            slot_list = compat_slots
        else:
            keys = fn_keys[fn_role]
            if not keys:
                continue
            matrix = KEYCODE_TO_MATRIX[keymap.layout]
            slot_list = sorted(matrix[k.keycode][0] * 8 + matrix[k.keycode][1] for k in keys)
        out += _fn_position_record(fn_role, slot_list)

    out += _PROFILE_TERMINATOR
    return bytes(out)


def _emit_layer_entry(
    out: bytearray,
    keymap: Keymap,
    profile_id: int,
    key: KeyInfo,
    layer_id: int,
    macro_slots: dict[str, int],
) -> None:
    per_profile = keymap.bindings[key]
    if profile_id not in per_profile:
        return
    binding = per_profile[profile_id]
    if binding.fn_role is not None:
        ghost = keymap.compat_fn_ghost.get((profile_id, key.keycode))
        if ghost is None:
            return
        value = _layer_value(ghost, layer_id)
    else:
        value = _layer_value(binding, layer_id)
        # TEX's web configurator ghost: a key bound to a macro on base gets an
        # "action = NO" row on every fn layer.  Trigger for unset slots and
        # explicit NO slots alike -- TEX's web configurator always emits the row.
        is_no = isinstance(value, KeyAction) and value.keycode == 0
        if (value is None or is_no) and layer_id in (1, 2, 3) and isinstance(binding.base, MacroAction):
            out += _normal_entry(key.keycode, layer_id, 0)
            return
    if value is None:
        return
    if isinstance(value, KeyAction):
        # YAML "NONE" / KeyAction(0) means "no row in TEX".
        if value.keycode == 0:
            return
        out += _normal_entry(key.keycode, layer_id, value.keycode)
    elif isinstance(value, MacroAction):
        slot = macro_slots[value.name]
        out += _macro_binding(key.keycode, layer_id, slot)
    else:
        raise TypeError(f"unexpected layer slot value: {value!r}")


def _layer_value(binding: KeyBinding, layer_id: int) -> KeyAction | MacroAction | None:
    if layer_id == 0:
        return binding.base
    if layer_id == 1:
        return binding.fn1
    if layer_id == 2:
        return binding.fn2
    return binding.fn3


def _normal_entry(key_keycode: int, layer_id: int, action_keycode: int) -> bytes:
    return (
        bytes([0x02, 0x20, key_keycode, layer_id])
        + action_keycode.to_bytes(2, "little")
        + b"\x00\x00"
    )


def _macro_binding(key_keycode: int, layer_id: int, macro_slot: int) -> bytes:
    return (
        bytes([0x02, 0x18])
        + macro_slot.to_bytes(2, "little")
        + bytes([key_keycode, 0x3C + layer_id])
        + b"\x01\x00"
    )


def _fn_position_record(fn_role: int, slot_list: Sequence[int | None]) -> bytes:
    """Emit a fn-position record with the given ordered slot list.

    Each slot is either a matrix index byte or ``None`` for the 0xB4 null
    sentinel TEX's web configurator emits.  Unused trailing positions are
    padded with 0xFF.
    """
    if len(slot_list) > 4:
        raise ValueError(f"fn{fn_role} has {len(slot_list)} slots; max is 4")

    marker = 0x93 + fn_role  # 1 -> 0x94, 2 -> 0x95, 3 -> 0x96
    payload = bytes(0xB4 if s is None else s for s in slot_list)
    payload += b"\xff" * (4 - len(slot_list))
    return bytes([0x02, marker]) + len(slot_list).to_bytes(2, "little") + payload


def _render_macro(events: list) -> bytes:
    out = bytearray()
    for event in events:
        keycode = event.key.keycode
        keycode_lo = keycode & 0xFF
        keycode_hi_bits = (keycode >> 8) & 0x03
        if event.action == "press":
            action_byte = 0x3C | keycode_hi_bits
        elif event.action == "release":
            action_byte = 0x5C | keycode_hi_bits
        else:
            raise ValueError(f"unknown macro action {event.action!r}")
        out += bytes([keycode_lo, action_byte])
        out += event.delay.to_bytes(2, "little")

    out += MACRO_SENTINEL
    if len(out) > MACRO_SECTION_SIZE:
        raise ValueError(f"macro section overflow: {len(out)} > {MACRO_SECTION_SIZE}")
    out += b"\xff" * (MACRO_SECTION_SIZE - len(out))
    return bytes(out)
