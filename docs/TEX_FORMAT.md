# TEX Shinobi .TEX File Format

This document consolidates what is currently known about the binary structure of TEX Shinobi
keymap files (`.TEX`).

## Contents

- [High-Level Layout](#high-level-layout)
- [Header](#header-8-bytes)
- [Section Descriptor Table](#section-descriptor-table)
- [Profile Sections](#profile-sections)
  - [Entry Format](#entry-format)
  - [Normal Key Entry (`0x20`)](#normal-key-entry-0x20)
  - [Macro Binding (`0x18`)](#macro-binding-0x18)
  - [Fn Position Records (`0x94`, `0x95`, `0x96`)](#fn-position-records-0x94-0x95-0x96)
  - [Matrix Index Reference](#matrix-index-reference)
  - [Action-Only Keycodes](#action-only-keycodes)
- [Macro Definition Sections](#macro-definition-sections)
- [Conventions](#conventions)
- [Padding and File Size](#padding-and-file-size)

## High-Level Layout

| Region           | Contents                                                                            |
|------------------|-------------------------------------------------------------------------------------|
| Header           | 8-byte file header (magic + section count)                                          |
| Descriptor table | 8 bytes * section_count -- one row per section                                      |
| Sections         | Profile and macro definition sections, at the offsets given in the descriptor table |

All multi-byte values are little-endian. There are two kinds of section:

- **Profile sections** -- packed 8-byte entries describing key mappings, key-to-macro bindings,
  and fn-key positions for one profile.
- **Macro definition sections** -- byte streams of 4-byte macro events for a single macro slot.

The format itself does not constrain the number of profile sections, the number of macro
sections, or their ordering. Stock firmware follows a fixed convention (see
[Conventions](#conventions)).

## Header (8 bytes)

| Byte(s) | Field           | Notes                                                  |
|---------|-----------------|--------------------------------------------------------|
| 0--5    | `magic`         | ASCII `CYFI` followed by two `0x00` bytes              |
| 6--7    | `section_count` | `uint16 LE` -- number of rows in the descriptor table  |

## Section Descriptor Table

Immediately after the header, `section_count` * 8-byte descriptors enumerate the file's sections.

| Byte(s) | Field      | Notes                                                             |
|---------|------------|-------------------------------------------------------------------|
| 0       | `kind`     | `0x00` profile section, `0x01` macro definition section           |
| 1       | `id`       | Profile id (`0x01`/`0x02`/`0x03`). For macros: the owning profile |
| 2--3    | `slot`     | `uint16 LE` -- 0-based macro slot. `0` for profile descriptors    |
| 4--7    | `offset`   | `uint32 LE` -- absolute byte offset of the section's payload      |

A profile descriptor names a profile section; a macro descriptor names the macro definition for
one `(profile, slot)` pair.

Example (three profiles, one user macro duplicated per profile -> `section_count = 6`):

```
0x0000  43 59 46 49 00 00 06 00                  magic + section_count=6
0x0008  00 01 00 00 38 00 00 00                  profile id=1 @ 0x0038
0x0010  00 02 00 00 28 0c 00 00                  profile id=2 @ 0x0C28
0x0018  00 03 00 00 18 18 00 00                  profile id=3 @ 0x1818
0x0020  01 01 00 00 08 24 00 00                  macro profile=1 slot=0 @ 0x2408
0x0028  01 02 00 00 88 26 00 00                  macro profile=2 slot=0 @ 0x2688
0x0030  01 03 00 00 08 29 00 00                  macro profile=3 slot=0 @ 0x2908
```

## Profile Sections

A profile section is a packed sequence of 8-byte entries starting at the offset named in its
descriptor and running until the next section. If the profile has any fn-based bindings, the
section ends with one fn-position record per fn layer that has bindings (see
[Fn Position Records](#fn-position-records-0x94-0x95-0x96)).

### Entry Format

Each entry is 8 bytes. The first two bytes (`type`, `marker`) discriminate the row; the
remaining six bytes' meaning depends on the marker.

| Byte(s) | Field      | Notes                                          |
|---------|------------|------------------------------------------------|
| 0       | `type`     | `0x02` for every profile-section entry         |
| 1       | `marker`   | row kind -- see subsections below              |
| 2--7    | payload    | layout depends on `marker`                     |

Observed markers:

| Marker                   | Meaning                         | Subsection                                                 |
|--------------------------|---------------------------------|------------------------------------------------------------|
| `0x20`                   | Normal key mapping              | [Normal Key Entry](#normal-key-entry-0x20)                 |
| `0x18`                   | Key -> macro binding            | [Macro Binding](#macro-binding-0x18)                       |
| `0x94` / `0x95` / `0x96` | Fn1 / Fn2 / Fn3 position record | [Fn Position Records](#fn-position-records-0x94-0x95-0x96) |

The payload bytes serve different roles depending on the marker -- byte 2 is *not* universally a
key index, byte 3 is *not* universally a layer id. See each marker's subsection.

### Normal Key Entry (`0x20`)

| Byte(s) | Field        | Notes                                                       |
|---------|--------------|-------------------------------------------------------------|
| 2       | `key_index`  | Physical matrix index of the key being mapped (0...255)     |
| 3       | `layer_id`   | `0x00` base, `0x01` fn1, `0x02` fn2, `0x03` fn3             |
| 4--5    | `keycode`    | `uint16 LE` -- the action assigned to (layer, key)          |
| 6--7    | reserved     | `uint16 LE` = `0x0000`                                      |

### Macro Binding (`0x18`)

Key shortcuts (on any layer) that trigger a macro slot.

| Byte(s) | Field           | Notes                                                          |
|---------|-----------------|----------------------------------------------------------------|
| 2--3    | `macro_slot`    | `uint16 LE` -- 0-based macro slot (`0` = M1, `1` = M2, ...)    |
| 4       | `key_index`     | Physical matrix index of the key being bound                   |
| 5       | `layer_marker`  | `0x3C` base, `0x3D` fn1, `0x3E` fn2, `0x3F` fn3                |
| 6--7    | reserved        | `uint16 LE` = `0x0001`                                         |

Note the role swap compared to `0x20`: bytes 2--3 are the *action* (macro slot), bytes 4--5 carry
the *binding target* (key + layer), and the layer is *not* in byte 3.

The `layer_marker` values equal `0x3C + layer_id` -- i.e. the same layer encoding as `0x20`'s
byte 3, offset by `0x3C`.

The macro slot is resolved through the descriptor table -- find the macro descriptor whose
`(id, slot)` matches `(profile_id, macro_slot)` to get the offset of the macro definition.

### Fn Position Records (`0x94`, `0x95`, `0x96`)

Profile sections that contain fn-based bindings end with one fn-position record per fn layer
that has any bindings:

- `0x94` -- fn1 positions
- `0x95` -- fn2 positions
- `0x96` -- fn3 positions

| Byte(s) | Field       | Notes                                                                 |
|---------|-------------|-----------------------------------------------------------------------|
| 2--3    | `count`     | `uint16 LE` -- number of valid entries in `fn_idx`                    |
| 4--7    | `fn_idx[4]` | matrix indices; only the first `count` are valid, the rest are `0xFF` |

Each valid `idx` identifies a fn-key position in the matrix as
`(col = idx // 8, row = idx % 8)`. `0x00` is a valid index (`(0, 0)` = the L_CTRL matrix slot);
the only "unused slot" sentinel is `0xFF`.

Examples:

- `count = 2`, `fn_idx = [0x00, 0x46, 0xFF, 0xFF]` -> `(0,0)` and `(8,6)`.
- `count = 2`, `fn_idx = [0x30, 0x46, 0xFF, 0xFF]` -> `(6,0)` and `(8,6)` (e.g. top/bottom halves
  of a split layout).

### Matrix Index Reference

TEX's web configurator and the keyboard firmware both use the same scan matrix. The table below
merges every `(col, row)` position observed across the default ANSI, ISO, and JIS layouts.
Columns:

- `Keycode` -- the physical key ID, which matches the default firmware keycode for that key.
- `Hi` / `Lo` -- the matrix `(col, row)` position.
- `Default Key` -- the symbolic identifier for that keycode.
- `Note` -- layout-specific qualifier (`ANSI only`, `ISO / JIS only`, etc.); empty rows apply
  to all three default layouts.

The physical key ID is the same as the keycode value. The cols and rows are
just internal keyboard wiring and have no direct relationship to the key ID.

| Keycode | Hi  | Lo  | Default Key | Note            |
|---------|-----|-----|-------------|-----------------|
|       4 |   6 |   4 | A           |                 |
|       5 |   0 |   1 | B           |                 |
|       6 |   6 |   2 | C           |                 |
|       7 |   0 |   3 | D           |                 |
|       8 |   2 |   5 | E           |                 |
|       9 |   1 |   3 | F           |                 |
|      10 |   2 |   3 | G           |                 |
|      11 |   3 |   3 | H           |                 |
|      12 |   7 |   5 | I           |                 |
|      13 |   4 |   3 | J           |                 |
|      14 |   5 |   3 | K           |                 |
|      15 |   6 |   3 | L           |                 |
|      16 |   2 |   1 | M           |                 |
|      17 |   1 |   1 | N           |                 |
|      18 |   0 |   4 | O           |                 |
|      19 |   1 |   4 | P           |                 |
|      20 |   0 |   5 | Q           |                 |
|      21 |   3 |   5 | R           |                 |
|      22 |   7 |   4 | S           |                 |
|      23 |   4 |   5 | T           |                 |
|      24 |   6 |   5 | U           |                 |
|      25 |   7 |   2 | V           |                 |
|      26 |   1 |   5 | W           |                 |
|      27 |   5 |   2 | X           |                 |
|      28 |   5 |   5 | Y           |                 |
|      29 |   4 |   2 | Z           |                 |
|      30 |   1 |   7 | 1           |                 |
|      31 |   2 |   7 | 2           |                 |
|      32 |   3 |   7 | 3           |                 |
|      33 |   4 |   7 | 4           |                 |
|      34 |   5 |   7 | 5           |                 |
|      35 |   6 |   7 | 6           |                 |
|      36 |   7 |   7 | 7           |                 |
|      37 |   0 |   6 | 8           |                 |
|      38 |   1 |   6 | 9           |                 |
|      39 |   2 |   6 | 0           |                 |
|      40 |   1 |   2 | ENTER       | ANSI only       |
|      40 |   4 |   4 | ENTER       | ISO / JIS only  |
|      41 |   8 |   4 | ESC         |                 |
|      42 |   6 |   6 | BACKSPACE   |                 |
|      43 |   7 |   6 | TAB         |                 |
|      44 |   3 |   0 | SPACE       |                 |
|      45 |   3 |   6 | NEG         |                 |
|      46 |   4 |   6 | EQUATION    |                 |
|      47 |   2 |   4 | L_BRACKETS  |                 |
|      48 |   3 |   4 | R_BRACKETS  |                 |
|      49 |   1 |   2 | BACKSLASH   | ISO / JIS only  |
|      49 |   4 |   4 | BACKSLASH   | ANSI only       |
|      51 |   7 |   3 | SEMICOLON   |                 |
|      52 |   0 |   2 | APOSTROPHE  |                 |
|      53 |   0 |   7 | TILDE       |                 |
|      54 |   3 |   1 | COMMA       |                 |
|      55 |   4 |   1 | DOT         |                 |
|      56 |   5 |   1 | SLASH       |                 |
|      57 |   5 |   4 | CAP         |                 |
|      58 |   8 |   3 | F1          |                 |
|      59 |   8 |   2 | F2          |                 |
|      60 |   8 |   1 | F3          |                 |
|      61 |   8 |   0 | F4          |                 |
|      62 |   9 |   7 | F5          |                 |
|      63 |   9 |   6 | F6          |                 |
|      64 |  10 |   7 | F7          |                 |
|      65 |  10 |   6 | F8          |                 |
|      66 |  10 |   5 | F9          |                 |
|      67 |  10 |   4 | F10         |                 |
|      68 |  10 |   3 | F11         |                 |
|      69 |  12 |   3 | F12         |                 |
|      70 |  12 |   4 | PRINT       |                 |
|      71 |  11 |   7 | SCROLL      |                 |
|      72 |  11 |   6 | PAUSE       |                 |
|      73 |  11 |   5 | INSERT      |                 |
|      74 |  11 |   4 | HOME        |                 |
|      75 |  11 |   3 | PGUP        |                 |
|      76 |  10 |   2 | DEL         |                 |
|      77 |  10 |   1 | END         |                 |
|      78 |  10 |   0 | PGDN        |                 |
|      79 |  11 |   0 | R_ARROW     |                 |
|      80 |  11 |   2 | L_ARROW     |                 |
|      81 |  11 |   1 | DN_ARROW    |                 |
|      82 |  12 |   1 | UP_ARROW    |                 |
|     100 |   3 |   2 | CODE45      | ISO only        |
|     101 |   5 |   0 | APP         |                 |
|     135 |   7 |   1 | CODE56      | JIS only        |
|     136 |  13 |   6 | CODE133     | JIS only        |
|     137 |   5 |   6 | CODE14      | JIS only        |
|     139 |  13 |   7 | CODE131     | JIS only        |
|     200 |   8 |   7 | G9          |                 |
|     201 |   8 |   6 | G10         |                 |
|     202 |   8 |   5 | G11         |                 |
|     203 |   6 |   0 | G12         |                 |
|     224 |   0 |   0 | L_CTRL      |                 |
|     225 |   2 |   2 | L_SHIFT     |                 |
|     226 |   2 |   0 | L_ALT       |                 |
|     227 |   1 |   0 | L_WIN       |                 |
|     228 |   7 |   0 | R_CTRL      |                 |
|     229 |   6 |   1 | R_SHIFT     |                 |
|     230 |   4 |   0 | R_ALT       |                 |
|     244 |  12 |   5 | MUTE        |                 |
|     245 |  12 |   6 | VOL_DEC     |                 |
|     246 |  12 |   7 | VOL_INC     |                 |
|     249 |  12 |   2 | W3BACK      |                 |
|     250 |  12 |   0 | W3FORWARD   |                 |

### Action-Only Keycodes

Keycode values that appear as the `keycode` field of a `0x20` entry but have no corresponding
default physical key (see [Matrix Index Reference](#matrix-index-reference) for keycodes that
match physical keys).

| Hex      | Dec | Symbol                  | Notes                                       |
|----------|-----|-------------------------|---------------------------------------------|
| `0x0000` |   0 | `NO`                    | Unbound                                     |
| `0x0001` |   1 | `ERR_RO`                |                                             |
| `0x0002` |   2 | `POST_FAIL`             |                                             |
| `0x0003` |   3 | `UNDEFINE`              |                                             |
| `0x0032` |  50 | `CODE42`                |                                             |
| `0x0053` |  83 | `NUM_LOCK`              | Numpad Num Lock                             |
| `0x0054` |  84 | `NUM_DIV`               | Numpad `/`                                  |
| `0x0055` |  85 | `NUM_STAR`              | Numpad `*`                                  |
| `0x0056` |  86 | `NUM_NEG`               | Numpad `-`                                  |
| `0x0057` |  87 | `NUM_PLUS`              | Numpad `+`                                  |
| `0x0058` |  88 | `NUM_ENTER`             | Numpad Enter                                |
| `0x0059` |  89 | `NUM_1`                 | Numpad 1                                    |
| `0x005A` |  90 | `NUM_2`                 | Numpad 2                                    |
| `0x005B` |  91 | `NUM_3`                 | Numpad 3                                    |
| `0x005C` |  92 | `NUM_4`                 | Numpad 4                                    |
| `0x005D` |  93 | `NUM_5`                 | Numpad 5                                    |
| `0x005E` |  94 | `NUM_6`                 | Numpad 6                                    |
| `0x005F` |  95 | `NUM_7`                 | Numpad 7                                    |
| `0x0060` |  96 | `NUM_8`                 | Numpad 8                                    |
| `0x0061` |  97 | `NUM_9`                 | Numpad 9                                    |
| `0x0062` |  98 | `NUM_0`                 | Numpad 0                                    |
| `0x0063` |  99 | `NUM_DOT`               | Numpad `.`                                  |
| `0x0066` | 102 | `POWER`                 | System power                                |
| `0x0067` | 103 | `EQUAL`                 |                                             |
| `0x0068` | 104 | `F13`                   |                                             |
| `0x0069` | 105 | `F14`                   |                                             |
| `0x006A` | 106 | `F15`                   |                                             |
| `0x006B` | 107 | `F16`                   |                                             |
| `0x006C` | 108 | `F17`                   |                                             |
| `0x006D` | 109 | `F18`                   |                                             |
| `0x006E` | 110 | `F19`                   |                                             |
| `0x006F` | 111 | `F20`                   |                                             |
| `0x0070` | 112 | `F21`                   |                                             |
| `0x0071` | 113 | `F22`                   |                                             |
| `0x0072` | 114 | `F23`                   |                                             |
| `0x0073` | 115 | `F24`                   |                                             |
| `0x0074` | 116 | `KB_EXECUTE`            | Keyboard execute                            |
| `0x0075` | 117 | `KB_HELP`               | Keyboard help                               |
| `0x0076` | 118 | `KB_MENU`               | Keyboard menu                               |
| `0x0077` | 119 | `KB_SELECT`             | Keyboard select                             |
| `0x0078` | 120 | `KB_STOP`               | Keyboard stop                               |
| `0x0079` | 121 | `KB_AGAIN`              | Keyboard again                              |
| `0x007A` | 122 | `KB_UNDO`               | Keyboard undo                               |
| `0x007B` | 123 | `KB_CUT`                | Keyboard cut                                |
| `0x007C` | 124 | `KB_COPY`               | Keyboard copy                               |
| `0x007D` | 125 | `KB_PASTE`              | Keyboard paste                              |
| `0x007E` | 126 | `KB_FIND`               | Keyboard find                               |
| `0x007F` | 127 | `KB_MUTE`               | Keyboard mute                               |
| `0x0080` | 128 | `KB_VOL_UP`             | Keyboard volume up                          |
| `0x0081` | 129 | `KB_VOL_DN`             | Keyboard volume down                        |
| `0x0082` | 130 | `LOCK_CAP`              | Locking Caps Lock                           |
| `0x0083` | 131 | `LOCK_NUM`              | Locking Num Lock                            |
| `0x0084` | 132 | `LOCK_SCR`              | Locking Scroll Lock                         |
| `0x0085` | 133 | `CODE107`               |                                             |
| `0x0086` | 134 | `AS_400`                |                                             |
| `0x008A` | 138 | `CODE132`               |                                             |
| `0x0090` | 144 | `CODE151`               |                                             |
| `0x0091` | 145 | `CODE150`               |                                             |
| `0x00B0` | 176 | `MOUSE_KEY1`            |                                             |
| `0x00B1` | 177 | `MOUSE_KEY2`            |                                             |
| `0x00B2` | 178 | `MOUSE_KEY3`            |                                             |
| `0x00B3` | 179 | `MOUSE_KEY4`            |                                             |
| `0x00B4` | 180 | `MOUSE_KEY5`            |                                             |
| `0x00B5` | 181 | `MOUSE_KEY6`            |                                             |
| `0x00B6` | 182 | `MOUSE_KEY7`            |                                             |
| `0x00B7` | 183 | `MOUSE_KEY8`            |                                             |
| `0x00B8` | 184 | `MOUSE_KEY9`            |                                             |
| `0x00B9` | 185 | `MOUSE_KEY10`           |                                             |
| `0x00BA` | 186 | `MOUSE_KEY11`           |                                             |
| `0x00BB` | 187 | `MOUSE_KEY12`           |                                             |
| `0x00BC` | 188 | `MOUSE_KEY13`           |                                             |
| `0x00BD` | 189 | `MOUSE_KEY14`           |                                             |
| `0x00BE` | 190 | `MOUSE_KEY15`           |                                             |
| `0x00BF` | 191 | `MOUSE_KEY16`           |                                             |
| `0x00C0` | 192 | `G1`                    |                                             |
| `0x00C1` | 193 | `G2`                    |                                             |
| `0x00C2` | 194 | `G3`                    |                                             |
| `0x00C3` | 195 | `G4`                    |                                             |
| `0x00C4` | 196 | `G5`                    |                                             |
| `0x00C5` | 197 | `G6`                    |                                             |
| `0x00C6` | 198 | `G7`                    |                                             |
| `0x00C7` | 199 | `G8`                    |                                             |
| `0x00CC` | 204 | `G13`                   |                                             |
| `0x00CD` | 205 | `G14`                   |                                             |
| `0x00CE` | 206 | `G15`                   |                                             |
| `0x00CF` | 207 | `G16`                   |                                             |
| `0x00D0` | 208 | `G17`                   |                                             |
| `0x00D1` | 209 | `G18`                   |                                             |
| `0x00D2` | 210 | `G19`                   |                                             |
| `0x00D3` | 211 | `G20`                   |                                             |
| `0x00D4` | 212 | `G21`                   |                                             |
| `0x00D5` | 213 | `G22`                   |                                             |
| `0x00D6` | 214 | `G23`                   |                                             |
| `0x00D7` | 215 | `G24`                   |                                             |
| `0x00E7` | 231 | `R_WIN`                 | Right Windows / Super                       |
| `0x00E9` | 233 | `ACPI_PD`               | ACPI power-down                             |
| `0x00EA` | 234 | `ACPI_SLEEP`            | ACPI sleep                                  |
| `0x00EB` | 235 | `ACPI_WAKE`             | ACPI wake                                   |
| `0x00EC` | 236 | `MEDIA_SEL`             | Media select                                |
| `0x00ED` | 237 | `MAIL`                  | Launch mail                                 |
| `0x00EE` | 238 | `CALCULATOR`            | Launch calculator                           |
| `0x00EF` | 239 | `MYCOMPUTER`            | Launch file manager                         |
| `0x00F0` | 240 | `PLAY_PAUSE`            | Media play/pause                            |
| `0x00F1` | 241 | `STOP`                  | Media stop                                  |
| `0x00F2` | 242 | `PRE_TRACK`             | Media previous track                        |
| `0x00F3` | 243 | `NEXT_TRACK`            | Media next track                            |
| `0x00F7` | 247 | `W3SEARCH`              | Browser search                              |
| `0x00F8` | 248 | `W3HOME`                | Browser home                                |
| `0x00FB` | 251 | `W3STOP`                | Browser stop                                |
| `0x00FC` | 252 | `W3REFRESH`             | Browser refresh                             |
| `0x00FD` | 253 | `W3FAVORITE`            | Browser favourites                          |
| `0x0131` | 305 | `TP_SPEED1`             | TrackPoint speed preset 1                   |
| `0x0132` | 306 | `TP_SPEED2`             | TrackPoint speed preset 2                   |
| `0x0133` | 307 | `TP_SPEED3`             | TrackPoint speed preset 3                   |
| `0x0134` | 308 | `TP_SPEED4`             | TrackPoint speed preset 4                   |
| `0x0135` | 309 | `TP_SPEED5`             | TrackPoint speed preset 5                   |
| `0x0136` | 310 | `TP_SPEED6`             | TrackPoint speed preset 6                   |
| `0x0137` | 311 | `TP_SPEED7`             | TrackPoint speed preset 7                   |
| `0x0138` | 312 | `TP_SPEED8`             | TrackPoint speed preset 8                   |
| `0x0139` | 313 | `TP_SPEED9`             | TrackPoint speed preset 9                   |
| `0x018A` | 394 | `BAD_MUTE`              | Broken variant of MUTE                      |
| `0x018B` | 395 | `BAD_VOL_DEC`           | Broken variant of VOL_DEC                   |
| `0x018C` | 396 | `BAD_VOL_INC`           | Broken variant of VOL_INC                   |
| `0x018D` | 397 | `BAD_ESC`               | Broken variant of ESC                       |
| `0x01E0` | 480 | `MOUSE_MOVE_UP_LEFT`    | Mouse cursor up-left                        |
| `0x01E1` | 481 | `MOUSE_MOVE_UP`         | Mouse cursor up                             |
| `0x01E2` | 482 | `MOUSE_MOVE_UP_RIGHT`   | Mouse cursor up-right                       |
| `0x01E3` | 483 | `MOUSE_MOVE_RIGHT`      | Mouse cursor right                          |
| `0x01E4` | 484 | `MOUSE_MOVE_DOWN_RIGHT` | Mouse cursor down-right                     |
| `0x01E5` | 485 | `MOUSE_MOVE_DOWN`       | Mouse cursor down                           |
| `0x01E6` | 486 | `MOUSE_MOVE_DOWN_LEFT`  | Mouse cursor down-left                      |
| `0x01E7` | 487 | `MOUSE_MOVE_LEFT`       | Mouse cursor left                           |
| `0x01F0` | 496 | `MOUSE_LEFT`            | Mouse left button                           |
| `0x01F1` | 497 | `MOUSE_RIGHT`           | Mouse right button                          |
| `0x01F2` | 498 | `MOUSE_MIDDLE`          | Mouse middle button                         |
| `0x01F3` | 499 | `MOUSE_BUTTON4`         | Mouse button 4                              |
| `0x01F4` | 500 | `MOUSE_BUTTON5`         | Mouse button 5                              |

The `BAD_*` codes are a bug in TEX's web configurator: it should have emitted the corresponding
real keycodes (`ESC` = 41, `MUTE` = 244, `VOL_DEC` = 245, `VOL_INC` = 246) for those fn-overlay
slots but emits these spurious values instead. The firmware treats them as no-ops -- the keys
act as if disabled. They are documented here because the bug is present in the default keymaps
emitted by TEX's web configurator.

## Macro Definition Sections

Each macro definition section is a fixed 0x280-byte block containing a sequence of 4-byte events
terminated by the sentinel `00 FC C8 00`. Any bytes between the terminator and the end of the
0x280 window are `0xFF`-filled. A section whose entire 0x280 window is `0xFF` is unused.

| Byte(s) | Meaning                                                        |
|---------|----------------------------------------------------------------|
| 0       | Base keycode (low byte)                                        |
| 1       | Action: `0x3C` press, `0x5C` release; low bits extend keycode  |
| 2--3    | Delay in milliseconds (`uint16 LE`)                            |

Macro definitions are referenced only via the section descriptor table -- they are not addressed
from inside profile sections. A macro binding ([`0x18`](#macro-binding-0x18)) names a slot index;
firmware resolves it by looking up the matching `(profile_id, slot)` macro descriptor in the
descriptor table.

## Conventions

The format itself doesn't fix the number of profile sections, the number of macro slots, or how
descriptors and sections are ordered. TEX's web configurator emits a fixed shape:

- Three profile sections, with ids `0x01`, `0x02`, `0x03`. The format permits any number; firmware
  support for more or fewer is untested.
- Macros are duplicated per profile: one user macro emits one macro section per profile, so for
  `P` profiles and `M` user-defined macros, `section_count = P + P * M = P * (1 + M)`.
- All profile descriptors precede all macro descriptors in the descriptor table.
- Profile sections sit immediately after the descriptor table; macro sections sit after the
  profile sections; the tail is `0xFF`-padded.

These are observations about how TEX's web configurator writes files, not constraints the format
imposes.

## Padding and File Size

Keymap files are padded with `0xFF` (small files) or truncated (large files) to a target
size. Empirically deduced from TEX's web configurator output:

```
file_size = max(entry_count * 8, 8192 + entry_count * 4 + (4 if entry_count is odd else 0))
```

The two expressions cross at `entry_count = 2048`: below that the `8192 + 4*N` term wins and
files are padded up; above it the `8*N` term wins and files are *truncated* by exactly
`num_macro_sections * 8` bytes -- the cut falls inside the trailing `0xFF` of the last macro
section, so the sentinel and events remain intact.

### Formula Breakdown

| Component          | Value                            | Notes                                                |
|--------------------|----------------------------------|------------------------------------------------------|
| Base size          | 8192 bytes (8KB)                 |                                                      |
| Per-entry overhead | +4 bytes per 8-byte entry        | Half-rate growth -- see Implementation Notes         |
| Odd alignment      | +4 bytes when entry count is odd | Restores 8-byte alignment (`odd * 4 == 4 mod 8`)     |
| Truncation cap     | `entry_count * 8`                | Applies once it exceeds the padded target            |

### Macro Section Special Case

A 640-byte macro section (80 * 8-byte slots) counts as **79 entries**, not 80. One slot's
worth (8 bytes) is subtracted per section before dividing:

```
entry_count = (data_size - num_macro_sections * 8) // 8
```

### Example Calculations

Padded (small file) -- 1131 entries, no macros:
- `8192 + 1131 * 4 = 12716`
- 1131 is odd, so `+ 4 -> 12720 bytes`

Truncated (large file) -- 2352 entries, 15 macro sections:
- Unpadded data: `2352 * 8 + 15 * 8 = 18936 bytes`
- `entry_count * 8 = 18816` wins over `8192 + 2352*4 = 17600`
- File capped at 18816 -- the last 120 bytes (`15 * 8`) of trailing `0xFF` get cut.

### Implementation Notes

The +4-per-entry rate looks like an implementation quirk -- perhaps the original code counted
entries in 16-bit words rather than bytes. The +4-for-odd then restores 8-byte alignment.
The `entry_count * 8` term is a hard cap on the file's effective size; macro sections "owe"
8 bytes each to that cap, which is what produces the per-section truncation when it activates.

### Reconstructing the Intent

The formula reads like a bug-then-patch chain. A plausible reconstruction of what was meant:

```
file_size = max(8192, entry_count * 8)
```

-- "at least one 8 KB block; otherwise just hold the entries." Two terms, both with obvious
semantics (an 8 KB floor, presumably matching a flash sector or similar; entry data at 8 bytes
each), no crossover that requires explaining, no odd-alignment patch.

The `MAX` in TEX's web configurator's code is most naturally read as a defensive guard ("don't let
the buffer be smaller than the entry data"). Under the clean formula that guard would never
fire -- `8192 + 8N` is always strictly greater than `8N`, so the max is always the padded
target. The fact that the guard *does* fire in practice, on files with more than 2048 entries,
is what reveals that the per-entry growth rate is wrong: `4N` instead of `8N`, half-rate.
The `+4 if odd` term then looks like a downstream fix bolted on after someone noticed the
file size came out misaligned -- it would be unnecessary if the rate were `8` to begin with.

The truncation observed for large files is the natural fallout: once the buffer is sized to
`8N` instead of `8N + 8192`, the physically-written data (which includes 8 wasted bytes per
macro section, since macros allocate 80 slots but count as 79 entries) overflows the buffer
and gets clipped from the end. The clip always falls inside the trailing `0xFF` of the last
macro section -- macro sentinel and events sit at the front -- so the bug never produced
corrupt firmware data, just files of slightly weird sizes.

`tex_writer` faithfully reproduces the buggy formula when `compat_tex_padding=True` (the
default for any Keymap loaded from a TEX file) and uses the clean `max(8192, 8N)` rule when
the flag is False (synthetic Keymaps).
