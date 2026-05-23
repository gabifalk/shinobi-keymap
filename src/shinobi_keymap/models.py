# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Gabi Falk

"""Format-agnostic keymap types.

"""

from __future__ import annotations

from collections.abc import Iterator

from .constants import (
    KEYCODE_TO_MATRIX,
    KEYCODE_TO_NAME,
    MATRIX_TO_KEYCODE,
    PHYSICAL_KEYCODES,
    KEYCODES,
)


class KeyInfo:
    """Physical key on the keyboard.  Used as the dict key in ``Keymap.bindings``."""

    __slots__ = ("keycode", "name")

    def __init__(self, keycode: int, name: str) -> None:
        self.keycode = keycode
        self.name = name

    def __hash__(self) -> int:
        return self.keycode

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, KeyInfo):
            return NotImplemented
        return self.keycode == other.keycode

    def __repr__(self) -> str:
        return f"KeyInfo({self.name!r})"


class KeyAction:
    """Action keycode -- what a key produces when pressed."""

    __slots__ = ("keycode", "name")

    def __init__(self, keycode: int, name: str) -> None:
        self.keycode = keycode
        self.name = name

    def __hash__(self) -> int:
        return self.keycode

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, KeyAction):
            return NotImplemented
        return self.keycode == other.keycode

    def __repr__(self) -> str:
        return f"KeyAction({self.name!r})"


class MacroAction:
    """Reference, by name, to a macro defined in ``Keymap.macros``."""

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MacroAction):
            return NotImplemented
        return self.name == other.name

    def __repr__(self) -> str:
        return f"MacroAction({self.name!r})"


class KeyBinding:
    """Per-(physical key, profile) bundle.

    Invariant: if ``fn_role`` is not None, all four layer slots are None.
    """

    __slots__ = ("fn_role", "base", "fn1", "fn2", "fn3")

    def __init__(
        self,
        fn_role: int | None = None,
        base: KeyAction | MacroAction | None = None,
        fn1: KeyAction | MacroAction | None = None,
        fn2: KeyAction | MacroAction | None = None,
        fn3: KeyAction | MacroAction | None = None,
    ) -> None:
        self.fn_role = fn_role
        self.base = base
        self.fn1 = fn1
        self.fn2 = fn2
        self.fn3 = fn3

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, KeyBinding):
            return NotImplemented
        return (
            self.fn_role == other.fn_role
            and self.base == other.base
            and self.fn1 == other.fn1
            and self.fn2 == other.fn2
            and self.fn3 == other.fn3
        )

    def __repr__(self) -> str:
        if self.fn_role is not None:
            return f"KeyBinding(fn_role={self.fn_role})"
        parts = []
        if self.base is not None:
            parts.append(f"base={self.base!r}")
        if self.fn1 is not None:
            parts.append(f"fn1={self.fn1!r}")
        if self.fn2 is not None:
            parts.append(f"fn2={self.fn2!r}")
        if self.fn3 is not None:
            parts.append(f"fn3={self.fn3!r}")
        return f"KeyBinding({', '.join(parts)})"


class MacroEvent:
    """One press-or-release tick inside a macro definition."""

    __slots__ = ("action", "key", "delay")

    def __init__(self, action: str, key: KeyAction, delay: int) -> None:
        self.action = action
        self.key = key
        self.delay = delay

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MacroEvent):
            return NotImplemented
        return (
            self.action == other.action
            and self.key == other.key
            and self.delay == other.delay
        )

    def __repr__(self) -> str:
        return f"MacroEvent({self.action!r}, {self.key!r}, delay={self.delay})"


