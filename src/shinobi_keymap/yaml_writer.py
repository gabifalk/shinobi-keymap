# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Gabi Falk

"""Write Keymap instances out as YAML keymap files.

Inverse of ``yaml_reader``.  Bindings are emitted in keycode order; only
non-empty layer slots are included.  An ``fn_role`` binding becomes a
``KEY: FN<n>`` entry on the base layer.  Profiles 1/2/3 are always emitted
(possibly as empty ``{}``) so the file shape matches reader expectations.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .constants import KEYCODE_TO_MATRIX, KEYCODE_TO_NAME, MATRIX_TO_KEYCODE
from .models import (
    KeyAction,
    Keymap,
    MacroAction,
    MacroEvent,
    default_keymap,
    keyaction_from_id,
    keyaction_from_name,
    layer_specific_default,
)


SUPPORTED_VERSION = 1
_DEFAULT_PROFILE_IDS = (1, 2, 3)
_LAYER_NAMES = ("base", "fn1", "fn2", "fn3")


def dump(keymap: Keymap, path: str | Path) -> None:
    """Write ``keymap`` to ``path`` as YAML."""
    Path(path).write_text(dumps(keymap))


def dumps(keymap: Keymap) -> str:
    """Serialise ``keymap`` to YAML text.

    Bindings that match the tool's default keymap for the layout are omitted.
    """
    doc: dict = {"version": SUPPORTED_VERSION, "layout": keymap.layout}

    compat = _render_compat(keymap)
    if compat:
        doc["compat"] = compat

    default = default_keymap(keymap.layout)
    profiles: dict = {}
    for pid in _DEFAULT_PROFILE_IDS:
        body = _render_profile(keymap, pid, default)
        profiles[f"profile{pid}"] = body if body else {}
    doc["profiles"] = profiles

    if keymap.macros:
        doc["macros"] = {name: _render_macro(events) for name, events in keymap.macros.items()}

    return str(yaml.safe_dump(doc, sort_keys=False, default_flow_style=False))


def _render_compat(keymap: Keymap) -> dict:
    out: dict = {}
    if keymap.compat_tex_padding:
        out["tex_padding"] = True
    touched = _render_compat_touched(keymap)
    if touched:
        out["touched"] = touched
    fn_ghost = _render_compat_fn_ghost(keymap)
    if fn_ghost:
        out["fn_ghost"] = fn_ghost
    slots = _render_compat_fn_position_slots(keymap)
    if slots:
        out["fn_position_slots"] = slots
    return out


def _render_compat_touched(keymap: Keymap) -> dict:
    out: dict = {}
    for (pid, layer_id), keycodes in sorted(keymap.compat_touched.items()):
        if not keycodes:
            continue
        names = [KEYCODE_TO_NAME[kc] for kc in sorted(keycodes)]
        out.setdefault(f"profile{pid}", {})[_LAYER_NAMES[layer_id]] = names
    return out


def _render_compat_fn_ghost(keymap: Keymap) -> dict:
    out: dict = {}
    for (pid, kc), ghost in sorted(keymap.compat_fn_ghost.items()):
        layers: dict = {}
        for layer_name in _LAYER_NAMES:
            value = getattr(ghost, layer_name)
            if value is not None:
                layers[layer_name] = _format_action(value)
        if layers:
            out.setdefault(f"profile{pid}", {})[KEYCODE_TO_NAME[kc]] = layers
    return out


def _render_compat_fn_position_slots(keymap: Keymap) -> dict:
    out: dict = {}
    matrix_lookup = MATRIX_TO_KEYCODE[keymap.layout]
    matrix = KEYCODE_TO_MATRIX[keymap.layout]
    for (pid, fn_role), slot_list in sorted(keymap.compat_fn_position_slots.items()):
        if slot_list == _default_fn_slot_list(keymap, pid, fn_role, matrix):
            continue  # matches what tex_writer would emit anyway
        rendered: list = []
        for slot in slot_list:
            if slot is None:
                rendered.append(None)
            else:
                kc = matrix_lookup[(slot // 8, slot % 8)]
                rendered.append(KEYCODE_TO_NAME[kc])
        out.setdefault(f"profile{pid}", {})[f"fn{fn_role}"] = rendered
    return out


def _default_fn_slot_list(keymap: Keymap, pid: int, fn_role: int, matrix: dict) -> list:
    """Slot list tex_writer derives when compat_fn_position_slots is absent."""
    indices = []
    for key, per_profile in keymap.bindings.items():
        binding = per_profile.get(pid)
        if binding is None or binding.fn_role != fn_role:
            continue
        hi, lo = matrix[key.keycode]
        indices.append(hi * 8 + lo)
    return sorted(indices)


def _render_profile(keymap: Keymap, profile_id: int, default: Keymap) -> dict:
    layers: dict = {name: {} for name in _LAYER_NAMES}
    all_keys = set(default.bindings) | set(keymap.bindings)
    for key in sorted(all_keys, key=lambda k: k.keycode):
        binding = keymap.bindings.get(key, {}).get(profile_id)
        default_binding = default.bindings.get(key, {}).get(profile_id)

        if binding is not None and binding.fn_role is not None:
            if default_binding is not None and default_binding.fn_role == binding.fn_role:
                continue  # fn_role matches default; no override to emit
            layers["base"][key.name] = f"FN{binding.fn_role}"
            continue

        if default_binding is None:
            # Key isn't in the default layout; emit every set slot verbatim.
            if binding is not None:
                for layer_name in _LAYER_NAMES:
                    value = getattr(binding, layer_name)
                    if value is not None:
                        layers[layer_name][key.name] = _format_action(value)
            continue

        # Resolve effective slot values: a None slot or absent-from-bindings
        # key means "no row in .TEX", which is semantically the same as NO.
        # Comparing those against the default-layout cascade lets the writer
        # naturally emit ``KEY: NONE`` when the slot diverges from default.
        def slot(layer_name: str) -> KeyAction | MacroAction:
            if binding is None:
                return keyaction_from_name("NO")
            value = getattr(binding, layer_name)
            return keyaction_from_name("NO") if value is None else value

        eff_base = slot("base")

        self_action = keyaction_from_id(key.keycode)
        demoted = default_binding.fn_role is not None
        implicit_base = self_action if demoted else default_binding.base

        cells: list = []
        if eff_base != implicit_base:
            cells.append(("base", eff_base))
        for layer_name in ("fn1", "fn2", "fn3"):
            value = slot(layer_name)
            layer_specific = layer_specific_default(default_binding, layer_name)
            if layer_specific is not None:
                expected = layer_specific
            elif isinstance(eff_base, MacroAction):
                # Macro on base cascades as a NO ghost row on each fn layer.
                expected = keyaction_from_name("NO")
            else:
                expected = eff_base
            if value == expected:
                continue
            cells.append((layer_name, value))

        # When demoted, the reader needs *some* slot in the YAML as the signal
        # to drop the default fn_role.  If everything else matches the cascade,
        # emit base anyway.
        if demoted and not cells:
            cells = [("base", eff_base)]

        for layer_name, value in cells:
            layers[layer_name][key.name] = _format_action(value)

    return {name: contents for name, contents in layers.items() if contents}


def _format_action(value: KeyAction | MacroAction) -> str:
    if isinstance(value, MacroAction):
        return f"M_{value.name}"
    if isinstance(value, KeyAction):
        if value.keycode == 0:
            return "NONE"
        return value.name
    raise TypeError(f"unexpected layer slot value: {value!r}")


def _render_macro(events: list) -> list:
    return [_render_event(e) for e in events]


def _render_event(event: MacroEvent) -> dict:
    out: dict = {"action": event.action, "key": event.key.name}
    if event.delay != 0:
        out["delay"] = event.delay
    return out
