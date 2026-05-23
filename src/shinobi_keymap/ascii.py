# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Gabi Falk

"""ASCII keyboard layout renderer.

Draws a keymap as a visual keyboard using box-drawing characters.
"""

from __future__ import annotations

from typing import Any

from .constants import KEYCODE_TO_MATRIX, KEYCODE_TO_NAME
from .models import KeyAction, KeyBinding, Keymap, MacroAction, keyinfo_from_id


# Each row carries a list of keycodes (0 = blank space) and the per-cell
# terminal-character widths.  Width is normally an int; ``'plus'`` marks the
# two-row ESC/DEL keys, and ``'enter_iso_top'``/``'enter_iso_bottom'`` mark
# the ISO/JIS L-shaped enter key.

_VISUAL_ANSI: list[dict[str, Any]] = [
    {"keys": [0, 200, 201, 202, 0, 80, 81, 79],
     "term_width": [64, 14, 14, 14, 49, 9, 9, 9]},
    {"keys": [203, 224, 227, 226, 44, 230, 101, 228, 0, 249, 82, 250],
     "term_width": [11, 14, 11, 14, 58, 13, 11, 11, 2, 9, 9, 9]},
    {"keys": [225, 0, 29, 27, 6, 25, 5, 17, 16, 54, 55, 56, 229, 0],
     "term_width": [27, None, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 33, None]},
    {"keys": [57, 4, 22, 7, 9, 10, 11, 13, 14, 15, 51, 52, 40],
     "term_width": [20, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 27]},
    {"keys": [43, 20, 26, 8, 21, 23, 28, 24, 12, 18, 19, 47, 48, 49],
     "term_width": [17, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 17]},
    {"keys": [53, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 45, 46, 42],
     "term_width": [11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 23]},
    {"keys": [41, 0, 58, 59, 60, 61, 0, 62, 63, 64, 65, 0, 66, 67, 68, 69, 0, 76, 77, 78],
     "term_width": ["plus", 3, 9, 9, 9, 9, 3, 9, 9, 9, 9, 3, 9, 9, 9, 9, 5, "plus", 9, 9]},
    {"keys": [41, 0, 244, 245, 246, 0, 70, 71, 72, 73, 0, 76, 74, 75],
     "term_width": ["plus", 9, 9, 9, 9, 55, 9, 9, 9, 9, 5, "plus", 9, 9]},
]

_VISUAL_ISO: list[dict[str, Any]] = [
    {"keys": [0, 200, 201, 202, 0, 80, 81, 79],
     "term_width": [64, 14, 14, 14, 49, 9, 9, 9]},
    {"keys": [203, 224, 227, 226, 44, 230, 101, 228, 0, 249, 82, 250],
     "term_width": [11, 14, 11, 14, 58, 13, 11, 11, 2, 9, 9, 9]},
    {"keys": [225, 100, 29, 27, 6, 25, 5, 17, 16, 54, 55, 56, 229, 0],
     "term_width": [14, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 33, None]},
    {"keys": [57, 4, 22, 7, 9, 10, 11, 13, 14, 15, 51, 52, 49, 40],
     "term_width": [20, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, "enter_iso_bottom"]},
    {"keys": [43, 20, 26, 8, 21, 23, 28, 24, 12, 18, 19, 47, 48, 40],
     "term_width": [17, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, "enter_iso_top"]},
    {"keys": [53, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 45, 46, 42],
     "term_width": [11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 23]},
    {"keys": [41, 0, 58, 59, 60, 61, 0, 62, 63, 64, 65, 0, 66, 67, 68, 69, 0, 76, 77, 78],
     "term_width": ["plus", 3, 9, 9, 9, 9, 3, 9, 9, 9, 9, 3, 9, 9, 9, 9, 5, "plus", 9, 9]},
    {"keys": [41, 0, 244, 245, 246, 0, 70, 71, 72, 73, 0, 76, 74, 75],
     "term_width": ["plus", 9, 9, 9, 9, 55, 9, 9, 9, 9, 5, "plus", 9, 9]},
]

