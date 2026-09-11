"""SP611E BLE RGB LED Controller Protocol Module.

This module handles constructing command byte payloads for the SP611E (BanlanX)
controller. It is completely decoupled from any BLE or I/O libraries for easy
unit testing.

Protocol Structure:
    Header:         0xA0
    Command Code:   1 byte
    Payload Length: 1 byte (number of payload bytes)
    Payload:        0 or more bytes
"""

from typing import Final, Optional, Tuple

# Protocol Constants
HEADER: Final[int] = 0xA0

# Command Codes
CMD_POWER: Final[int] = 0x62
CMD_STATUS: Final[int] = 0x70
CMD_BRIGHTNESS: Final[int] = 0x66
CMD_RGB: Final[int] = 0x69
CMD_EFFECT: Final[int] = 0x63
CMD_SPEED: Final[int] = 0x67

# Special Effect IDs
# On the SP611E "static color" is not a separate command; it is an effect/mode
# that must be selected with CMD_EFFECT before CMD_RGB has any visible effect.
# While a dynamic effect (0x01-0x8E) or sound effect (0xC9-0xDA) is running,
# CMD_RGB only updates the stored color register and the animation keeps going.
EFFECT_SOLID_COLOR: Final[int] = 0xBE
EFFECT_SOLID_WHITE: Final[int] = 0xBF


def build_command(cmd_code: int, payload: bytes = b"") -> bytes:
    """Build a raw SP611E protocol frame.

    Args:
        cmd_code: Single byte integer (0-255) specifying the command.
        payload: Optional bytes payload for the command.

    Returns:
        Raw bytes frame ready to be sent to the write characteristic.
    """
    if not (0 <= cmd_code <= 255):
        raise ValueError(f"Invalid command code: {cmd_code}. Must be between 0 and 255.")
    if len(payload) > 255:
        raise ValueError(f"Payload length cannot exceed 255 bytes (got {len(payload)}).")

    return bytes([HEADER, cmd_code, len(payload)]) + payload


def create_turn_on_command() -> bytes:
    """Generate command bytes to turn ON the SP611E controller.

    Command frame: A0 62 01 01

    Returns:
        bytes: b'\\xa0\\x62\\x01\\x01'
    """
    return build_command(CMD_POWER, bytes([0x01]))


def create_turn_off_command() -> bytes:
    """Generate command bytes to turn OFF the SP611E controller.

    Command frame: A0 62 01 00

    Returns:
        bytes: b'\\xa0\\x62\\x01\\x00'
    """
    return build_command(CMD_POWER, bytes([0x00]))


def create_set_brightness_command(level: int) -> bytes:
    """Generate command bytes to set brightness level (0-255).

    Command frame: A0 66 01 [level]

    Args:
        level: Brightness level from 0 (min/off) to 255 (max).

    Returns:
        bytes: b'\xa0\x66\x01[level]'
    """
    if not (0 <= level <= 255):
        raise ValueError(f"Brightness level must be between 0 and 255 (got {level}).")
    return build_command(CMD_BRIGHTNESS, bytes([level]))


def create_set_rgb_command(red: int, green: int, blue: int, brightness: int = 255) -> bytes:
    """Generate command bytes to set static RGB color with brightness.

    Command frame: A0 69 04 [R] [G] [B] [brightness]

    Args:
        red: Red component (0-255).
        green: Green component (0-255).
        blue: Blue component (0-255).
        brightness: Brightness component (0-255, default 255).

    Returns:
        bytes: b'\xa0\x69\x04[R][G][B][brightness]'
    """
    for name, val in [("Red", red), ("Green", green), ("Blue", blue), ("Brightness", brightness)]:
        if not (0 <= val <= 255):
            raise ValueError(f"{name} value must be between 0 and 255 (got {val}).")

    return build_command(CMD_RGB, bytes([red, green, blue, brightness]))


