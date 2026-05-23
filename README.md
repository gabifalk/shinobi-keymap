# TEX Shinobi Keymap Tools

[![PyPI](https://img.shields.io/pypi/v/shinobi-keymap.svg)](https://pypi.org/project/shinobi-keymap/)

Python tools for working with TEX Shinobi keyboard keymap files (`.TEX` format).

## Features

- **Parse** binary `.TEX` keymap files into a format-agnostic `Keymap` model.
- **Convert** between `.TEX` and a human-readable YAML format.
- **Render** an ASCII visualisation of the layout, with per-profile / per-layer views.
- **Emulate** the keyboard at a REPL to test how a keymap behaves before flashing.
- **Dump** and **diff** `.TEX` binaries with annotated hex output.
- **Byte-equal round-trip** with the `.TEX` output of TEX's web configurator (including its padding and ghost-row quirks).

## Installation

```bash
pip install shinobi-keymap
```

This installs the `shinobi-keymap` command. For a development checkout, install the source tree in editable mode instead:

```bash
pip install -e .
```

## Quick Start

```bash
# Inspect a binary keymap
shinobi-keymap ascii KEYMAP.TEX --layout ANSI

# Convert it to editable YAML
shinobi-keymap convert KEYMAP.TEX --layout ANSI -o keymap.yaml

# Edit keymap.yaml, then write a new binary
shinobi-keymap convert keymap.yaml -o NEW_KEYMAP.TEX
```

## CLI Commands

### `shinobi-keymap convert`

Convert between `.TEX` and YAML. Input/output formats are inferred from the file
extension; pass `--from` / `--to` to override.

```bash
# .TEX -> YAML (stdout)
shinobi-keymap convert KEYMAP.TEX --layout ANSI

# .TEX -> YAML (file)
shinobi-keymap convert KEYMAP.TEX --layout ANSI -o keymap.yaml

# YAML -> .TEX
shinobi-keymap convert keymap.yaml -o KEYMAP.TEX
```

Options:

- `--layout {ANSI,ISO,JIS}` -- required when reading `.TEX`.
- `-o, --output FILE` -- output path; format inferred from extension.
- `--from {yaml,tex}` -- explicit input format.
- `--to {yaml,tex}` -- explicit output format.

### `shinobi-keymap ascii`

Render an ASCII visualisation of a keymap, or of the tool's defaults.

```bash
shinobi-keymap ascii keymap.yaml
shinobi-keymap ascii KEYMAP.TEX --layout ANSI

# Filter by profile/layer
shinobi-keymap ascii keymap.yaml --profile 1 --layer fn1

# Reference views (no input file needed)
shinobi-keymap ascii --key-names --layout ANSI
shinobi-keymap ascii --key-ids --layout ANSI
shinobi-keymap ascii --key-matrix --layout ANSI
shinobi-keymap ascii --show-default --layout ANSI
```

### `shinobi-keymap emulate`

Interactive REPL for exercising a keymap.

```bash
shinobi-keymap emulate KEYMAP.TEX --layout ANSI
shinobi-keymap emulate keymap.yaml --profile profile2
```

REPL commands:

- `press KEY` -- press and hold a key
- `release KEY` -- release a held key
- `tap KEY...` -- press and release keys in sequence
- `state` -- show current layer and held keys
- `reset` -- reset emulator
- `quit` / Ctrl+D -- exit

TAB completion is available for key names.

### `shinobi-keymap dump`

Annotated hex dump of a `.TEX` file.

```bash
shinobi-keymap dump KEYMAP.TEX --layout ANSI
shinobi-keymap dump KEYMAP.TEX --layout ANSI --diffable
```

### `shinobi-keymap diff`

Diff two `.TEX` files via their annotated dumps.

```bash
shinobi-keymap diff KEYMAP1.TEX KEYMAP2.TEX --layout ANSI
```

### `shinobi-keymap actions`

Print every action name usable on the right side of a YAML binding (or inside
a macro `key:`), one per line. Names are clustered by keycode group (so e.g.
`F1`..`F12` and `NUM_*` stay together); pipe to `sort` for alphabetical order
or to `grep` to search.

```bash
shinobi-keymap actions | grep -i vol
```

## YAML Format

The YAML format is sparse: only overrides of the layout's default keymap are
listed. Each of the three profiles is emitted (possibly as `{}`); within a
profile, only layers with overrides appear, and within a layer, only keys
that differ from the cascade.

```yaml
version: 1
layout: ANSI
profiles:
  profile1:
    base:
      CAPS_LOCK: ESC        # CapsLock -> Escape
      PGUP: END             # PgUp acts as End
    fn1:
      H: M_hi               # FN1 + H types "hi"
  profile2: {}
  profile3: {}
macros:
  hi:
  - action: press
    key: H
  - action: release
    key: H
  - action: press
    key: I
  - action: release
    key: I
```

### Key points

- **Physical key names** -- `A`, `ESC`, `L_SHIFT`, `G12`, etc. instead of matrix indices. For the list of valid LHS keys, run `shinobi-keymap ascii --key-names --layout ANSI` (or `--layout ISO` / `JIS`), or see the "Matrix Index Reference" section of `docs/TEX_FORMAT.md`; for the list of valid RHS action names, run `shinobi-keymap actions`, or see the "Action-Only Keycodes" section of `docs/TEX_FORMAT.md`.
- **Sparse layers** -- anything matching the layout default is omitted.
- **Cascade** -- on read, an unset `fn1`/`fn2`/`fn3` slot for a key falls back to that key's `base` value (which itself falls back to the layout default).
- **Special action values:**
  - `FN1` / `FN2` / `FN3` on `base` make a key a layer trigger.
  - `NONE` means "no binding" (suppresses the cascade for that slot).
  - `M_<name>` references a macro defined under `macros:`.
- **Macro events** are `action: press|release`, `key: <action-keycode>`, optional `delay:` (milliseconds to wait *after* the event). `delay: 0` may be omitted.
- **`compat:` block** -- optional, used to preserve quirks of TEX's web configurator (padding, ghost rows, fn-position ordering) for byte-equal round-trips. Hand-written keymaps don't need it.

## Python API

```python
from shinobi_keymap import (
    Keymap, KeyBinding,
    keyinfo_from_name, keyaction_from_name,
)
from shinobi_keymap import tex_reader, tex_writer, yaml_reader, yaml_writer

# Load
keymap = tex_reader.read("KEYMAP.TEX", layout="ANSI")
# or
keymap = yaml_reader.read("keymap.yaml")

# Inspect / modify
caps = keyinfo_from_name("CAPS_LOCK")
keymap.bindings[caps] = {
    1: KeyBinding(base=keyaction_from_name("ESC")),
}

# Save
yaml_writer.dump(keymap, "out.yaml")
tex_writer.dump(keymap, "out.TEX")
```

`Keymap.bindings` is keyed `KeyInfo -> {profile_id: KeyBinding}`, where
`profile_id` is `1`, `2`, or `3`. A `KeyBinding` has either a non-`None`
`fn_role` (making the key a layer trigger) or up to four layer slots
(`base`, `fn1`, `fn2`, `fn3`), each holding a `KeyAction`, a `MacroAction`,
or `None`.

## Development

```bash
pip install -e '.[dev]'
pytest
```

See `docs/TEX_FORMAT.md` for the binary format reference.

## License

GPL-2.0-or-later
