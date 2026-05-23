# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Gabi Falk

"""Command-line interface for the TEX Shinobi keymap tools.

Run as ``python3 cli.py ...`` from the repo root, or via the
``shinobi-keymap`` script entry point when installed.
"""

from __future__ import annotations

import argparse
import difflib
import io
import sys
from pathlib import Path

from . import ascii as ascii_view
from . import emulator
from . import tex_dump
from . import tex_reader
from . import tex_writer
from . import yaml_reader
from . import yaml_writer
from .constants import KEYCODES
from .models import Keymap, default_keymap

try:
    import readline
except ImportError:
    readline = None  # type: ignore[assignment]


_FORMATS = ("yaml", "tex")
_EXTENSIONS = {".tex": "tex", ".yaml": "yaml", ".yml": "yaml"}


def _detect_format(path: str) -> str | None:
    return _EXTENSIONS.get(Path(path).suffix.lower())


def _load_keymap(path: str, fmt: str, layout: str | None) -> Keymap:
    if fmt == "tex":
        if layout is None:
            raise SystemExit("error: --layout is required when reading a .TEX file")
        return tex_reader.read(path, layout)
    if fmt == "yaml":
        return yaml_reader.read(path)
    raise SystemExit(f"error: unsupported input format {fmt!r}")


def _emit_keymap(keymap: Keymap, output: str | None, fmt: str) -> None:
    if fmt == "yaml":
        text = yaml_writer.dumps(keymap)
        if output is None:
            sys.stdout.write(text)
        else:
            Path(output).write_text(text)
        return
    if fmt == "tex":
        data = tex_writer.dumps(keymap)
        if output is None:
            sys.stdout.buffer.write(data)
        else:
            Path(output).write_bytes(data)
        return
    raise SystemExit(f"error: unsupported output format {fmt!r}")


def _parse_profile(value: str) -> int:
    """Accept either ``profileN`` or a bare ``N`` (1, 2, or 3)."""
    if value.startswith("profile") and value[7:].isdigit():
        n = int(value[7:])
    elif value.isdigit():
        n = int(value)
    else:
        raise SystemExit(f"error: invalid profile {value!r}; expected 'profile1' or '1'")
    if n not in (1, 2, 3):
        raise SystemExit(f"error: profile must be 1, 2, or 3, got {n}")
    return n


def cmd_emulate(args: argparse.Namespace) -> None:
    src_fmt = args.from_ or _detect_format(args.input)
    if src_fmt is None:
        raise SystemExit(
            f"error: cannot infer input format for {args.input!r}; pass --from"
        )
    keymap = _load_keymap(args.input, src_fmt, args.layout)
    profile_id = _parse_profile(args.profile) if args.profile else 1
    em = emulator.Emulator(keymap, profile_id=profile_id)
    _run_repl(em)


_REPL_COMMANDS = ("press", "release", "tap", "state", "reset", "quit")


class _ReplCompleter:
    """TAB completer for the emulator REPL.

    Completes the first token against the REPL commands, and subsequent
    tokens against the keymap's key names when the command takes keys.
    """

    _KEY_COMMANDS = ("press", "release", "tap")

    def __init__(self, key_names: list[str]) -> None:
        self.key_names = sorted(key_names)
        self._matches: list[str] = []

    def complete(self, text: str, state: int) -> str | None:
        if state == 0:
            self._matches = self._compute_matches(text)
        if state < len(self._matches):
            return self._matches[state]
        return None

    def _compute_matches(self, text: str) -> list:
        line = readline.get_line_buffer() if readline is not None else text
        tokens = line.split()
        completing_first_token = not tokens or (
            len(tokens) == 1 and not line.endswith((" ", "\t"))
        )
        if completing_first_token:
            return [c for c in _REPL_COMMANDS if c.startswith(text)]
        if tokens[0] in self._KEY_COMMANDS:
            return [k for k in self.key_names if k.startswith(text)]
        return []


