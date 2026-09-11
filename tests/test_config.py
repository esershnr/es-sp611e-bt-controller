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