_VISUAL_JIS: list[dict[str, Any]] = [
    {"keys": [0, 200, 201, 202, 0, 80, 81, 79],
     "term_width": [64, 14, 14, 14, 49, 9, 9, 9]},
    {"keys": [203, 224, 227, 226, 139, 44, 136, 230, 101, 228, 0, 249, 82, 250],
     "term_width": [11, 14, 11, 11, 11, 37, 11, 11, 11, 11, 2, 9, 9, 9]},
    {"keys": [225, 100, 29, 27, 6, 25, 5, 17, 16, 54, 55, 56, 135, 229],
     "term_width": [27, None, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 20]},
    {"keys": [57, 4, 22, 7, 9, 10, 11, 13, 14, 15, 51, 52, 49, 40],
     "term_width": [20, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, "enter_iso_bottom"]},
    {"keys": [43, 20, 26, 8, 21, 23, 28, 24, 12, 18, 19, 47, 48, 40],
     "term_width": [17, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, "enter_iso_top"]},
    {"keys": [53, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 45, 46, 137, 42],
     "term_width": [11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 10]},
    {"keys": [41, 0, 58, 59, 60, 61, 0, 62, 63, 64, 65, 0, 66, 67, 68, 69, 0, 76, 77, 78],
     "term_width": ["plus", 3, 9, 9, 9, 9, 3, 9, 9, 9, 9, 3, 9, 9, 9, 9, 5, "plus", 9, 9]},
    {"keys": [41, 0, 244, 245, 246, 0, 70, 71, 72, 73, 0, 76, 74, 75],
     "term_width": ["plus", 9, 9, 9, 9, 55, 9, 9, 9, 9, 5, "plus", 9, 9]},
]

_VISUAL_LAYOUTS: dict[str, list[dict[str, Any]]] = {
    "ANSI": _VISUAL_ANSI,
    "ISO": _VISUAL_ISO,
    "JIS": _VISUAL_JIS,
}

_LAYERS = ("base", "fn1", "fn2", "fn3")


def render(keymap: Keymap, profile_id: int = 1, layer: str = "base") -> str:
    """Render one (profile, layer) of ``keymap`` as a box-drawing diagram."""
    if keymap.layout not in _VISUAL_LAYOUTS:
        raise ValueError(f"no visual layout for {keymap.layout!r}")
    if layer not in _LAYERS:
        raise ValueError(f"unknown layer {layer!r}")

    is_fn_layer = layer != "base"
    fn_triggers = {
        key.keycode: per_profile[profile_id].fn_role
        for key, per_profile in keymap.bindings.items()
        if profile_id in per_profile and per_profile[profile_id].fn_role is not None
    }

    labels: dict[int, str] = {}
    for key, per_profile in keymap.bindings.items():
        if profile_id not in per_profile:
            continue
        binding = per_profile[profile_id]

        if binding.fn_role is not None:
            labels[key.keycode] = f"[FN{binding.fn_role}]"
            continue

        # On an fn layer, a key that's an fn-trigger in this profile shows as
        # [FN<N>] -- pressing it activates the layer rather than producing
        # whatever its slot says.
        if is_fn_layer and key.keycode in fn_triggers:
            labels[key.keycode] = f"[FN{fn_triggers[key.keycode]}]"
            continue

        slot = _slot_value(binding, layer)
        labels[key.keycode] = _format_label(slot)

    return _render_keyboard(labels, _VISUAL_LAYOUTS[keymap.layout])


def _slot_value(binding: KeyBinding, layer: str) -> KeyAction | MacroAction | None:
    if layer == "base":
        return binding.base
    if layer == "fn1":
        return binding.fn1
    if layer == "fn2":
        return binding.fn2
    return binding.fn3