def _run_repl(em: "emulator.Emulator") -> None:
    """Read-eval-print loop driving the emulator.

    Commands: ``press KEY``, ``release KEY``, ``tap KEY...``, ``state``,
    ``reset``, ``quit`` (also EOF / Ctrl+D).  When the ``readline`` module
    is available, TAB completion is enabled for commands and key names.
    """
    if readline is not None:
        key_names = [k.name for k in em.keymap.bindings]
        completer = _ReplCompleter(key_names)
        readline.set_completer(completer.complete)
        readline.parse_and_bind("tab: complete")

    while True:
        try:
            line = input("> ")
        except EOFError:
            print()
            return
        except KeyboardInterrupt:
            print()
            return

        line = line.strip()
        if not line:
            continue

        parts = line.split()
        cmd, rest = parts[0], parts[1:]

        try:
            if cmd == "quit":
                return
            elif cmd == "reset":
                em.reset()
            elif cmd == "state":
                print(f"layer: {em.active_layer}")
                print(f"held: {em.held_keys}")
            elif cmd == "press":
                if len(rest) != 1:
                    print("usage: press KEY")
                    continue
                for event in em.press(rest[0]):
                    print(event)
            elif cmd == "release":
                if len(rest) != 1:
                    print("usage: release KEY")
                    continue
                for event in em.release(rest[0]):
                    print(event)
            elif cmd == "tap":
                if not rest:
                    print("usage: tap KEY [KEY ...]")
                    continue
                for key in rest:
                    for event in em.tap(key):
                        print(event)
            else:
                print(f"unknown command: {cmd!r}")
        except (emulator.UnknownKeyError, emulator.KeyNotHeldError) as exc:
            print(f"error: {exc}")


def cmd_dump(args: argparse.Namespace) -> None:
    if args.layout is None:
        raise SystemExit("error: --layout is required for dump")
    tex_dump.dump_hex(
        args.input,
        layout=args.layout,
        no_addresses=args.diffable,
        output=sys.stdout,
    )


def _dump_to_string(path: str, layout: str) -> str:
    buf = io.StringIO()
    tex_dump.dump_hex(path, layout=layout, no_addresses=True, output=buf)
    return buf.getvalue()


def cmd_diff(args: argparse.Namespace) -> None:
    if args.layout is None:
        raise SystemExit("error: --layout is required for diff")
    a = _dump_to_string(args.file1, args.layout)
    b = _dump_to_string(args.file2, args.layout)
    sys.stdout.writelines(
        difflib.unified_diff(
            a.splitlines(keepends=True),
            b.splitlines(keepends=True),
            fromfile=str(args.file1),
            tofile=str(args.file2),
        )
    )


def cmd_ascii(args: argparse.Namespace) -> None:
    reference_mode = None
    if args.key_names:
        reference_mode = "names"
    elif args.key_ids:
        reference_mode = "ids"
    elif args.key_matrix:
        reference_mode = "matrix"

    if reference_mode is not None:
        if args.layout is None:
            raise SystemExit(
                f"error: --layout is required with --key-{reference_mode}"
            )
        print(ascii_view.render_reference(args.layout, reference_mode))
        return

    if args.show_default:
        if args.layout is None:
            raise SystemExit("error: --layout is required with --show-default")
        keymap = default_keymap(args.layout)
    else:
        if args.input is None:
            raise SystemExit(
                "error: input file is required (or pass --show-default / "
                "--key-names / --key-ids / --key-matrix)"
            )
        src_fmt = args.from_ or _detect_format(args.input)
        if src_fmt is None:
            raise SystemExit(
                f"error: cannot infer input format for {args.input!r}; pass --from"
            )
        keymap = _load_keymap(args.input, src_fmt, args.layout)

    profile_ids = (_parse_profile(args.profile),) if args.profile else None
    layers = (args.layer,) if args.layer else None

    print(ascii_view.render_all(
        keymap,
        profile_ids=profile_ids,
        layers=layers,
        headers=not args.no_headers,
    ))


def cmd_convert(args: argparse.Namespace) -> None:
    src_fmt = args.from_ or _detect_format(args.input)
    if src_fmt is None:
        raise SystemExit(
            f"error: cannot infer input format for {args.input!r}; pass --from"
        )

    if args.output is not None:
        dst_fmt = args.to or _detect_format(args.output)
        if dst_fmt is None:
            raise SystemExit(
                f"error: cannot infer output format for {args.output!r}; pass --to"
            )
    else:
        dst_fmt = args.to or "yaml"

    keymap = _load_keymap(args.input, src_fmt, args.layout)
    _emit_keymap(keymap, args.output, dst_fmt)


