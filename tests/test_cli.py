"""Unit tests for the CLI commands using Click CliRunner."""

from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from sp611e_cli.cli import main
from sp611e_cli.device import DiscoveredDevice


def test_cli_help() -> None:
    """Test root --help command."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "SP611E (BanlanX) Bluetooth LE RGB LED Kontrolcüsü" in result.output
    assert "scan" in result.output
    assert "on" in result.output
    assert "off" in result.output
    assert "config" in result.output


def test_on_without_mac() -> None:
    """Test on command fails gracefully when no MAC is provided or saved."""
    runner = CliRunner()
    with patch("sp611e_cli.cli.get_default_mac", return_value=None):
        result = runner.invoke(main, ["on"])
        assert result.exit_code != 0
        assert "Hata: MAC adresi belirtilmedi!" in result.output


def test_on_with_mac_success() -> None:
    """Test on command with valid MAC executes send_command."""
    runner = CliRunner()
    with patch("sp611e_cli.cli.SP611EController.send_command", new_callable=AsyncMock) as mock_send:
        result = runner.invoke(main, ["--mac", "AA:BB:CC:DD:EE:FF", "on"])
        assert result.exit_code == 0
        assert "✓ Başarılı: AA:BB:CC:DD:EE:FF cihazı açıldı." in result.output
        mock_send.assert_awaited_once()


def test_off_with_mac_success() -> None:
    """Test off command with valid MAC executes send_command."""
    runner = CliRunner()
    with patch("sp611e_cli.cli.SP611EController.send_command", new_callable=AsyncMock) as mock_send:
        result = runner.invoke(main, ["--mac", "AA:BB:CC:DD:EE:FF", "off"])
        assert result.exit_code == 0
        assert "✓ Başarılı: AA:BB:CC:DD:EE:FF cihazı kapatıldı." in result.output
        mock_send.assert_awaited_once()


def test_scan_command() -> None:
    """Test scan command lists detected SP611E devices."""
    mock_devices = [
        DiscoveredDevice(
            address="AA:BB:CC:DD:EE:FF",
            name="SP611E_1234",
            rssi=-65,
            is_sp611e=True,
        )
    ]
    runner = CliRunner()
    with patch("sp611e_cli.cli.scan_devices", new_callable=AsyncMock, return_value=mock_devices):
        result = runner.invoke(main, ["scan"])
        assert result.exit_code == 0
        assert "AA:BB:CC:DD:EE:FF" in result.output
        assert "SP611E_1234" in result.output
        assert "[SP611E]" in result.output


def test_brightness_command() -> None:
    """Test brightness command with level and percentage."""
    runner = CliRunner()
    with patch("sp611e_cli.cli.SP611EController.send_command", new_callable=AsyncMock) as mock_send:
        result = runner.invoke(main, ["--mac", "AA:BB:CC:DD:EE:FF", "brightness", "128"])
        assert result.exit_code == 0
        assert "128/255" in result.output
        mock_send.assert_awaited_once()

    # Percentage
    with patch("sp611e_cli.cli.SP611EController.send_command", new_callable=AsyncMock) as mock_send:
        result = runner.invoke(main, ["--mac", "AA:BB:CC:DD:EE:FF", "brightness", "50%"])
        assert result.exit_code == 0
        assert "128/255" in result.output
        mock_send.assert_awaited_once()


def test_color_command() -> None:
    """Test color command with named color and hex."""
    runner = CliRunner()
    with patch("sp611e_cli.cli.SP611EController.send_commands", new_callable=AsyncMock) as mock_send:
        result = runner.invoke(main, ["--mac", "AA:BB:CC:DD:EE:FF", "color", "red"])
        assert result.exit_code == 0
        assert "#FF0000" in result.output
        mock_send.assert_awaited_once()
        # Solid-mode switch must precede the RGB frame, in one connection.
        assert list(mock_send.await_args.args[0]) == [
            bytes([0xA0, 0x63, 0x01, 0xBE]),
            bytes([0xA0, 0x69, 0x04, 0xFF, 0x00, 0x00, 0xFF]),
        ]

    with patch("sp611e_cli.cli.SP611EController.send_commands", new_callable=AsyncMock) as mock_send:
        result = runner.invoke(main, ["--mac", "AA:BB:CC:DD:EE:FF", "color", "#00FF00", "-b", "100"])
        assert result.exit_code == 0
        assert "#00FF00" in result.output
        mock_send.assert_awaited_once()
        assert list(mock_send.await_args.args[0])[1] == bytes([0xA0, 0x69, 0x04, 0x00, 0xFF, 0x00, 100])


def test_effect_command() -> None:
    """Test effect command with and without speed."""
    runner = CliRunner()
    with patch("sp611e_cli.cli.SP611EController.send_commands", new_callable=AsyncMock) as mock_send:
        result = runner.invoke(main, ["--mac", "AA:BB:CC:DD:EE:FF", "effect", "5"])
        assert result.exit_code == 0
        assert "efekti 5 olarak ayarlandı" in result.output
        mock_send.assert_awaited_once()
        assert list(mock_send.await_args.args[0]) == [bytes([0xA0, 0x63, 0x01, 0x05])]

    # With speed option: both frames in a single connection
    with patch("sp611e_cli.cli.SP611EController.send_commands", new_callable=AsyncMock) as mock_send:
        result = runner.invoke(main, ["--mac", "AA:BB:CC:DD:EE:FF", "effect", "10", "-s", "8"])
        assert result.exit_code == 0
        assert "efekti 10 olarak ayarlandı" in result.output
        assert "hızı 8/10" in result.output
        mock_send.assert_awaited_once()
        assert list(mock_send.await_args.args[0]) == [
            bytes([0xA0, 0x63, 0x01, 0x0A]),
            bytes([0xA0, 0x67, 0x01, 0x08]),
        ]


def test_speed_command() -> None:
    """Test speed command valid and invalid ranges."""
    runner = CliRunner()
    with patch("sp611e_cli.cli.SP611EController.send_command", new_callable=AsyncMock) as mock_send:
        result = runner.invoke(main, ["--mac", "AA:BB:CC:DD:EE:FF", "speed", "7"])
        assert result.exit_code == 0
        assert "hızı 7/10 olarak ayarlandı" in result.output
        mock_send.assert_awaited_once()

    result_invalid = runner.invoke(main, ["--mac", "AA:BB:CC:DD:EE:FF", "speed", "15"])
    assert result_invalid.exit_code != 0
    assert "1 ile 10 arasında" in result_invalid.output




def test_set_command_color_and_brightness() -> None:
    """`sp611e set --color red --brightness 10` sends all frames over one connection."""
    runner = CliRunner()
    with patch("sp611e_cli.cli.SP611EController.send_commands", new_callable=AsyncMock) as mock_send:
        result = runner.invoke(
            main, ["--mac", "AA:BB:CC:DD:EE:FF", "set", "--color", "red", "--brightness", "10"]
        )
        assert result.exit_code == 0, result.output
        assert "renk: #FF0000" in result.output
        assert "parlaklık: 10/255" in result.output
        mock_send.assert_awaited_once()
        assert list(mock_send.await_args.args[0]) == [
            bytes([0xA0, 0x63, 0x01, 0xBE]),
            bytes([0xA0, 0x69, 0x04, 0xFF, 0x00, 0x00, 10]),
            bytes([0xA0, 0x66, 0x01, 10]),
        ]


def test_root_shortcut_without_subcommand() -> None:
    """`sp611e --color red --brightness 10` (no subcommand) behaves like `set`."""
    runner = CliRunner()
    with patch("sp611e_cli.cli.SP611EController.send_commands", new_callable=AsyncMock) as mock_send:
        result = runner.invoke(
            main, ["--mac", "AA:BB:CC:DD:EE:FF", "--on", "--color", "#00FF00", "-b", "80%"]
        )
        assert result.exit_code == 0, result.output
        mock_send.assert_awaited_once()
        assert list(mock_send.await_args.args[0]) == [
            bytes([0xA0, 0x62, 0x01, 0x01]),
            bytes([0xA0, 0x63, 0x01, 0xBE]),
            bytes([0xA0, 0x69, 0x04, 0x00, 0xFF, 0x00, 204]),
            bytes([0xA0, 0x66, 0x01, 204]),
        ]

    # Root with no options and no subcommand just prints help.
    result_help = runner.invoke(main, [])
    assert result_help.exit_code == 0
    assert "Usage:" in result_help.output


def test_set_command_effect_and_speed() -> None:
    runner = CliRunner()
    with patch("sp611e_cli.cli.SP611EController.send_commands", new_callable=AsyncMock) as mock_send:
        result = runner.invoke(main, ["--mac", "AA:BB:CC:DD:EE:FF", "set", "-e", "5", "-s", "8", "--off"])
        assert result.exit_code == 0, result.output
        assert list(mock_send.await_args.args[0]) == [
            bytes([0xA0, 0x63, 0x01, 0x05]),
            bytes([0xA0, 0x67, 0x01, 0x08]),
            bytes([0xA0, 0x62, 0x01, 0x00]),
        ]


def test_set_command_rejects_conflicts() -> None:
    runner = CliRunner()
    with patch("sp611e_cli.cli.SP611EController.send_commands", new_callable=AsyncMock) as mock_send:
        result = runner.invoke(main, ["--mac", "AA:BB:CC:DD:EE:FF", "set", "--color", "red", "--effect", "3"])
        assert result.exit_code != 0
        assert "aynı anda" in result.output
        mock_send.assert_not_awaited()

        result = runner.invoke(main, ["--mac", "AA:BB:CC:DD:EE:FF", "set", "--on", "--off"])
        assert result.exit_code != 0
        assert "--on ve --off" in result.output

        result = runner.invoke(main, ["--mac", "AA:BB:CC:DD:EE:FF", "set", "--brightness", "300"])
        assert result.exit_code != 0
        assert "0 ile 255" in result.output
        mock_send.assert_not_awaited()


def test_set_command_rgb_components() -> None:
    """`--rgb 0 0 255` accepts three separate components."""
    runner = CliRunner()
    with patch("sp611e_cli.cli.SP611EController.send_commands", new_callable=AsyncMock) as mock_send:
        result = runner.invoke(main, ["--mac", "AA:BB:CC:DD:EE:FF", "--rgb", "0", "0", "255", "-b", "10"])
        assert result.exit_code == 0, result.output
        assert "renk: #0000FF" in result.output
        assert list(mock_send.await_args.args[0]) == [
            bytes([0xA0, 0x63, 0x01, 0xBE]),
            bytes([0xA0, 0x69, 0x04, 0x00, 0x00, 0xFF, 10]),
            bytes([0xA0, 0x66, 0x01, 10]),
        ]

    with patch("sp611e_cli.cli.SP611EController.send_commands", new_callable=AsyncMock) as mock_send:
        result = runner.invoke(main, ["--mac", "AA:BB:CC:DD:EE:FF", "set", "--rgb", "0", "0", "300"])
        assert result.exit_code != 0
        mock_send.assert_not_awaited()

        result = runner.invoke(main, ["--mac", "AA:BB:CC:DD:EE:FF", "set", "--rgb", "1", "2", "3", "--color", "red"])
        assert result.exit_code != 0
        assert "--color ve --rgb" in result.output
        mock_send.assert_not_awaited()
