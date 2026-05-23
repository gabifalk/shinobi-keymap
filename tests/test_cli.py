# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Gabi Falk

"""Tests for the command-line interface."""

from __future__ import annotations

from pathlib import Path

import pytest

from shinobi_keymap import cli
from shinobi_keymap import yaml_reader


FIXTURES_TEX = Path(__file__).parent / "fixtures" / "tex_files"
FIXTURES_YAML = Path(__file__).parent / "fixtures" / "yaml_expected"


# ---------------------------------------------------------- .TEX -> YAML

def test_convert_tex_to_yaml_file(tmp_path, capsys):
    out = tmp_path / "out.yaml"
    cli.main([
        "convert",
        str(FIXTURES_TEX / "KEYMAP_FN_TEST.TEX"),
        "--layout", "ANSI",
        "-o", str(out),
    ])
    captured = capsys.readouterr()
    assert captured.out == ""
    km = yaml_reader.read(out)
    assert km.layout == "ANSI"
    assert any(b.fn_role == 1 for v in km.bindings.values() for b in v.values())


def test_convert_tex_to_yaml_stdout(capsys):
    cli.main([
        "convert",
        str(FIXTURES_TEX / "KEYMAP_FN_TEST.TEX"),
        "--layout", "ANSI",
    ])
    text = capsys.readouterr().out
    assert text.startswith("version: 1\n")
    assert "layout: ANSI" in text


# ---------------------------------------------------------- YAML -> .TEX

def test_convert_yaml_to_tex_file(tmp_path):
    out = tmp_path / "out.TEX"
    cli.main([
        "convert",
        str(FIXTURES_YAML / "KEYMAP_FN_TEST.yaml"),
        "-o", str(out),
    ])
    data = out.read_bytes()
    assert data[:6] == b"CYFI\x00\x00"


def test_yaml_to_tex_round_trip(tmp_path):
    tex_out = tmp_path / "out.TEX"
    yaml_out = tmp_path / "back.yaml"
    cli.main([
        "convert",
        str(FIXTURES_YAML / "KEYMAP_FN_TEST.yaml"),
        "-o", str(tex_out),
    ])
    cli.main([
        "convert", str(tex_out), "--layout", "ANSI", "-o", str(yaml_out),
    ])

    src = yaml_reader.read(FIXTURES_YAML / "KEYMAP_FN_TEST.yaml")
    dst = yaml_reader.read(yaml_out)
    assert src.bindings == dst.bindings
    assert src.macros == dst.macros


# ---------------------------------------------------------- format inference

def test_explicit_from_overrides_extension(tmp_path):
    # Copy a YAML file under a misleading .TEX name and force --from yaml.
    misnamed = tmp_path / "fake.TEX"
    misnamed.write_text((FIXTURES_YAML / "KEYMAP_FN_TEST.yaml").read_text())

    out = tmp_path / "actual.yaml"
    cli.main(["convert", str(misnamed), "--from", "yaml", "-o", str(out)])
    km = yaml_reader.read(out)
    assert km.layout == "ANSI"


def test_explicit_to_overrides_extension(tmp_path):
    out = tmp_path / "weirdname.bin"
    cli.main([
        "convert",
        str(FIXTURES_YAML / "KEYMAP_FN_TEST.yaml"),
        "-o", str(out),
        "--to", "tex",
    ])
    assert out.read_bytes()[:6] == b"CYFI\x00\x00"


def test_unknown_input_extension_requires_from(tmp_path):
    weird = tmp_path / "input.bin"
    weird.write_bytes(b"junk")
    with pytest.raises(SystemExit, match="cannot infer input format"):
        cli.main(["convert", str(weird), "-o", str(tmp_path / "out.yaml")])


def test_unknown_output_extension_requires_to(tmp_path):
    with pytest.raises(SystemExit, match="cannot infer output format"):
        cli.main([
            "convert",
            str(FIXTURES_YAML / "KEYMAP_FN_TEST.yaml"),
            "-o", str(tmp_path / "out.bin"),
        ])


# ---------------------------------------------------------- required-arg errors

def test_tex_input_without_layout_errors(tmp_path):
    with pytest.raises(SystemExit, match="--layout is required"):
        cli.main([
            "convert",
            str(FIXTURES_TEX / "KEYMAP_FN_TEST.TEX"),
            "-o", str(tmp_path / "out.yaml"),
        ])


def test_no_subcommand_errors():
    with pytest.raises(SystemExit):
        cli.main([])


def test_invalid_layout_errors():
    with pytest.raises(SystemExit):
        cli.main([
            "convert",
            str(FIXTURES_TEX / "KEYMAP_FN_TEST.TEX"),
            "--layout", "DVORAK",
        ])


