# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Gabi Falk

"""Read YAML keymap files into Keymap instances.

The YAML schema is sparse: only key overrides are listed, defaults are implicit.
A binding that maps a key to ``FN1`` / ``FN2`` / ``FN3`` on the base layer is
translated into the corresponding ``fn_role`` (and the four layer slots stay
empty per the invariant).  Action values prefixed with ``M_`` reference a macro
by name from the top-level ``macros:`` mapping.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .constants import KEYCODE_TO_MATRIX
from .models import (
    KeyAction,
    KeyBinding,
    KeyInfo,
    Keymap,
    MacroAction,
    MacroEvent,
    fill_defaults,
    keyaction_from_name,
    keyinfo_from_name,
)


SUPPORTED_VERSION = 1
SUPPORTED_LAYOUTS = ("ANSI", "ISO", "JIS")
_LAYER_NAMES = ("base", "fn1", "fn2", "fn3")
_FN_TRIGGERS = {"FN1": 1, "FN2": 2, "FN3": 3}
_FN_ROLE_NAMES = {"fn1": 1, "fn2": 2, "fn3": 3}

# YAML spells "unbound" as NONE; the canonical .TEX keycode name is NO.
_ACTION_ALIASES = {"NONE": "NO"}


def read(path: str | Path) -> Keymap:
    """Read a YAML keymap file into a Keymap."""
    return loads(Path(path).read_text())


def loads(text: str) -> Keymap:
    """Parse YAML keymap data into a Keymap."""
    doc = yaml.safe_load(text)
    if not isinstance(doc, dict):
        raise ValueError("YAML keymap must be a mapping at the top level")

    version = doc.get("version")
    if version != SUPPORTED_VERSION:
        raise ValueError(f"unsupported YAML version {version!r}; expected {SUPPORTED_VERSION}")

    layout = doc.get("layout")
    if layout not in SUPPORTED_LAYOUTS:
        raise ValueError(f"unsupported layout {layout!r}; expected one of {SUPPORTED_LAYOUTS}")

    compat = doc.get("compat") or {}
    keymap = Keymap(
        layout=layout,
        compat_tex_padding=bool(compat.get("tex_padding", False)),
    )

    for profile_name, profile_body in (doc.get("profiles") or {}).items():
        profile_id = _parse_profile_id(profile_name)
        _read_profile(keymap, profile_id, profile_body or {})

    for macro_name, events in (doc.get("macros") or {}).items():
        keymap.macros[macro_name] = [_parse_event(e) for e in events]

    _read_compat_touched(keymap, compat.get("touched") or {})
    _read_compat_fn_ghost(keymap, compat.get("fn_ghost") or {})
    _read_compat_fn_position_slots(keymap, compat.get("fn_position_slots") or {})

    fill_defaults(keymap)
    return keymap


def _read_compat_touched(keymap: Keymap, touched: dict) -> None:
    for profile_name, by_layer in touched.items():
        pid = _parse_profile_id(profile_name)
        for layer_name, key_names in (by_layer or {}).items():
            if layer_name not in _FN_ROLE_NAMES:
                raise ValueError(f"compat.touched: unknown layer {layer_name!r}")
            layer_id = _LAYER_NAMES.index(layer_name)
            keymap.compat_touched[(pid, layer_id)] = {
                keyinfo_from_name(n).keycode for n in (key_names or [])
            }


def _read_compat_fn_ghost(keymap: Keymap, fn_ghost: dict) -> None:
    for profile_name, by_key in fn_ghost.items():
        pid = _parse_profile_id(profile_name)
        for key_name, by_layer in (by_key or {}).items():
            kc = keyinfo_from_name(key_name).keycode
            ghost = KeyBinding()
            for layer_name, action in (by_layer or {}).items():
                if layer_name not in _LAYER_NAMES:
                    raise ValueError(f"compat.fn_ghost: unknown layer {layer_name!r}")
                _set_slot(ghost, _LAYER_NAMES.index(layer_name), _parse_action(action))
            keymap.compat_fn_ghost[(pid, kc)] = ghost


def _read_compat_fn_position_slots(keymap: Keymap, fn_pos: dict) -> None:
    matrix = KEYCODE_TO_MATRIX[keymap.layout]
    for profile_name, by_role in fn_pos.items():
        pid = _parse_profile_id(profile_name)
        for role_name, slot_list in (by_role or {}).items():
            if role_name not in _FN_ROLE_NAMES:
                raise ValueError(f"compat.fn_position_slots: unknown role {role_name!r}")
            fn_role = _FN_ROLE_NAMES[role_name]
            parsed: list = []
            for slot in slot_list or []:
                if slot is None:
                    parsed.append(None)
                else:
                    hi, lo = matrix[keyinfo_from_name(slot).keycode]
                    parsed.append(hi * 8 + lo)
            keymap.compat_fn_position_slots[(pid, fn_role)] = parsed


def _parse_profile_id(name: str) -> int:
    if not isinstance(name, str) or not name.startswith("profile") or not name[7:].isdigit():
        raise ValueError(f"invalid profile name {name!r}; expected 'profileN'")
    return int(name[7:])


def _read_profile(keymap: Keymap, profile_id: int, profile_body: dict) -> None:
    for layer_name, mappings in profile_body.items():
        if layer_name not in _LAYER_NAMES:
            raise ValueError(f"unknown layer {layer_name!r}")
        layer_id = _LAYER_NAMES.index(layer_name)
        for raw_key, action in (mappings or {}).items():
            # PyYAML parses unquoted digit keys ("1", "2", ...) as ints.
            key_name = str(raw_key) if isinstance(raw_key, int) else raw_key
            _apply_mapping(keymap, profile_id, layer_id, key_name, action)


def _apply_mapping(
    keymap: Keymap, profile_id: int, layer_id: int, key_name: str, action: str
) -> None:
    key = keyinfo_from_name(key_name)
    binding = _get_binding(keymap, key, profile_id)

    if layer_id == 0 and isinstance(action, str) and action in _FN_TRIGGERS:
        binding.fn_role = _FN_TRIGGERS[action]
        binding.base = None
        binding.fn1 = None
        binding.fn2 = None
        binding.fn3 = None
        return

    if binding.fn_role is not None:
        # TEX's web configurator quirk: layer-slot entries for an fn-trigger key.
        return

    _set_slot(binding, layer_id, _parse_action(action))


def _parse_action(action: object) -> KeyAction | MacroAction:
    if isinstance(action, str) and action.startswith("M_"):
        return MacroAction(action[2:])
    if not isinstance(action, str):
        raise ValueError(f"action must be a string, got {action!r}")
    return keyaction_from_name(_ACTION_ALIASES.get(action, action))


def _get_binding(keymap: Keymap, key: KeyInfo, profile_id: int) -> KeyBinding:
    per_profile = keymap.bindings.setdefault(key, {})
    if profile_id not in per_profile:
        per_profile[profile_id] = KeyBinding()
    return per_profile[profile_id]


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


def _parse_event(event: object) -> MacroEvent:
    if not isinstance(event, dict):
        raise ValueError(f"macro event must be a mapping, got {event!r}")
    action = event.get("action")
    if action not in ("press", "release"):
        raise ValueError(f"macro event has unknown action {action!r}")
    key_name = event.get("key")
    if not isinstance(key_name, str):
        raise ValueError(f"macro event missing 'key': {event!r}")
    delay = event.get("delay", 0)
    if not isinstance(delay, int):
        raise ValueError(f"macro event 'delay' must be an integer, got {delay!r}")
    return MacroEvent(action, keyaction_from_name(key_name), delay)
