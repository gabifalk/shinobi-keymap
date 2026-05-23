# tests/fixtures/__init__.py
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Gabi Falk

"""Test fixture paths and helpers."""

from pathlib import Path

# Base fixtures directory
FIXTURES_DIR = Path(__file__).parent

# Common subdirectories
TEX_DIR = FIXTURES_DIR / "tex_files"
YAML_DIR = FIXTURES_DIR / "yaml"
YAML_EXPECTED_DIR = FIXTURES_DIR / "yaml_expected"
CLI_ASCII_DIR = FIXTURES_DIR / "cli_ascii"
DUMP_EXPECTED_DIR = FIXTURES_DIR / "dump_expected"


def get_tex(name: str) -> Path:
    """Get path to a .TEX fixture file.

    Args:
        name: Filename with or without .TEX extension

    Returns:
        Path to the fixture file
    """
    if not name.endswith(".TEX"):
        name = f"{name}.TEX"
    return TEX_DIR / name


def get_yaml(name: str) -> Path:
    """Get path to a YAML fixture file.

    Args:
        name: Filename with or without .yaml extension

    Returns:
        Path to the fixture file
    """
    if not name.endswith((".yaml", ".yml")):
        name = f"{name}.yaml"
    return YAML_DIR / name


def get_yaml_expected(name: str) -> Path:
    """Get path to an expected YAML fixture file.

    Args:
        name: Filename with or without .yaml extension

    Returns:
        Path to the fixture file
    """
    if not name.endswith((".yaml", ".yml")):
        name = f"{name}.yaml"
    return YAML_EXPECTED_DIR / name
