"""Color parsing utility for SP611E CLI.

Supports named colors, Hex codes (#RRGGBB, #RGB), and integer RGB components.
"""

from typing import Dict, Sequence, Tuple

NAMED_COLORS: Dict[str, Tuple[int, int, int]] = {
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "white": (255, 255, 255),
    "warm-white": (255, 214, 170),
    "warmwhite": (255, 214, 170),
    "cool-white": (200, 225, 255),
    "coolwhite": (200, 225, 255),
    "yellow": (255, 255, 0),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "orange": (255, 128, 0),
    "purple": (128, 0, 128),
    "pink": (255, 105, 180),
    "violet": (238, 130, 238),
    "indigo": (75, 0, 130),
    "lime": (50, 205, 50),
    "teal": (0, 128, 128),
    "turquoise": (64, 224, 208),
    "gold": (255, 215, 0),
}


def parse_hex_color(hex_str: str) -> Tuple[int, int, int]:
    """Parse a hex color string like '#FF0000' or 'FF0000' or '#F00'."""
    cleaned = hex_str.strip().lstrip("#")
    if len(cleaned) == 3:
        # Expand 3-character hex (e.g. F00 -> FF0000)
        cleaned = "".join(c * 2 for c in cleaned)

    if len(cleaned) != 6:
        raise ValueError(f"Geçersiz hex renk formatı: '{hex_str}'. (Örnek: '#FF5733' veya '#F00')")

    try:
        r = int(cleaned[0:2], 16)
        g = int(cleaned[2:4], 16)
        b = int(cleaned[4:6], 16)
        return r, g, b
    except ValueError as exc:
        raise ValueError(f"Geçersiz hex karakterleri: '{hex_str}'") from exc


def parse_color(color_tokens: Sequence[str]) -> Tuple[int, int, int]:
    """Parse color from CLI tokens.

    Supports:
        - Named color: 'red', 'green', 'warm-white'
        - Hex color: '#FF5733', '00FF00', '#F00'
        - Comma separated: '255,128,0'
        - 3 separate arguments: '255' '128' '0'

    Returns:
        Tuple of (red, green, blue) as integers 0-255.
    """
    if not color_tokens:
        raise ValueError(
            "Renk parametresi belirtilmedi!\n"
            "Kullanım örnekleri:\n"
            "  sp611e color red\n"
            "  sp611e color '#FF5733'\n"
            "  sp611e color 255 128 0"
        )

    # Case 1: 3 separate arguments (e.g. 255 128 0)
    if len(color_tokens) == 3:
        try:
            r = int(color_tokens[0])
            g = int(color_tokens[1])
            b = int(color_tokens[2])
        except ValueError as exc:
            raise ValueError(f"RGB değerleri sayı olmalıdır: {' '.join(color_tokens)}") from exc

        for name, val in [("Kırmızı", r), ("Yeşil", g), ("Mavi", b)]:
            if not (0 <= val <= 255):
                raise ValueError(f"{name} değeri 0-255 aralığında olmalıdır (girilen: {val})")
        return r, g, b

    # Case 2: Single argument
    if len(color_tokens) == 1:
        token = color_tokens[0].strip()

        # Comma-separated (e.g. 255,128,0)
        if "," in token:
            parts = [p.strip() for p in token.split(",")]
            if len(parts) == 3:
                return parse_color(parts)
            raise ValueError(f"Virgülle ayrılmış RGB değeri 3 sayı içermelidir (örn: 255,128,0), girilen: '{token}'")

        # Named color
        normalized_name = token.lower().replace("_", "-")
        if normalized_name in NAMED_COLORS:
            return NAMED_COLORS[normalized_name]

        # Hex code (starts with # or 3/6 hex chars)
        if token.startswith("#") or len(token) in (3, 6):
            return parse_hex_color(token)

        known_list = ", ".join(sorted(list(set(NAMED_COLORS.keys()))[:8])) + "..."
        raise ValueError(
            f"Bilinmeyen renk formatı veya adı: '{token}'.\n"
            f"Desteklenen örnek isimler: {known_list}\n"
            "Veya Hex: '#FF0000', RGB: 255 0 0"
        )

    raise ValueError(f"Geçersiz renk parametresi sayısı ({len(color_tokens)} adet verildi).")
