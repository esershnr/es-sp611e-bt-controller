"""Configuration management for SP611E CLI.

Stores and retrieves persistent user preferences in ~/.sp611e/config.toml:

    [device]
    mac = "AA:BB:CC:DD:EE:FF"

    [openrgb]              # defaults for `sp611e openrgb` (all optional)
    device = "ASUS Aura"
    zone = "RGB Header"
    pick = "avg"
    fps = 10.0
    brightness = 30
    idle_timeout = 30.0
    power_on = true
    host = "127.0.0.1"
    port = 6742
"""

from pathlib import Path
import tomllib
from typing import Any, Dict, Optional

CONFIG_DIR: Path = Path.home() / ".sp611e"
CONFIG_FILE: Path = CONFIG_DIR / "config.toml"

# Keys accepted in the [openrgb] section (anything else is ignored on read).
OPENRGB_KEYS = ("device", "zone", "pick", "fps", "brightness", "idle_timeout", "power_on", "host", "port")


def get_config_path() -> Path:
    """Return the path to the configuration file."""
    return CONFIG_FILE


def load_config() -> Dict[str, Any]:
    """Load configuration from config.toml.

    Returns:
        Dictionary containing configuration values or empty dict if not found/invalid.
    """
    if not CONFIG_FILE.is_file():
        return {}
    try:
        with open(CONFIG_FILE, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def save_config(config: Dict[str, Dict[str, Any]]) -> None:
    """Write the whole configuration (a dict of flat sections) to config.toml.

    Only scalar values (str, bool, int, float) are supported; None values are skipped.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    lines = ["# SP611E CLI Configuration", ""]
    for section, values in config.items():
        entries = [(k, v) for k, v in values.items() if v is not None]
        if not entries:
            continue
        lines.append(f"[{section}]")
        for key, value in entries:
            lines.append(f"{key} = {_toml_scalar(value)}")
        lines.append("")
    CONFIG_FILE.write_text("\n".join(lines), encoding="utf-8")


def update_section(section: str, values: Dict[str, Any]) -> Dict[str, Any]:
    """Merge values into one section (None removes a key) and persist; returns the new section."""
    config = load_config()
    current = dict(config.get(section, {}))
    for key, value in values.items():
        if value is None:
            current.pop(key, None)
        else:
            current[key] = value
    config[section] = current
    save_config(config)
    return current


def _toml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def get_default_mac() -> Optional[str]:
    """Get the saved default MAC address if present."""
    config = load_config()
    mac = config.get("device", {}).get("mac")
    if mac and isinstance(mac, str):
        return mac.strip().upper()
    return None


def save_default_mac(mac_address: str) -> None:
    """Save the default MAC address to config.toml (other sections are preserved).

    Args:
        mac_address: The Bluetooth MAC address or device address string.
    """
    update_section("device", {"mac": mac_address.strip().upper()})


def get_openrgb_defaults() -> Dict[str, Any]:
    """Return the saved [openrgb] defaults (only known keys)."""
    section = load_config().get("openrgb", {})
    if not isinstance(section, dict):
        return {}
    return {k: section[k] for k in OPENRGB_KEYS if k in section}


def save_openrgb_defaults(**values: Any) -> Dict[str, Any]:
    """Merge the given [openrgb] defaults into config.toml; None values are removed."""
    unknown = set(values) - set(OPENRGB_KEYS)
    if unknown:
        raise ValueError(f"Bilinmeyen openrgb ayarı: {', '.join(sorted(unknown))}")
    return update_section("openrgb", values)