def test_value_error_from_reader_becomes_clean_systemexit(tmp_path):
    # Hand a YAML that the reader will reject for version mismatch.
    bad = tmp_path / "bad.yaml"
    bad.write_text("version: 99\nlayout: ANSI\n")
    with pytest.raises(SystemExit, match="error:"):
        cli.main(["convert", str(bad)])


# ---------------------------------------------------------- emulate REPL

def _drive_repl(monkeypatch, lines):
    """Feed ``lines`` to ``input()`` and return what the REPL printed."""
    seq = iter(lines)
    import builtins
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(seq))


def test_emulate_press_release_emits_events(monkeypatch, capsys):
    _drive_repl(monkeypatch, ["press A", "release A", "quit"])
    cli.main(["emulate", str(FIXTURES_YAML / "KEYMAP_FN_TEST.yaml")])
    out = capsys.readouterr().out
    assert "PRESS A" in out
    assert "RELEASE A" in out


def test_emulate_tap_handles_multiple_keys(monkeypatch, capsys):
    _drive_repl(monkeypatch, ["tap A B C", "quit"])
    cli.main(["emulate", str(FIXTURES_YAML / "KEYMAP_FN_TEST.yaml")])
    lines = capsys.readouterr().out.splitlines()
    actions = [l.strip() for l in lines if "PRESS" in l or "RELEASE" in l]
    assert actions == [
        "PRESS A", "RELEASE A",
        "PRESS B", "RELEASE B",
        "PRESS C", "RELEASE C",
    ]


def test_emulate_fn_overlay_active(monkeypatch, capsys):
    _drive_repl(monkeypatch, ["press G12", "tap A", "release G12", "quit"])
    cli.main(["emulate", str(FIXTURES_YAML / "KEYMAP_FN_TEST.yaml")])
    out = capsys.readouterr().out
    assert "PRESS F1" in out  # A on fn1 in KEYMAP_FN_TEST is F1
    assert "RELEASE F1" in out


def test_emulate_state_reports_layer_and_held(monkeypatch, capsys):
    _drive_repl(monkeypatch, ["press G12", "state", "release G12", "quit"])
    cli.main(["emulate", str(FIXTURES_YAML / "KEYMAP_FN_TEST.yaml")])
    out = capsys.readouterr().out
    assert "layer: fn1" in out
    assert "held: ['G12']" in out


def test_emulate_reset_clears(monkeypatch, capsys):
    _drive_repl(monkeypatch, ["press G12", "reset", "state", "quit"])
    cli.main(["emulate", str(FIXTURES_YAML / "KEYMAP_FN_TEST.yaml")])
    out = capsys.readouterr().out
    assert "layer: base" in out
    assert "held: []" in out


def test_emulate_unknown_key_reports_error(monkeypatch, capsys):
    _drive_repl(monkeypatch, ["press NOPE", "quit"])
    cli.main(["emulate", str(FIXTURES_YAML / "KEYMAP_FN_TEST.yaml")])
    out = capsys.readouterr().out
    assert "error:" in out
    assert "NOPE" in out


def test_emulate_release_unheld_reports_error(monkeypatch, capsys):
    _drive_repl(monkeypatch, ["release A", "quit"])
    cli.main(["emulate", str(FIXTURES_YAML / "KEYMAP_FN_TEST.yaml")])
    out = capsys.readouterr().out
    assert "error:" in out


def test_emulate_unknown_command_reports(monkeypatch, capsys):
    _drive_repl(monkeypatch, ["fly", "quit"])
    cli.main(["emulate", str(FIXTURES_YAML / "KEYMAP_FN_TEST.yaml")])
    out = capsys.readouterr().out
    assert "unknown command" in out


def test_emulate_eof_exits_cleanly(monkeypatch, capsys):
    seq = iter([])
    import builtins
    def fake_input(prompt=""):
        try:
            return next(seq)
        except StopIteration:
            raise EOFError
    monkeypatch.setattr(builtins, "input", fake_input)
    # Should return cleanly without raising.
    cli.main(["emulate", str(FIXTURES_YAML / "KEYMAP_FN_TEST.yaml")])


def test_emulate_profile_selector_int(monkeypatch, capsys):
    _drive_repl(monkeypatch, ["press G12", "tap A", "release G12", "quit"])
    # Profile 2 of FN_TEST: G12 is FN1 but no overlays on A.  fn1+A should
    # emit "A" (the layout default).
    cli.main([
        "emulate",
        str(FIXTURES_YAML / "KEYMAP_FN_TEST.yaml"),
        "--profile", "2",
    ])
    out = capsys.readouterr().out
    assert "PRESS A" in out
    assert "PRESS F1" not in out


def test_emulate_invalid_profile_errors():
    with pytest.raises(SystemExit, match="error:"):
        cli.main([
            "emulate",
            str(FIXTURES_YAML / "KEYMAP_FN_TEST.yaml"),
            "--profile", "bogus",
        ])


