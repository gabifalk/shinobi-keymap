# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Gabi Falk

"""Tools for working with TEX Shinobi keyboard keymap files."""

from .models import (
    KeyAction,
    KeyBinding,
    KeyInfo,
    Keymap,
    MacroAction,
    MacroEvent,
    default_keymap,
    fill_defaults,
    keyaction_from_id,
    keyaction_from_name,
    keyinfo_from_id,
    keyinfo_from_name,
    keyinfo_from_phys,
    layer_specific_default,
    physical_keys,
)

__all__ = [
    "KeyAction",
    "KeyBinding",
    "KeyInfo",
    "Keymap",
    "MacroAction",
    "MacroEvent",
    "default_keymap",
    "fill_defaults",
    "keyaction_from_id",
    "keyaction_from_name",
    "keyinfo_from_id",
    "keyinfo_from_name",
    "keyinfo_from_phys",
    "layer_specific_default",
    "physical_keys",
]