class Keymap:
    """Format-agnostic keymap.  Produced and consumed by YAML and .TEX serializers.

    The four ``compat_*`` fields capture TEX's web configurator quirks
    that don't affect firmware behaviour but are needed to round-trip a
    ``.TEX`` file byte-for-byte.  Hand-written keymaps can leave them all
    at their defaults (empty / False).

    ``compat_tex_padding`` (bool): when True, the writer pads the file with
    ``0xFF`` to the target size TEX's web configurator emits (see
    ``docs/TEX_FORMAT.md`` "Padding and File Size").  Reader sets this on
    any ``.TEX`` input whose size differs from the natural section end.

    ``compat_touched`` (``{(profile_id, layer_id): set[keycode]}``): per
    fn-layer set of keycodes the user "touched" in TEX's web configurator
    UI.  Drives that UI's byte-exact fn-layer ordering -- touched keys
    form a priority block emitted first (keycode-sorted), with everything
    else following (also keycode-sorted).  Base never has a priority
    block, so ``layer_id`` is 1/2/3 only.  Not derivable from binding
    values alone: a slot can be touched and still hold a value that
    matches its cascade default.

    ``compat_fn_ghost`` (``{(profile_id, keycode): KeyBinding}``): for keys
    that are fn-triggers (``fn_role`` set), holds the layer-slot actions
    TEX's web configurator wrote out anyway.  The firmware ignores them
    (the fn-position record overrides), but reproducing them is needed
    for byte-equal round-trips.  The stored ``KeyBinding`` has
    ``fn_role=None`` and only the layer slots that were actually emitted.

    ``compat_fn_position_slots`` (``{(profile_id, fn_role): list[int | None]}``):
    the exact ordered slot list to emit in the fn-position footer record.
    Each slot is a matrix index (``hi * 8 + lo``) or ``None`` for the
    ``0xB4`` null sentinel TEX's web configurator emits.  When absent,
    the writer derives a sorted list from the ``fn_role`` bindings;
    supply this only when the ordering TEX's web configurator emits
    differs from that derivation (e.g. null sentinels, or a non-sorted
    order).
    """

    __slots__ = (
        "layout", "bindings", "macros",
        "compat_touched", "compat_tex_padding", "compat_fn_ghost",
        "compat_fn_position_slots",
    )

    def __init__(
        self,
        layout: str,
        bindings: dict[KeyInfo, dict[int, KeyBinding]] | None = None,
        macros: dict[str, list[MacroEvent]] | None = None,
        compat_touched: dict[tuple[int, int], set[int]] | None = None,
        compat_tex_padding: bool = False,
        compat_fn_ghost: dict[tuple[int, int], KeyBinding] | None = None,
        compat_fn_position_slots: dict[tuple[int, int], list[int | None]] | None = None,
    ) -> None:
        self.layout = layout
        self.bindings = bindings if bindings is not None else {}
        self.macros = macros if macros is not None else {}
        self.compat_touched = compat_touched if compat_touched is not None else {}
        self.compat_tex_padding = compat_tex_padding
        self.compat_fn_ghost = compat_fn_ghost if compat_fn_ghost is not None else {}
        self.compat_fn_position_slots = (
            compat_fn_position_slots if compat_fn_position_slots is not None else {}
        )


def keyinfo_from_id(keycode: int) -> KeyInfo:
    if keycode not in PHYSICAL_KEYCODES:
        raise ValueError(f"keycode {keycode} is not a physical key")
    return KeyInfo(keycode, KEYCODE_TO_NAME[keycode])


def keyinfo_from_name(name: str) -> KeyInfo:
    if name not in KEYCODES:
        raise ValueError(f"{name!r} is not a known .TEX keycode name")
    keycode = KEYCODES[name]
    if keycode not in PHYSICAL_KEYCODES:
        raise ValueError(f"{name!r} is not a physical key")
    return KeyInfo(keycode, name)


def keyinfo_from_phys(layout: str, hi: int, lo: int) -> KeyInfo:
    keycode = MATRIX_TO_KEYCODE[layout][(hi, lo)]
    return KeyInfo(keycode, KEYCODE_TO_NAME[keycode])


def physical_keys(layout: str) -> Iterator[KeyInfo]:
    """Yield every physical key on ``layout`` as a ``KeyInfo``."""
    for keycode in KEYCODE_TO_MATRIX[layout]:
        yield keyinfo_from_id(keycode)


def keyaction_from_id(value: int) -> KeyAction:
    if value not in KEYCODE_TO_NAME:
        raise ValueError(f"keycode {value} is not a known .TEX keycode")
    return KeyAction(value, KEYCODE_TO_NAME[value])


def keyaction_from_name(name: str) -> KeyAction:
    if name not in KEYCODES:
        raise ValueError(f"{name!r} is not a known .TEX keycode name")
    return KeyAction(KEYCODES[name], name)


# Our tool's default keymap, layered on top of the "every key maps to itself"
# baseline.  These defaults define what bindings the YAML writer treats as
# "no override" (and so omits) and what the YAML reader's ``fill_defaults``
# pass adds back when reading a sparse YAML file.  On the base layer, an
# action of ``FN1``/``FN2``/``FN3`` designates the key as an fn-trigger
# (sets ``fn_role`` on the binding instead of a base-layer keycode).
_DEFAULT_LAYER_OVERRIDES: dict = {
    "base": {
        "G12": "FN1",
    },
    "fn1": {
        "1": "TP_SPEED1",
        "2": "TP_SPEED2",
        "3": "TP_SPEED3",
        "4": "TP_SPEED4",
        "5": "TP_SPEED5",
        "6": "TP_SPEED6",
        "7": "TP_SPEED7",
        "8": "TP_SPEED8",
        "9": "TP_SPEED9",
        "R_ARROW": "NEXT_TRACK",
        "L_ARROW": "PRE_TRACK",
        "DN_ARROW": "PLAY_PAUSE",
        "UP_ARROW": "STOP",
    },
    "fn2": {},
    "fn3": {},
}