def test_emulate_profile_out_of_range_errors():
    with pytest.raises(SystemExit, match="profile must be"):
        cli.main([
            "emulate",
            str(FIXTURES_YAML / "KEYMAP_FN_TEST.yaml"),
            "--profile", "5",
        ])


def test_emulate_tex_input_requires_layout():
    with pytest.raises(SystemExit, match="--layout is required"):
        cli.main([
            "emulate",
            str(FIXTURES_TEX / "KEYMAP_FN_TEST.TEX"),
        ])


# ---------------------------------------------------------- TAB completion

def _completer_with_buffer(monkeypatch, key_names, buffer: str):
    """Build a ``_ReplCompleter`` and fake ``readline.get_line_buffer`` to
    return ``buffer`` so the completer's first-token detection works."""
    monkeypatch.setattr(cli.readline, "get_line_buffer", lambda: buffer)
    return cli._ReplCompleter(key_names)


def _all_completions(completer, text):
    out = []
    for i in range(100):
        match = completer.complete(text, i)
        if match is None:
            break
        out.append(match)
    return out


def test_completer_completes_command_names(monkeypatch):
    c = _completer_with_buffer(monkeypatch, ["A", "B", "C"], "pr")
    assert _all_completions(c, "pr") == ["press"]


def test_completer_completes_partial_command(monkeypatch):
    c = _completer_with_buffer(monkeypatch, [], "re")
    assert sorted(_all_completions(c, "re")) == ["release", "reset"]


def test_completer_completes_key_names_after_press(monkeypatch):
    c = _completer_with_buffer(monkeypatch, ["A", "B", "ESC", "F1"], "press F")
    assert _all_completions(c, "F") == ["F1"]


def test_completer_completes_key_names_after_release(monkeypatch):
    c = _completer_with_buffer(monkeypatch, ["A", "B", "ESC"], "release E")
    assert _all_completions(c, "E") == ["ESC"]


def test_completer_completes_key_names_after_tap(monkeypatch):
    c = _completer_with_buffer(monkeypatch, ["A", "B", "ESC"], "tap A B ")
    assert sorted(_all_completions(c, "")) == ["A", "B", "ESC"]


def test_completer_returns_nothing_for_keyless_commands(monkeypatch):
    c = _completer_with_buffer(monkeypatch, ["A", "B"], "state ")
    assert _all_completions(c, "") == []


def test_completer_no_match_returns_empty(monkeypatch):
    c = _completer_with_buffer(monkeypatch, ["A", "B"], "press Z")
    assert _all_completions(c, "Z") == []


# ---------------------------------------------------------- ascii subcommand

def test_ascii_default_emits_all_profiles_and_layers(capsys):
    cli.main(["ascii", str(FIXTURES_YAML / "KEYMAP_FN_TEST.yaml")])
    out = capsys.readouterr().out
    headers = [l for l in out.splitlines() if l.startswith("Profile ")]
    assert len(headers) == 12


def test_ascii_profile_and_layer_filter(capsys):
    cli.main([
        "ascii",
        str(FIXTURES_YAML / "KEYMAP_FN_TEST.yaml"),
        "--profile", "1",
        "--layer", "fn1",
    ])
    out = capsys.readouterr().out
    headers = [l for l in out.splitlines() if l.startswith("Profile ")]
    assert len(headers) == 1
    assert "fn1" in headers[0]


def test_ascii_no_headers_flag(capsys):
    cli.main([
        "ascii",
        str(FIXTURES_YAML / "KEYMAP_FN_TEST.yaml"),
        "--profile", "1",
        "--layer", "base",
        "--no-headers",
    ])
    out = capsys.readouterr().out
    assert "Profile " not in out


def test_ascii_tex_input_requires_layout():
    with pytest.raises(SystemExit, match="--layout is required"):
        cli.main([
            "ascii",
            str(FIXTURES_TEX / "KEYMAP_FN_TEST.TEX"),
        ])


def test_ascii_show_default_renders_without_file(capsys):
    cli.main(["ascii", "--show-default", "--layout", "ANSI",
              "--profile", "1", "--layer", "base"])
    out = capsys.readouterr().out
    # G12 is the default fn1 trigger so it renders as [FN1] on base.
    assert "[FN1]" in out


def test_ascii_show_default_requires_layout():
    with pytest.raises(SystemExit, match="--layout is required"):
        cli.main(["ascii", "--show-default"])


def test_ascii_show_default_fn1_layer_shows_trackpoint_speeds(capsys):
    cli.main(["ascii", "--show-default", "--layout", "ANSI",
              "--profile", "1", "--layer", "fn1"])
    out = capsys.readouterr().out
    assert "TP_SPEED1" in out
    assert "TP_SPEED9" in out


def test_ascii_without_input_or_show_default_errors():
    with pytest.raises(SystemExit, match="input file is required"):
        cli.main(["ascii", "--layout", "ANSI"])


