# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Gabi Falk

"""Keyboard emulator for testing and debugging Keymap instances.

The Keymap is expected to be in its dense form -- the YAML and .TEX readers
produce dense keymaps already; if you construct one in Python, call
``models.fill_defaults(keymap)`` first.
"""

from __future__ import annotations

from typing import Union

from .models import (
    KeyAction,
    KeyBinding,
    KeyInfo,
    Keymap,
    MacroAction,
    keyinfo_from_name,
)


class UnknownKeyError(Exception):
    """Raised when a key identifier doesn't resolve to a physical key."""


class KeyNotHeldError(Exception):
    """Raised on ``release()`` for a key that wasn't pressed."""


class Event:
    """One HID-level press/release with an optional inter-event delay."""

    __slots__ = ("action", "keycode", "delay_ms")

    def __init__(self, action: str, keycode: str, delay_ms: int = 0) -> None:
        self.action = action  # "PRESS" or "RELEASE"
        self.keycode = keycode
        self.delay_ms = delay_ms

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Event):
            return NotImplemented
        return (
            self.action == other.action
            and self.keycode == other.keycode
            and self.delay_ms == other.delay_ms
        )

    def __repr__(self) -> str:
        return f"Event({self.action!r}, {self.keycode!r}, delay_ms={self.delay_ms})"

    def __str__(self) -> str:
        if self.delay_ms > 0:
            return f"{self.action} {self.keycode} [{self.delay_ms}ms]"
        return f"{self.action} {self.keycode}"


KeyId = Union[str, KeyInfo]


class Emulator:
    """Simulates the firmware's keypress handling for a single profile."""

    def __init__(self, keymap: Keymap, profile_id: int = 1) -> None:
        if profile_id not in (1, 2, 3):
            raise ValueError(f"profile_id must be 1, 2, or 3, got {profile_id}")
        self.keymap = keymap
        self.profile_id = profile_id
        self.active_fn: int | None = None
        self.held: set[KeyInfo] = set()

    @property
    def active_layer(self) -> str:
        return "base" if self.active_fn is None else f"fn{self.active_fn}"

    @property
    def held_keys(self) -> list[str]:
        return sorted(k.name for k in self.held)

    def reset(self) -> None:
        self.active_fn = None
        self.held.clear()

    def press(self, key: KeyId) -> list[Event]:
        """Press a key.  Returns the events the firmware would emit."""
        info = self._resolve(key)
        self.held.add(info)

        binding = self._binding(info)
        if binding is None:
            return []

        if binding.fn_role is not None:
            # One layer at a time: only the first held fn-trigger activates;
            # subsequent fn-trigger presses are ignored until that one is
            # released.
            if self.active_fn is None:
                self.active_fn = binding.fn_role
            return []

        slot = self._current_slot(binding)
        if isinstance(slot, MacroAction):
            return self._expand_macro(slot)
        if isinstance(slot, KeyAction) and slot.keycode != 0:
            return [Event("PRESS", slot.name)]
        return []

    def release(self, key: KeyId) -> list[Event]:
        """Release a previously pressed key."""
        info = self._resolve(key)
        if info not in self.held:
            raise KeyNotHeldError(f"not held: {info.name!r}")
        self.held.discard(info)

        binding = self._binding(info)
        if binding is None:
            return []

        if binding.fn_role is not None:
            if self.active_fn == binding.fn_role:
                self.active_fn = None
            return []

        slot = self._current_slot(binding)
        if isinstance(slot, MacroAction):
            return []  # macros fire on press only
        if isinstance(slot, KeyAction) and slot.keycode != 0:
            return [Event("RELEASE", slot.name)]
        return []

    def tap(self, key: KeyId) -> list[Event]:
        """Press and release a key, returning the combined event stream."""
        return self.press(key) + self.release(key)

    def _resolve(self, key: KeyId) -> KeyInfo:
        if isinstance(key, KeyInfo):
            return key
        if isinstance(key, str):
            try:
                return keyinfo_from_name(key)
            except (KeyError, ValueError) as exc:
                raise UnknownKeyError(f"unknown key: {key!r}") from exc
        raise UnknownKeyError(f"unknown key: {key!r}")

    def _binding(self, info: KeyInfo) -> KeyBinding | None:
        per_profile = self.keymap.bindings.get(info)
        if per_profile is None:
            return None
        return per_profile.get(self.profile_id)

    def _current_slot(self, binding: KeyBinding) -> KeyAction | MacroAction | None:
        if self.active_fn is None:
            return binding.base
        if self.active_fn == 1:
            return binding.fn1
        if self.active_fn == 2:
            return binding.fn2
        return binding.fn3

    def _expand_macro(self, ref: MacroAction) -> list[Event]:
        events = self.keymap.macros.get(ref.name, ())
        out = []
        for ev in events:
            action = "PRESS" if ev.action == "press" else "RELEASE"
            out.append(Event(action, ev.key.name, delay_ms=ev.delay))
        return out