def cmd_actions(args: argparse.Namespace) -> None:
    # Names sorted by keycode so related groups (F1..F12, NUM_*, MOUSE_*)
    # stay clustered; pipe to ``sort`` for alphabetical order.
    for name, _kc in sorted(KEYCODES.items(), key=lambda item: item[1]):
        sys.stdout.write(f"{name}\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shinobi-keymap",
        description="Tools for working with TEX Shinobi keyboard keymap files.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    convert = subparsers.add_parser(
        "convert", help="Convert between supported keymap formats."
    )
    convert.add_argument("input", help="Path to input keymap file.")
    convert.add_argument(
        "-o", "--output",
        help="Output file path; format inferred from extension unless --to is given.",
    )
    convert.add_argument(
        "--layout", choices=("ANSI", "ISO", "JIS"),
        help="Keyboard layout; required when reading a .TEX file.",
    )
    convert.add_argument(
        "--from", dest="from_", choices=_FORMATS,
        help="Explicit input format (overrides extension inference).",
    )
    convert.add_argument(
        "--to", choices=_FORMATS,
        help="Explicit output format (overrides extension inference).",
    )
    convert.set_defaults(func=cmd_convert)

    emulate = subparsers.add_parser(
        "emulate", help="Interactive emulator REPL."
    )
    emulate.add_argument("input", help="Path to input keymap file.")
    emulate.add_argument(
        "--layout", choices=("ANSI", "ISO", "JIS"),
        help="Keyboard layout; required when reading a .TEX file.",
    )
    emulate.add_argument(
        "--from", dest="from_", choices=_FORMATS,
        help="Explicit input format (overrides extension inference).",
    )
    emulate.add_argument(
        "--profile",
        help="Profile to emulate: 'profile1', 'profile2', 'profile3', or the bare number.",
    )
    emulate.set_defaults(func=cmd_emulate)

    ascii_cmd = subparsers.add_parser(
        "ascii", help="Render a keymap as an ASCII keyboard diagram."
    )
    ascii_cmd.add_argument(
        "input", nargs="?",
        help="Path to input keymap file (omit with --show-default).",
    )
    ascii_cmd.add_argument(
        "--layout", choices=("ANSI", "ISO", "JIS"),
        help="Keyboard layout; required when reading a .TEX file or "
             "passing --show-default.",
    )
    ascii_cmd.add_argument(
        "--from", dest="from_", choices=_FORMATS,
        help="Explicit input format (overrides extension inference).",
    )
    ascii_cmd.add_argument(
        "--profile",
        help="Render only this profile ('profile1' / '1' / etc).",
    )
    ascii_cmd.add_argument(
        "--layer", choices=("base", "fn1", "fn2", "fn3"),
        help="Render only this layer.",
    )
    ascii_cmd.add_argument(
        "--no-headers", action="store_true",
        help="Suppress the 'Profile X | Layer: Y | Layout: Z' headers.",
    )
    mode_group = ascii_cmd.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--show-default", action="store_true",
        help="Render the tool's default keymap for --layout (no input file).",
    )
    mode_group.add_argument(
        "--key-names", action="store_true",
        help="Render a reference diagram with key names in each cell.",
    )
    mode_group.add_argument(
        "--key-ids", action="store_true",
        help="Render a reference diagram with numeric keycodes in each cell.",
    )
    mode_group.add_argument(
        "--key-matrix", action="store_true",
        help="Render a reference diagram with each key's matrix position (hi,lo).",
    )
    ascii_cmd.set_defaults(func=cmd_ascii)

    dump = subparsers.add_parser(
        "dump", help="Dump a .TEX binary file as annotated hex."
    )
    dump.add_argument("input", help="Path to .TEX file.")
    dump.add_argument(
        "--layout", choices=("ANSI", "ISO", "JIS"),
        help="Keyboard layout (required).",
    )
    dump.add_argument(
        "--diffable", action="store_true",
        help="Omit File:/Size: header and per-row file offsets so two dumps "
             "diff cleanly.",
    )
    dump.set_defaults(func=cmd_dump)

    diff = subparsers.add_parser(
        "diff", help="Diff two .TEX files via their annotated dumps."
    )
    diff.add_argument("file1", help="First .TEX file.")
    diff.add_argument("file2", help="Second .TEX file.")
    diff.add_argument(
        "--layout", choices=("ANSI", "ISO", "JIS"),
        help="Keyboard layout (required).",
    )
    diff.set_defaults(func=cmd_diff)

    actions = subparsers.add_parser(
        "actions",
        help="List every action name usable in a YAML keymap, one per line.",
    )
    actions.set_defaults(func=cmd_actions)

    return parser


def main(argv: list | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except ValueError as exc:
        raise SystemExit(f"error: {exc}")


if __name__ == "__main__":
    main()