def test_ascii_key_names_no_file_needed(capsys):
    cli.main(["ascii", "--key-names", "--layout", "ANSI"])
    out = capsys.readouterr().out
    assert " A " in out  # cell for keycode 4
    assert "L_CTRL" in out


def test_ascii_key_ids_renders_numeric_codes(capsys):
    cli.main(["ascii", "--key-ids", "--layout", "ANSI"])
    out = capsys.readouterr().out
    assert " 4 " in out
    assert "230" in out


def test_ascii_key_matrix_renders_positions(capsys):
    cli.main(["ascii", "--key-matrix", "--layout", "ANSI"])
    out = capsys.readouterr().out
    assert "6,4" in out
    assert "0,0" in out


def test_ascii_key_names_requires_layout():
    with pytest.raises(SystemExit, match="--layout is required"):
        cli.main(["ascii", "--key-names"])


def test_ascii_mode_flags_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        cli.main(["ascii", "--key-names", "--key-ids", "--layout", "ANSI"])
    with pytest.raises(SystemExit):
        cli.main(["ascii", "--show-default", "--key-matrix", "--layout", "ANSI"])


# ---------------------------------------------------------- dump subcommand

def test_dump_writes_to_stdout(capsys):
    cli.main([
        "dump",
        str(FIXTURES_TEX / "KEYMAP_EMPTY.TEX"),
        "--layout", "ANSI",
    ])
    out = capsys.readouterr().out
    assert "Header:" in out
    assert "Pointers:" in out
    assert "File:" in out  # default (non-diffable) emits File:/Size: header


def test_dump_diffable_omits_file_header(capsys):
    cli.main([
        "dump",
        str(FIXTURES_TEX / "KEYMAP_EMPTY.TEX"),
        "--layout", "ANSI",
        "--diffable",
    ])
    out = capsys.readouterr().out
    assert "File:" not in out
    assert "Size:" not in out
    # No offset prefixes either.
    assert "0x0000" not in out


def test_dump_requires_layout():
    with pytest.raises(SystemExit, match="--layout is required"):
        cli.main([
            "dump",
            str(FIXTURES_TEX / "KEYMAP_EMPTY.TEX"),
        ])


# ---------------------------------------------------------- diff subcommand

def test_diff_identical_files_produces_no_output(capsys):
    cli.main([
        "diff",
        str(FIXTURES_TEX / "KEYMAP_EMPTY.TEX"),
        str(FIXTURES_TEX / "KEYMAP_EMPTY.TEX"),
        "--layout", "ANSI",
    ])
    assert capsys.readouterr().out == ""


def test_diff_different_files_emits_unified_diff(capsys):
    cli.main([
        "diff",
        str(FIXTURES_TEX / "KEYMAP_EMPTY.TEX"),
        str(FIXTURES_TEX / "KEYMAP_FN_TEST.TEX"),
        "--layout", "ANSI",
    ])
    out = capsys.readouterr().out
    assert out.startswith("--- ")
    assert "+++ " in out
    # Hunk markers in unified format.
    assert "@@ " in out


def test_diff_labels_use_passed_paths(capsys):
    cli.main([
        "diff",
        str(FIXTURES_TEX / "KEYMAP_EMPTY.TEX"),
        str(FIXTURES_TEX / "KEYMAP_FN_TEST.TEX"),
        "--layout", "ANSI",
    ])
    out = capsys.readouterr().out
    assert "KEYMAP_EMPTY.TEX" in out
    assert "KEYMAP_FN_TEST.TEX" in out


def test_diff_requires_layout():
    with pytest.raises(SystemExit, match="--layout is required"):
        cli.main([
            "diff",
            str(FIXTURES_TEX / "KEYMAP_EMPTY.TEX"),
            str(FIXTURES_TEX / "KEYMAP_FN_TEST.TEX"),
        ])


def test_diff_rejects_bad_magic(tmp_path):
    # Hand the diff two files where one isn't a .TEX file at all.
    bad = tmp_path / "bad.bin"
    bad.write_bytes(b"NOPE\x00\x00\x00\x00")
    with pytest.raises(SystemExit, match="bad magic"):
        cli.main([
            "diff", str(bad), str(FIXTURES_TEX / "KEYMAP_EMPTY.TEX"),
            "--layout", "ANSI",
        ])


# ---------------------------------------------------------- actions subcommand

def test_actions_lists_known_names(capsys):
    cli.main(["actions"])
    names = capsys.readouterr().out.splitlines()
    # Includes both a physical key (A) and an action-only keycode (MOUSE_LEFT).
    assert "A" in names
    assert "MOUSE_LEFT" in names
    # No blank lines, no duplicates.
    assert all(n.strip() for n in names)
    assert len(names) == len(set(names))
