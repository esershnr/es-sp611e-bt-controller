"""Unit tests for the SP611E protocol builder."""

import pytest

from sp611e_cli.protocol import (
    CMD_BRIGHTNESS,
    CMD_POWER,
    CMD_RGB,
    CMD_STATUS,
    HEADER,
    build_command,
    create_turn_off_command,
    create_turn_on_command,
)


def test_turn_on_command() -> None:
    """Test that turn on command generates exact byte sequence A0 62 01 01."""
    cmd = create_turn_on_command()
    expected = bytes([0xA0, 0x62, 0x01, 0x01])
    assert cmd == expected
    assert cmd == b"\xa0\x62\x01\x01"
    assert len(cmd) == 4


def test_turn_off_command() -> None:
    """Test that turn off command generates exact byte sequence A0 62 01 00."""
    cmd = create_turn_off_command()
    expected = bytes([0xA0, 0x62, 0x01, 0x00])
    assert cmd == expected
    assert cmd == b"\xa0\x62\x01\x00"
    assert len(cmd) == 4


def test_build_command_no_payload() -> None:
    """Test building a command with zero payload (e.g. status query A0 70 00)."""
    cmd = build_command(CMD_STATUS)
    assert cmd == bytes([HEADER, CMD_STATUS, 0x00])
    assert cmd == b"\xa0\x70\x00"


def test_build_command_single_byte_payload() -> None:
    """Test building a command with single byte payload (e.g. brightness)."""
    level = 128
    cmd = build_command(CMD_BRIGHTNESS, bytes([level]))
    assert cmd == bytes([HEADER, CMD_BRIGHTNESS, 0x01, level])
    assert cmd == b"\xa0\x66\x01\x80"


def test_build_command_multi_byte_payload() -> None:
    """Test building a command with multi-byte payload (e.g. RGB R, G, B, Brightness)."""
    payload = bytes([255, 128, 0, 200])
    cmd = build_command(CMD_RGB, payload)
    assert cmd == bytes([HEADER, CMD_RGB, 0x04, 255, 128, 0, 200])
    assert len(cmd) == 7


def test_build_command_invalid_code() -> None:
    """Test that invalid command codes outside 0-255 raise ValueError."""
    with pytest.raises(ValueError, match="Invalid command code"):
        build_command(-1)

    with pytest.raises(ValueError, match="Invalid command code"):
        build_command(256)


def test_build_command_payload_too_long() -> None:
    """Test that payloads exceeding 255 bytes raise ValueError."""
    large_payload = bytes([0] * 256)
    with pytest.raises(ValueError, match="Payload length cannot exceed"):
        build_command(CMD_POWER, large_payload)


def test_set_brightness_command() -> None:
    """Test that set brightness generates exact sequence A0 66 01 [level]."""
    from sp611e_cli.protocol import create_set_brightness_command

    cmd_max = create_set_brightness_command(255)
    assert cmd_max == bytes([0xA0, 0x66, 0x01, 0xFF])
    assert cmd_max == b"\xa0\x66\x01\xff"

    cmd_zero = create_set_brightness_command(0)
    assert cmd_zero == bytes([0xA0, 0x66, 0x01, 0x00])

    with pytest.raises(ValueError, match="Brightness level must be between 0 and 255"):
        create_set_brightness_command(-1)
    with pytest.raises(ValueError, match="Brightness level must be between 0 and 255"):
        create_set_brightness_command(256)


def test_set_rgb_command() -> None:
    """Test that set RGB generates exact sequence A0 69 04 [R] [G] [B] [brightness]."""
    from sp611e_cli.protocol import create_set_rgb_command

    # Red with default full brightness 255
    cmd_red = create_set_rgb_command(255, 0, 0)
    assert cmd_red == bytes([0xA0, 0x69, 0x04, 0xFF, 0x00, 0x00, 0xFF])

    # Green with 128 brightness
    cmd_green = create_set_rgb_command(0, 255, 0, brightness=128)
    assert cmd_green == bytes([0xA0, 0x69, 0x04, 0x00, 0xFF, 0x00, 0x80])

    # Blue
    cmd_blue = create_set_rgb_command(0, 0, 255, brightness=200)
    assert cmd_blue == bytes([0xA0, 0x69, 0x04, 0x00, 0x00, 0xFF, 200])

    with pytest.raises(ValueError, match="Red value must be between 0 and 255"):
        create_set_rgb_command(300, 0, 0)
    with pytest.raises(ValueError, match="Brightness value must be between 0 and 255"):
        create_set_rgb_command(0, 0, 0, brightness=-5)


