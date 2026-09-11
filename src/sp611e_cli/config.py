"""Configuration management for SP611E CLI.

Stores and retrieves persistent user preferences, such as the default MAC address,
in ~/.sp611e/config.toml.
"""

from pathlib import Path
import tomllib
from typing import Any, Dict, Optional

CONFIG_DIR: Path = Path.home() / ".sp611e"
CONFIG_FILE: Path = CONFIG_DIR / "config.toml"


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


def get_default_mac() -> Optional[str]:
    """Get the saved default MAC address if present."""
    config = load_config()
    mac = config.get("device", {}).get("mac")
    if mac and isinstance(mac, str):
        return mac.strip().upper()
    return None


def save_default_mac(mac_address: str) -> None:
    """Save the default MAC address to config.toml.

    Args:
        mac_address: The Bluetooth MAC address or device address string.
    """
    cleaned_mac = mac_address.strip().upper()
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    content = (
        "# SP611E CLI Configuration\n\n"
        "[device]\n"
        f'mac = "{cleaned_mac}"\n'
    )
    CONFIG_FILE.write_text(content, encoding="utf-8")