def _format_label(value: KeyAction | MacroAction | None) -> str:
    if value is None:
        return ""
    if isinstance(value, MacroAction):
        return f"M_{value.name}"
    if isinstance(value, KeyAction):
        if value.keycode == 0:
            return ""
        return value.name
    return str(value)


def _render_keyboard(labels: dict, layout_rows: list) -> str:
    lines: list[str] = []
    plus_keys_shown: set[int] = set()
    enter_iso_shown = False

    # Walk rows from bottom to top so the visual output matches a keyboard.
    for row_data in reversed(layout_rows):
        row_keys = row_data["keys"]
        row_widths = row_data["term_width"]

        top = "    "
        mid = "    "
        bot = "    "

        for key_idx, width in zip(row_keys, row_widths):
            if width is None or key_idx is None:
                continue

            if isinstance(width, int):
                if key_idx == 0:
                    top += " " * width
                    mid += " " * width
                    bot += " " * width
                else:
                    label = labels.get(key_idx, "")[:width]
                    top += f"┌{'─' * width}┐"
                    mid += f"│{label:^{width}}│"
                    bot += f"└{'─' * width}┘"
            elif width == "plus":
                if key_idx not in plus_keys_shown:
                    label = labels.get(key_idx, "")[:11]
                    top += f"┌{'─' * 11}┐"
                    mid += f"│{label:^11}│"
                    bot += f"│{' ' * 11}│"
                    plus_keys_shown.add(key_idx)
                else:
                    top += f"│{' ' * 11}│"
                    mid += f"│{' ' * 11}│"
                    bot += f"└{'─' * 11}┘"
            elif width == "enter_iso_top":
                tw = 17
                if not enter_iso_shown:
                    label = labels.get(key_idx, "")[:tw]
                    top += f"┌{'─' * tw}┐"
                    mid += f"│{label:^{tw}}│"
                    spaces = tw - 5
                    bot += f"└────┐{' ' * spaces}│"
                    enter_iso_shown = True
            elif width == "enter_iso_bottom":
                bw = 12
                top += f"  │{' ' * bw}│"
                mid += f"  │{' ' * bw}│"
                bot += f"  └{'─' * bw}┘"

        lines.append(top)
        lines.append(mid)
        lines.append(bot)

    return "\n".join(lines)


def render_reference(layout: str, mode: str) -> str:
    """Render a reference view of the layout's physical keys.

    ``mode`` is one of:
      * ``"names"`` -- each cell shows the key's name (e.g. ``"A"``).
      * ``"ids"`` -- each cell shows the numeric keycode (e.g. ``"4"``).
      * ``"matrix"`` -- each cell shows the matrix position as ``"hi,lo"``.
    """
    if layout not in _VISUAL_LAYOUTS:
        raise ValueError(f"no visual layout for {layout!r}")
    if mode not in ("names", "ids", "matrix"):
        raise ValueError(f"unknown reference mode {mode!r}")

    labels: dict[int, str] = {}
    for keycode, (hi, lo) in KEYCODE_TO_MATRIX[layout].items():
        if mode == "names":
            labels[keycode] = KEYCODE_TO_NAME[keycode]
        elif mode == "ids":
            labels[keycode] = str(keycode)
        else:
            labels[keycode] = f"{hi},{lo}"

    return _render_keyboard(labels, _VISUAL_LAYOUTS[layout])


def render_all(
    keymap: Keymap,
    profile_ids: tuple[int, ...] | None = None,
    layers: tuple[str, ...] | None = None,
    headers: bool = True,
) -> str:
    """Render multiple (profile, layer) views, separated by headers."""
    profile_ids = profile_ids if profile_ids is not None else (1, 2, 3)
    layers = layers if layers is not None else _LAYERS

    chunks: list[str] = []
    for pid in profile_ids:
        for lyr in layers:
            if headers:
                chunks.append(
                    f"Profile {pid} | Layer: {lyr} | Layout: {keymap.layout}\n"
                    + "=" * 80
                )
            chunks.append(render(keymap, pid, lyr))
    return "\n\n".join(chunks)
