"""Unit tests for the color parsing utility."""

import pytest

from sp611e_cli.colors import parse_color, parse_hex_color


def test_parse_named_colors() -> None:
    """Test parsing named colors (case-insensitive, dash or underscore)."""
    assert parse_color(["red"]) == (255, 0, 0)
    assert parse_color(["GREEN"]) == (0, 255, 0)
    assert parse_color(["blue"]) == (0, 0, 255)
    assert parse_color(["warm-white"]) == (255, 214, 170)
    assert parse_color(["warm_white"]) == (255, 214, 170)
    assert parse_color(["cool-white"]) == (200, 225, 255)


def test_parse_hex_color_6_char() -> None:
    """Test parsing standard 6-character hex colors."""
    assert parse_hex_color("#FF5733") == (255, 87, 51)
    assert parse_hex_color("00FF00") == (0, 255, 0)
    assert parse_color(["#0000FF"]) == (0, 0, 255)


def test_parse_hex_color_3_char() -> None:
    """Test parsing shorthand 3-character hex colors."""
    assert parse_hex_color("#F00") == (255, 0, 0)
    assert parse_hex_color("0F0") == (0, 255, 0)
    assert parse_color(["#00F"]) == (0, 0, 255)


def test_parse_comma_separated() -> None:
    """Test parsing comma-separated RGB values."""
    assert parse_color(["255,128,0"]) == (255, 128, 0)
    assert parse_color(["0, 255, 100"]) == (0, 255, 100)


def test_parse_three_args() -> None:
    """Test parsing three separate CLI arguments."""
    assert parse_color(["255", "128", "64"]) == (255, 128, 64)


def test_parse_invalid_values() -> None:
    """Test error handling for invalid color strings."""
    with pytest.raises(ValueError, match="Bilinmeyen renk"):
        parse_color(["not-a-real-color-1234"])

    with pytest.raises(ValueError, match="Geçersiz hex"):
        parse_hex_color("#GG0011")

    with pytest.raises(ValueError, match="0-255"):
        parse_color(["300", "0", "0"])

    with pytest.raises(ValueError, match="Renk parametresi belirtilmedi"):
        parse_color([])