def test_set_effect_command() -> None:
    """Test that set effect generates exact sequence A0 63 01 [effect_id]."""
    from sp611e_cli.protocol import create_set_effect_command

    cmd_1 = create_set_effect_command(1)
    assert cmd_1 == bytes([0xA0, 0x63, 0x01, 0x01])

    cmd_42 = create_set_effect_command(42)
    assert cmd_42 == bytes([0xA0, 0x63, 0x01, 42])

    with pytest.raises(ValueError, match="Effect ID must be between 1 and 255"):
        create_set_effect_command(0)
    with pytest.raises(ValueError, match="Effect ID must be between 1 and 255"):
        create_set_effect_command(256)


def test_static_color_mode_command() -> None:
    """Static color mode is effect 0xBE: A0 63 01 BE."""
    from sp611e_cli.protocol import EFFECT_SOLID_COLOR, create_static_color_mode_command

    assert EFFECT_SOLID_COLOR == 0xBE
    assert create_static_color_mode_command() == bytes([0xA0, 0x63, 0x01, 0xBE])


def test_set_static_color_commands_sequence() -> None:
    """Static color must be preceded by the solid-mode switch so a running effect stops."""
    from sp611e_cli.protocol import create_set_static_color_commands

    frames = create_set_static_color_commands(0, 240, 255, brightness=26)
    assert frames == [
        bytes([0xA0, 0x63, 0x01, 0xBE]),
        bytes([0xA0, 0x69, 0x04, 0x00, 0xF0, 0xFF, 0x1A]),
    ]

    # Default brightness is full
    frames_default = create_set_static_color_commands(255, 0, 0)
    assert frames_default[1] == bytes([0xA0, 0x69, 0x04, 0xFF, 0x00, 0x00, 0xFF])

    with pytest.raises(ValueError, match="Green value must be between 0 and 255"):
        create_set_static_color_commands(0, 256, 0)


def test_create_state_commands_color_and_brightness() -> None:
    """--color + --brightness: mode switch, RGB with level folded in, then brightness frame."""
    from sp611e_cli.protocol import create_state_commands

    frames = create_state_commands(rgb=(255, 0, 0), brightness=10)
    assert frames == [
        bytes([0xA0, 0x63, 0x01, 0xBE]),
        bytes([0xA0, 0x69, 0x04, 0xFF, 0x00, 0x00, 10]),
        bytes([0xA0, 0x66, 0x01, 10]),
    ]


def test_create_state_commands_full_ordering() -> None:
    """Power on first, effect, speed, brightness, and power off last."""
    from sp611e_cli.protocol import create_state_commands

    frames = create_state_commands(power=True, effect_id=5, speed=8, brightness=200)
    assert frames == [
        bytes([0xA0, 0x62, 0x01, 0x01]),
        bytes([0xA0, 0x63, 0x01, 0x05]),
        bytes([0xA0, 0x67, 0x01, 0x08]),
        bytes([0xA0, 0x66, 0x01, 200]),
    ]

    frames_off = create_state_commands(rgb=(1, 2, 3), power=False)
    assert frames_off[-1] == bytes([0xA0, 0x62, 0x01, 0x00])
    assert frames_off[0] == bytes([0xA0, 0x63, 0x01, 0xBE])


def test_create_state_commands_validation() -> None:
    from sp611e_cli.protocol import create_state_commands

    with pytest.raises(ValueError, match="aynı anda"):
        create_state_commands(rgb=(1, 2, 3), effect_id=4)
    with pytest.raises(ValueError, match="en az bir ayar"):
        create_state_commands()
    with pytest.raises(ValueError, match="Effect speed"):
        create_state_commands(speed=11)


def test_set_speed_command() -> None:
    """Test that set speed generates exact sequence A0 67 01 [speed]."""
    from sp611e_cli.protocol import create_set_speed_command

    cmd_1 = create_set_speed_command(1)
    assert cmd_1 == bytes([0xA0, 0x67, 0x01, 0x01])

    cmd_10 = create_set_speed_command(10)
    assert cmd_10 == bytes([0xA0, 0x67, 0x01, 10])

    with pytest.raises(ValueError, match="Effect speed must be between 1 and 10"):
        create_set_speed_command(0)
    with pytest.raises(ValueError, match="Effect speed must be between 1 and 10"):
        create_set_speed_command(11)


