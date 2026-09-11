"""Unit tests for configuration management."""

from pathlib import Path
from unittest.mock import patch

from sp611e_cli.config import get_default_mac, load_config, save_default_mac


def test_config_save_and_load(tmp_path: Path) -> None:
    """Test saving MAC address to config and loading it back."""
    test_config_file = tmp_path / "config.toml"
    test_config_dir = tmp_path

    with patch("sp611e_cli.config.CONFIG_DIR", test_config_dir), \
         patch("sp611e_cli.config.CONFIG_FILE", test_config_file):

        # Initially, no config
        assert load_config() == {}
        assert get_default_mac() is None

        # Save MAC
        save_default_mac("aa:bb:cc:dd:ee:ff")

        # Config file should exist
        assert test_config_file.is_file()

        # Should load and normalize uppercase
        cfg = load_config()
        assert cfg["device"]["mac"] == "AA:BB:CC:DD:EE:FF"
        assert get_default_mac() == "AA:BB:CC:DD:EE:FF"


def test_openrgb_defaults_roundtrip_and_preserve_mac(tmp_path: Path) -> None:
    """[openrgb] defaults are saved/merged without clobbering [device], and vice versa."""
    from sp611e_cli.config import get_openrgb_defaults, save_openrgb_defaults

    with patch("sp611e_cli.config.CONFIG_DIR", tmp_path), \
         patch("sp611e_cli.config.CONFIG_FILE", tmp_path / "config.toml"):
        save_default_mac("AA:BB:CC:DD:EE:FF")
        assert get_openrgb_defaults() == {}

        saved = save_openrgb_defaults(device="ASUS Aura", zone="RGB Header", brightness=30, fps=15.0, power_on=False)
        assert saved == {"device": "ASUS Aura", "zone": "RGB Header", "brightness": 30, "fps": 15.0, "power_on": False}
        assert get_default_mac() == "AA:BB:CC:DD:EE:FF"

        # Merge: only given keys change; None removes a key.
        save_openrgb_defaults(pick="brightest", zone=None)
        assert get_openrgb_defaults() == {"device": "ASUS Aura", "pick": "brightest", "brightness": 30, "fps": 15.0, "power_on": False}

        # Re-saving the MAC keeps the openrgb section.
        save_default_mac("11:22:33:44:55:66")
        assert get_default_mac() == "11:22:33:44:55:66"
        assert get_openrgb_defaults()["device"] == "ASUS Aura"

        text = (tmp_path / "config.toml").read_text(encoding="utf-8")
        assert "[device]" in text and "[openrgb]" in text and "power_on = false" in text


def test_openrgb_defaults_reject_unknown_key_and_escape_quotes(tmp_path: Path) -> None:
    import pytest

    from sp611e_cli.config import get_openrgb_defaults, save_openrgb_defaults

    with patch("sp611e_cli.config.CONFIG_DIR", tmp_path), \
         patch("sp611e_cli.config.CONFIG_FILE", tmp_path / "config.toml"):
        with pytest.raises(ValueError, match="Bilinmeyen"):
            save_openrgb_defaults(colour="red")
        name = 'My "RGB" Strip' + chr(92) + 'v2'  # quotes and a backslash
        save_openrgb_defaults(device=name)
        assert get_openrgb_defaults()["device"] == name