_FN_TRIGGER_NAMES = {"FN1": 1, "FN2": 2, "FN3": 3}


def default_keymap(layout: str) -> "Keymap":
    """Build the tool's default ``Keymap`` for ``layout``.

    Every physical key on the layout maps to itself on every layer of every
    profile, plus the per-layer overrides in ``_DEFAULT_LAYER_OVERRIDES``:
      * On the base layer, ``G12`` is an ``FN1`` trigger.
      * On the ``fn1`` layer, the number row (``1``..``9``) and arrow keys
        produce trackpoint-speed and media-control actions.
    """
    keymap = Keymap(layout=layout)
    for key in physical_keys(layout):
        self_action = keyaction_from_id(key.keycode)
        for pid in (1, 2, 3):
            keymap.bindings.setdefault(key, {})[pid] = KeyBinding(
                base=self_action, fn1=self_action, fn2=self_action, fn3=self_action,
            )

    for layer_name, overrides in _DEFAULT_LAYER_OVERRIDES.items():
        for key_name, action_name in overrides.items():
            key = keyinfo_from_name(key_name)

            if layer_name == "base" and action_name in _FN_TRIGGER_NAMES:
                fn_role = _FN_TRIGGER_NAMES[action_name]
                for pid in (1, 2, 3):
                    keymap.bindings[key][pid] = KeyBinding(fn_role=fn_role)
                continue

            action = keyaction_from_name(action_name)
            for pid in (1, 2, 3):
                setattr(keymap.bindings[key][pid], layer_name, action)

    return keymap


def layer_specific_default(
    default_binding: "KeyBinding", layer_name: str
) -> "KeyAction | MacroAction | None":
    """Return the key-specific layer default for ``layer_name``, or ``None``.

    A default is "key-specific" iff the default's value for this layer
    differs from the default's base value (so e.g. ``1`` on ``fn1`` ->
    ``TP_SPEED1`` is key-specific because base default for ``1`` is just
    ``1``).  When the default has ``fn_role`` set, all four layer slots are
    ``None`` and there's no layer-specific default to return.
    """
    if default_binding.fn_role is not None:
        return None
    layer_value: KeyAction | MacroAction | None = getattr(default_binding, layer_name)
    if layer_value != default_binding.base:
        return layer_value
    return None


def fill_defaults(keymap: "Keymap") -> None:
    """Merge ``default_keymap(keymap.layout)`` into ``keymap``.

    Resolution per (key, profile):
      1. No user binding at all: clone the default.
      2. User has ``fn_role`` set: leave untouched.
      3. Otherwise (user has ``fn_role=None``):
         * ``base``: user's value, else the default's base value, else self
           if the default was ``fn_role`` (the user has "demoted" this key).
         * Each ``fnN``: user's value, else the key-specific layer default
           if one exists (e.g. ``TP_SPEED1`` for ``1`` on fn1), else the
           resolved ``base`` -- so a base override cascades into all fn
           layers that don't have their own layer-specific default.
    """
    default = default_keymap(keymap.layout)
    for key, default_per_profile in default.bindings.items():
        per_profile = keymap.bindings.setdefault(key, {})
        for pid in (1, 2, 3):
            default_binding = default_per_profile[pid]
            user_binding = per_profile.get(pid)

            if user_binding is None:
                per_profile[pid] = KeyBinding(
                    fn_role=default_binding.fn_role,
                    base=default_binding.base,
                    fn1=default_binding.fn1,
                    fn2=default_binding.fn2,
                    fn3=default_binding.fn3,
                )
                continue

            if user_binding.fn_role is not None:
                continue

            self_action = keyaction_from_id(key.keycode)
            demoted = default_binding.fn_role is not None

            if user_binding.base is None:
                user_binding.base = self_action if demoted else default_binding.base

            for layer_name in ("fn1", "fn2", "fn3"):
                if getattr(user_binding, layer_name) is not None:
                    continue
                if isinstance(user_binding.base, MacroAction):
                    # Macro on base doesn't cascade into fn layers; tex_writer
                    # emits NO ghost rows there to match TEX's web configurator.
                    continue
                layer_specific = layer_specific_default(default_binding, layer_name)
                fill = layer_specific if layer_specific is not None else user_binding.base
                setattr(user_binding, layer_name, fill)