def create_static_color_mode_command() -> bytes:
    """Generate command bytes to switch the controller into static (solid) color mode.

    Command frame: A0 63 01 BE

    Returns:
        bytes: b'\\xa0\\x63\\x01\\xbe'
    """
    return build_command(CMD_EFFECT, bytes([EFFECT_SOLID_COLOR]))


def create_set_static_color_commands(
    red: int, green: int, blue: int, brightness: int = 255
) -> list[bytes]:
    """Generate the full command sequence needed to display a static RGB color.

    The SP611E keeps running the active dynamic effect if only CMD_RGB is sent,
    so the sequence first selects the solid-color mode and then applies the color:

        A0 63 01 BE
        A0 69 04 [R] [G] [B] [brightness]

    Args:
        red: Red component (0-255).
        green: Green component (0-255).
        blue: Blue component (0-255).
        brightness: Brightness component (0-255, default 255).

    Returns:
        list[bytes]: Frames to send in order over a single connection.
    """
    return [
        create_static_color_mode_command(),
        create_set_rgb_command(red, green, blue, brightness=brightness),
    ]


def create_state_commands(
    *,
    power: Optional[bool] = None,
    rgb: Optional[Tuple[int, int, int]] = None,
    brightness: Optional[int] = None,
    effect_id: Optional[int] = None,
    speed: Optional[int] = None,
) -> list[bytes]:
    """Compose the frames for applying several settings in one connection.

    Frames are ordered so that the strip ends up in the requested state:

        1. power on              (A0 62 01 01)        if power is True
        2. effect                (A0 63 01 id)        if effect_id given
        3. speed                 (A0 67 01 s)         if speed given
        4. static color          (A0 63 01 BE + A0 69 04 R G B L) if rgb given
        5. brightness            (A0 66 01 b)         if brightness given
        6. power off             (A0 62 01 00)        if power is False

    When both rgb and brightness are given, brightness is also folded into the
    level byte of the RGB frame. rgb and effect_id are mutually exclusive
    because static color is itself an effect (see EFFECT_SOLID_COLOR).

    Raises:
        ValueError: On conflicting or out-of-range values, or when nothing is requested.
    """
    if rgb is not None and effect_id is not None:
        raise ValueError("Statik renk ve dinamik efekt aynı anda seçilemez (renk = efekt 0xBE).")

    frames: list[bytes] = []
    if power is True:
        frames.append(create_turn_on_command())
    if effect_id is not None:
        frames.append(create_set_effect_command(effect_id))
    if speed is not None:
        frames.append(create_set_speed_command(speed))
    if rgb is not None:
        level = 255 if brightness is None else brightness
        frames.extend(create_set_static_color_commands(*rgb, brightness=level))
    if brightness is not None:
        frames.append(create_set_brightness_command(brightness))
    if power is False:
        frames.append(create_turn_off_command())

    if not frames:
        raise ValueError("Uygulanacak en az bir ayar belirtilmelidir.")
    return frames


def create_set_effect_command(effect_id: int) -> bytes:
    """Generate command bytes to select dynamic lighting effect (1-255).

    Command frame: A0 63 01 [effect_id]

    Args:
        effect_id: Effect ID integer (typically 1-142 or 1-255).

    Returns:
        bytes: b'\xa0\x63\x01[effect_id]'
    """
    if not (1 <= effect_id <= 255):
        raise ValueError(f"Effect ID must be between 1 and 255 (got {effect_id}).")
    return build_command(CMD_EFFECT, bytes([effect_id]))


def create_set_speed_command(speed: int) -> bytes:
    """Generate command bytes to set effect speed (1-10).

    Command frame: A0 67 01 [speed]

    Args:
        speed: Speed integer from 1 (slowest) to 10 (fastest).

    Returns:
        bytes: b'\xa0\x67\x01[speed]'
    """
    if not (1 <= speed <= 10):
        raise ValueError(f"Effect speed must be between 1 and 10 (got {speed}).")
    return build_command(CMD_SPEED, bytes([speed]))

