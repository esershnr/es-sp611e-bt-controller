"""Command Line Interface (CLI) for SP611E BLE RGB LED controller."""

import asyncio
import os
import sys
from typing import Optional

import click

from sp611e_cli import __version__
from sp611e_cli.config import (
    get_config_path,
    get_default_mac,
    get_openrgb_defaults,
    save_default_mac,
    save_openrgb_defaults,
)
from sp611e_cli.device import (
    SP611ECommandError,
    SP611EConnectionError,
    SP611EController,
    SP611EDeviceNotFoundError,
    SP611EError,
    scan_devices,
)
from sp611e_cli.colors import parse_color
from sp611e_cli.logging_config import get_log_path, setup_logging
from sp611e_cli.protocol import (
    create_set_brightness_command,
    create_set_effect_command,
    create_set_speed_command,
    create_set_static_color_commands,
    create_state_commands,
    create_turn_off_command,
    create_turn_on_command,
)

# Ensure UTF-8 output encoding on Windows consoles
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass


def resolve_mac(mac: Optional[str]) -> str:
    """Resolve target MAC address from CLI option or config file."""
    if mac:
        return mac.strip().upper()

    default_mac = get_default_mac()
    if default_mac:
        return default_mac

    click.secho(
        "Hata: MAC adresi belirtilmedi!\n"
        "Lütfen komuta '--mac <MAC>' parametresini ekleyin veya varsayılan adres kaydetmek için:\n"
        "  sp611e config --set-mac <MAC>\n"
        "Yakındaki cihazları bulmak için:\n"
        "  sp611e scan",
        fg="red",
        err=True,
    )
    sys.exit(1)


def parse_brightness_value(level_str: str, percent: bool = False) -> int:
    """Parse '200', '80%' or ('50', percent=True) into a 0-255 level.

    Raises:
        ValueError: On non-numeric input or out-of-range values.
    """
    cleaned = level_str.strip()
    is_percent = percent or cleaned.endswith("%")
    if cleaned.endswith("%"):
        cleaned = cleaned[:-1].strip()

    try:
        val = float(cleaned)
    except ValueError as exc:
        raise ValueError(f"Geçersiz parlaklık değeri: '{level_str}'") from exc

    if is_percent:
        if not (0 <= val <= 100):
            raise ValueError("Yüzde değeri 0 ile 100 arasında olmalıdır.")
        return int(round((val / 100.0) * 255))

    level = int(round(val))
    if not (0 <= level <= 255):
        raise ValueError("Parlaklık seviyesi 0 ile 255 arasında olmalıdır.")
    return level


# Options shared by `sp611e set ...` and the root shortcut `sp611e --color ...`.
_STATE_OPTIONS = [
    click.option("--on", "power_on", is_flag=True, default=False, help="Cihazı aç."),
    click.option("--off", "power_off", is_flag=True, default=False, help="Cihazı kapat (diğer ayarlardan sonra)."),
    click.option("--color", "-c", default=None, metavar="COLOR", help="Statik renk: isim, '#RRGGBB' veya 'R,G,B'."),
    click.option("--rgb", nargs=3, type=click.IntRange(0, 255), default=None, metavar="R G B", help="Statik renk, 3 ayrı bileşen (örn: --rgb 0 0 255)."),
    click.option("--brightness", "-b", default=None, metavar="LEVEL", help="Parlaklık: 0-255 veya yüzde ('80%')."),
    click.option("--effect", "-e", type=int, default=None, metavar="ID", help="Dinamik efekt ID (1-255)."),
    click.option("--speed", "-s", type=int, default=None, metavar="SPEED", help="Efekt hızı (1-10)."),
]


def _with_state_options(func):
    for option in reversed(_STATE_OPTIONS):
        func = option(func)
    return func


def apply_state(
    target_mac: str,
    *,
    power_on: bool,
    power_off: bool,
    color: Optional[str],
    rgb: Optional[tuple[int, int, int]],
    brightness: Optional[str],
    effect: Optional[int],
    speed: Optional[int],
) -> None:
    """Validate the combined settings and send them over a single BLE connection."""
    if power_on and power_off:
        click.secho("Hata: --on ve --off aynı anda kullanılamaz.", fg="red", err=True)
        sys.exit(1)

    if color is not None and rgb is not None:
        click.secho("Hata: --color ve --rgb aynı anda kullanılamaz.", fg="red", err=True)
        sys.exit(1)

    try:
        if color is not None:
            rgb = parse_color([color])
        level = parse_brightness_value(brightness) if brightness is not None else None
        frames = create_state_commands(
            power=True if power_on else (False if power_off else None),
            rgb=rgb,
            brightness=level,
            effect_id=effect,
            speed=speed,
        )
    except ValueError as exc:
        click.secho(f"Hata: {exc}", fg="red", err=True)
        sys.exit(1)

    summary = []
    if power_on:
        summary.append("güç: açık")
    if effect is not None:
        summary.append(f"efekt: {effect}")
    if speed is not None:
        summary.append(f"hız: {speed}/10")
    if rgb is not None:
        summary.append(f"renk: #{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}")
    if level is not None:
        summary.append(f"parlaklık: {level}/255 ({round((level / 255.0) * 100)}%)")
    if power_off:
        summary.append("güç: kapalı")
    click.echo(f"Ayarlar uygulanıyor ({target_mac}): " + ", ".join(summary) + "...")

    controller = SP611EController(mac_address=target_mac)
    try:
        asyncio.run(controller.send_commands(frames))
        click.secho(f"✓ Başarılı: {len(frames)} komut tek bağlantıda iletildi.", fg="green")
    except (SP611EDeviceNotFoundError, SP611EConnectionError, SP611ECommandError) as exc:
        click.secho(f"\n[Hata] {exc}", fg="red", err=True)
        sys.exit(1)
    except Exception as exc:
        click.secho(f"\n[Beklenmeyen Hata] {exc}", fg="red", err=True)
        sys.exit(1)


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="sp611e")
@click.option(
    "--mac",
    "-m",
    default=None,
    help="Hedef SP611E cihazının Bluetooth MAC adresi (örn: AA:BB:CC:DD:EE:FF).",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Ayrıntılı hata ayıklama (debug) çıktılarını konsolda göster.",
)
@_with_state_options
@click.pass_context
def main(
    ctx: click.Context,
    mac: Optional[str],
    verbose: bool,
    power_on: bool,
    power_off: bool,
    color: Optional[str],
    rgb: Optional[tuple[int, int, int]],
    brightness: Optional[str],
    effect: Optional[int],
    speed: Optional[int],
) -> None:
    """SP611E (BanlanX) Bluetooth LE RGB LED Kontrolcüsü CLI Aracı.

    Alt komut vermeden birden fazla ayarı tek seferde uygulayabilirsiniz:

    
      sp611e --color red --brightness 10
      sp611e --on --effect 5 --speed 8
    """
    setup_logging(verbose=verbose)
    ctx.ensure_object(dict)
    ctx.obj["MAC"] = mac
    ctx.obj["VERBOSE"] = verbose

    if ctx.invoked_subcommand is not None:
        return

    has_state = any(v is not None for v in (color, rgb, brightness, effect, speed)) or power_on or power_off
    if not has_state:
        click.echo(ctx.get_help())
        return

    apply_state(
        resolve_mac(mac),
        power_on=power_on,
        power_off=power_off,
        color=color,
        rgb=rgb,
        brightness=brightness,
        effect=effect,
        speed=speed,
    )


@main.command("set")
@click.option(
    "--mac",
    "-m",
    default=None,
    help="Hedef SP611E cihazının Bluetooth MAC adresi.",
)
@_with_state_options
@click.pass_context
def cmd_set(
    ctx: click.Context,
    mac: Optional[str],
    power_on: bool,
    power_off: bool,
    color: Optional[str],
    rgb: Optional[tuple[int, int, int]],
    brightness: Optional[str],
    effect: Optional[int],
    speed: Optional[int],
) -> None:
    """Birden fazla ayarı tek BLE bağlantısında uygular.

    
    Örnekler:
      sp611e set --color red --brightness 10
      sp611e set --rgb 0 0 255 --brightness 50%
      sp611e set --on --color "#FF5733" -b 80%
      sp611e set --effect 5 --speed 8
      sp611e set --color 255,128,0 --off
    """
    apply_state(
        resolve_mac(mac or ctx.obj.get("MAC")),
        power_on=power_on,
        power_off=power_off,
        color=color,
        rgb=rgb,
        brightness=brightness,
        effect=effect,
        speed=speed,
    )


@main.command("scan")
@click.option(
    "--timeout",
    "-t",
    type=float,
    default=5.0,
    show_default=True,
    help="Bluetooth tarama süresi (saniye).",
)
@click.option(
    "--all",
    "-a",
    "show_all",
    is_flag=True,
    default=False,
    help="Sadece SP611E değil, bulunan tüm BLE cihazlarını listele.",
)
def cmd_scan(timeout: float, show_all: bool) -> None:
    """Yakındaki BLE cihazlarını tarar ve SP611E cihazlarını listeler."""
    click.echo(f"Bluetooth cihazları taranıyor ({timeout}s)...")

    try:
        devices = asyncio.run(scan_devices(timeout=timeout))
    except SP611EError as exc:
        click.secho(f"Tarama hatası: {exc}", fg="red", err=True)
        sys.exit(1)
    except Exception as exc:
        click.secho(f"Beklenmeyen tarama hatası: {exc}", fg="red", err=True)
        sys.exit(1)

    if not show_all:
        devices = [d for d in devices if d.is_sp611e]

    if not devices:
        if show_all:
            click.secho("Hiçbir BLE cihazı bulunamadı. Bluetooth'un açık olduğundan emin olun.", fg="yellow")
        else:
            click.secho(
                "SP611E cihazı bulunamadı.\n"
                "İpucu: Yakındaki tüm BLE cihazlarını görmek için 'sp611e scan --all' komutunu deneyin.",
                fg="yellow",
            )
        return

    click.echo("\n" + "=" * 65)
    click.echo(f"{'MAC Adresi':<20} {'RSSI':<8} {'Cihaz Adı':<25} {'Eşleşme'}")
    click.echo("=" * 65)

    for dev in devices:
        match_tag = "[SP611E]" if dev.is_sp611e else ""
        color = "green" if dev.is_sp611e else "white"
        line = f"{dev.address:<20} {f'{dev.rssi} dBm':<8} {dev.name[:24]:<25} {match_tag}"
        click.secho(line, fg=color)

    click.echo("=" * 65)
    click.echo("Cihazı varsayılan olarak kaydetmek için:")
    click.secho("  sp611e config --set-mac <MAC>\n", fg="cyan")


@main.command("on")
@click.option(
    "--mac",
    "-m",
    default=None,
    help="Hedef SP611E cihazının Bluetooth MAC adresi.",
)
@click.pass_context
def cmd_on(ctx: click.Context, mac: Optional[str]) -> None:
    """SP611E LED kontrolcüsünü AÇAR."""
    target_mac = resolve_mac(mac or ctx.obj.get("MAC"))
    click.echo(f"Cihaz açılıyor: {target_mac}...")

    controller = SP611EController(mac_address=target_mac)
    cmd = create_turn_on_command()

    try:
        asyncio.run(controller.send_command(cmd))
        click.secho(f"✓ Başarılı: {target_mac} cihazı açıldı.", fg="green")
    except (SP611EDeviceNotFoundError, SP611EConnectionError, SP611ECommandError) as exc:
        click.secho(f"\n[Hata] {exc}", fg="red", err=True)
        sys.exit(1)
    except Exception as exc:
        click.secho(f"\n[Beklenmeyen Hata] {exc}", fg="red", err=True)
        sys.exit(1)


@main.command("off")
@click.option(
    "--mac",
    "-m",
    default=None,
    help="Hedef SP611E cihazının Bluetooth MAC adresi.",
)
@click.pass_context
def cmd_off(ctx: click.Context, mac: Optional[str]) -> None:
    """SP611E LED kontrolcüsünü KAPATIR."""
    target_mac = resolve_mac(mac or ctx.obj.get("MAC"))
    click.echo(f"Cihaz kapatılıyor: {target_mac}...")

    controller = SP611EController(mac_address=target_mac)
    cmd = create_turn_off_command()

    try:
        asyncio.run(controller.send_command(cmd))
        click.secho(f"✓ Başarılı: {target_mac} cihazı kapatıldı.", fg="green")
    except (SP611EDeviceNotFoundError, SP611EConnectionError, SP611ECommandError) as exc:
        click.secho(f"\n[Hata] {exc}", fg="red", err=True)
        sys.exit(1)
    except Exception as exc:
        click.secho(f"\n[Beklenmeyen Hata] {exc}", fg="red", err=True)
        sys.exit(1)


@main.command("brightness")
@click.argument("level_str", metavar="LEVEL")
@click.option(
    "--mac",
    "-m",
    default=None,
    help="Hedef SP611E cihazının Bluetooth MAC adresi.",
)
@click.option(
    "--percent",
    "-p",
    is_flag=True,
    default=False,
    help="Değeri yüzde (0-100) olarak yorumla.",
)
@click.pass_context
def cmd_brightness(ctx: click.Context, level_str: str, mac: Optional[str], percent: bool) -> None:
    """Parlaklık seviyesini ayarlar (0-255 veya 0-100%).

    Örnekler:
      sp611e brightness 200
      sp611e brightness 80%
      sp611e brightness 50 -p
    """
    target_mac = resolve_mac(mac or ctx.obj.get("MAC"))

    try:
        level = parse_brightness_value(level_str, percent=percent)
    except ValueError as exc:
        click.secho(f"Hata: {exc}", fg="red", err=True)
        sys.exit(1)

    click.echo(f"Parlaklık ayarlanıyor: {level}/255 ({round((level / 255.0) * 100)}%)...")
    controller = SP611EController(mac_address=target_mac)
    cmd = create_set_brightness_command(level)

    try:
        asyncio.run(controller.send_command(cmd))
        click.secho(f"✓ Başarılı: {target_mac} parlaklığı {level}/255 olarak ayarlandı.", fg="green")
    except (SP611EDeviceNotFoundError, SP611EConnectionError, SP611ECommandError) as exc:
        click.secho(f"\n[Hata] {exc}", fg="red", err=True)
        sys.exit(1)
    except Exception as exc:
        click.secho(f"\n[Beklenmeyen Hata] {exc}", fg="red", err=True)
        sys.exit(1)


@main.command("color")
@click.argument("color_args", nargs=-1, required=True, metavar="COLOR...")
@click.option(
    "--mac",
    "-m",
    default=None,
    help="Hedef SP611E cihazının Bluetooth MAC adresi.",
)
@click.option(
    "--brightness",
    "-b",
    type=int,
    default=255,
    show_default=True,
    help="Renk ile birlikte uygulanacak parlaklık (0-255).",
)
@click.pass_context
def cmd_color(ctx: click.Context, color_args: tuple[str, ...], mac: Optional[str], brightness: int) -> None:
    """Statik RGB rengini ayarlar (İsim, Hex veya RGB bileşenleri).

    Örnekler:
      sp611e color red
      sp611e color warm-white
      sp611e color "#FF5733"
      sp611e color 255 128 0
      sp611e color blue -b 150
    """
    target_mac = resolve_mac(mac or ctx.obj.get("MAC"))

    if not (0 <= brightness <= 255):
        click.secho("Hata: Parlaklık değeri 0 ile 255 arasında olmalıdır.", fg="red", err=True)
        sys.exit(1)

    try:
        r, g, b = parse_color(color_args)
    except ValueError as exc:
        click.secho(f"Hata: {exc}", fg="red", err=True)
        sys.exit(1)

    hex_repr = f"#{r:02X}{g:02X}{b:02X}"
    click.echo(f"Renk ayarlanıyor: RGB({r}, {g}, {b}) [{hex_repr}] - Parlaklık: {brightness}...")

    controller = SP611EController(mac_address=target_mac)
    # Static-mode switch (A0 63 01 BE) + color frame over a single connection;
    # without the mode switch a running dynamic effect would swallow the color.
    frames = create_set_static_color_commands(r, g, b, brightness=brightness)

    try:
        asyncio.run(controller.send_commands(frames))
        click.secho(f"✓ Başarılı: {target_mac} rengi {hex_repr} olarak ayarlandı.", fg="green")
    except (SP611EDeviceNotFoundError, SP611EConnectionError, SP611ECommandError) as exc:
        click.secho(f"\n[Hata] {exc}", fg="red", err=True)
        sys.exit(1)
    except Exception as exc:
        click.secho(f"\n[Beklenmeyen Hata] {exc}", fg="red", err=True)
        sys.exit(1)


@main.command("effect")
@click.argument("effect_id", type=int, metavar="EFFECT_ID")
@click.option(
    "--mac",
    "-m",
    default=None,
    help="Hedef SP611E cihazının Bluetooth MAC adresi.",
)
@click.option(
    "--speed",
    "-s",
    type=int,
    default=None,
    help="Efekt hızı (1-10). Belirtilirse efektle birlikte hız da ayarlanır.",
)
@click.pass_context
def cmd_effect(ctx: click.Context, effect_id: int, mac: Optional[str], speed: Optional[int]) -> None:
    """Dinamik ışık efektini ayarlar (1-255).

    Örnekler:
      sp611e effect 1
      sp611e effect 10 -s 5
    """
    target_mac = resolve_mac(mac or ctx.obj.get("MAC"))

    if not (1 <= effect_id <= 255):
        click.secho("Hata: Efekt ID 1 ile 255 arasında olmalıdır.", fg="red", err=True)
        sys.exit(1)

    if speed is not None and not (1 <= speed <= 10):
        click.secho("Hata: Efekt hızı 1 ile 10 arasında olmalıdır.", fg="red", err=True)
        sys.exit(1)

    if speed is not None:
        click.echo(f"Efekt ayarlanıyor: ID {effect_id}, hız {speed}/10...")
    else:
        click.echo(f"Efekt ayarlanıyor: ID {effect_id}...")

    controller = SP611EController(mac_address=target_mac)
    frames = [create_set_effect_command(effect_id)]
    if speed is not None:
        frames.append(create_set_speed_command(speed))

    try:
        # Effect + speed go over one connection (each reconnect costs seconds).
        asyncio.run(controller.send_commands(frames))
        click.secho(f"✓ Başarılı: {target_mac} efekti {effect_id} olarak ayarlandı.", fg="green")
        if speed is not None:
            click.secho(f"✓ Başarılı: Efekt hızı {speed}/10 olarak ayarlandı.", fg="green")

    except (SP611EDeviceNotFoundError, SP611EConnectionError, SP611ECommandError) as exc:
        click.secho(f"\n[Hata] {exc}", fg="red", err=True)
        sys.exit(1)
    except Exception as exc:
        click.secho(f"\n[Beklenmeyen Hata] {exc}", fg="red", err=True)
        sys.exit(1)


@main.command("speed")
@click.argument("speed", type=int, metavar="SPEED")
@click.option(
    "--mac",
    "-m",
    default=None,
    help="Hedef SP611E cihazının Bluetooth MAC adresi.",
)
@click.pass_context
def cmd_speed(ctx: click.Context, speed: int, mac: Optional[str]) -> None:
    """Efekt oynatma hızını ayarlar (1-10: 1 en yavaş, 10 en hızlı).

    Örnekler:
      sp611e speed 5
      sp611e speed 10
    """
    target_mac = resolve_mac(mac or ctx.obj.get("MAC"))

    if not (1 <= speed <= 10):
        click.secho("Hata: Hız değeri 1 ile 10 arasında olmalıdır (1: en yavaş, 10: en hızlı).", fg="red", err=True)
        sys.exit(1)

    click.echo(f"Efekt hızı ayarlanıyor: {speed}/10...")
    controller = SP611EController(mac_address=target_mac)
    cmd = create_set_speed_command(speed)

    try:
        asyncio.run(controller.send_command(cmd))
        click.secho(f"✓ Başarılı: {target_mac} efekt hızı {speed}/10 olarak ayarlandı.", fg="green")
    except (SP611EDeviceNotFoundError, SP611EConnectionError, SP611ECommandError) as exc:
        click.secho(f"\n[Hata] {exc}", fg="red", err=True)
        sys.exit(1)
    except Exception as exc:
        click.secho(f"\n[Beklenmeyen Hata] {exc}", fg="red", err=True)
        sys.exit(1)


@main.command("config")
@click.option(
    "--set-mac",
    type=str,
    default=None,
    help="Varsayılan SP611E MAC adresini yapılandırma dosyasına kaydet.",
)
@click.option(
    "--show",
    is_flag=True,
    default=False,
    help="Mevcut yapılandırma dosyasını ve kayıtlı MAC adresini göster.",
)
def cmd_config(set_mac: Optional[str], show: bool) -> None:
    """Yapılandırma ayarlarını yönetir (~/.sp611e/config.toml)."""
    cfg_path = get_config_path()

    if set_mac:
        cleaned_mac = set_mac.strip().upper()
        save_default_mac(cleaned_mac)
        click.secho(f"✓ Varsayılan MAC adresi kaydedildi: {cleaned_mac}", fg="green")
        click.echo(f"Yapılandırma dosyası: {cfg_path}")
        return

    # Default action or --show: display current configuration
    current_mac = get_default_mac()
    click.echo(f"Yapılandırma Dosyası: {cfg_path}")
    if current_mac:
        click.secho(f"Varsayılan MAC Adresi: {current_mac}", fg="cyan")
    else:
        click.secho("Kayıtlı varsayılan MAC adresi bulunamadı.", fg="yellow")
        click.echo("Kaydetmek için: sp611e config --set-mac <MAC>")

    openrgb_defaults = get_openrgb_defaults()
    if openrgb_defaults:
        click.secho("[openrgb] varsayılanları: " + ", ".join(f"{k}={v}" for k, v in openrgb_defaults.items()), fg="cyan")
    else:
        click.echo("[openrgb] varsayılanı yok (kaydetmek için: sp611e openrgb ... --save)")


@main.command("gui")
@click.option(
    "--port",
    "-p",
    type=int,
    default=8080,
    show_default=True,
    help="Web dashboard port numarası.",
)
@click.option(
    "--host",
    "-h",
    type=str,
    default="127.0.0.1",
    show_default=True,
    help="Dinlenecek ağ arayüzü.",
)
@click.option(
    "--no-browser",
    is_flag=True,
    default=False,
    help="Tarayıcıyı otomatik açma.",
)
def cmd_gui(port: int, host: str, no_browser: bool) -> None:
    """SP611E Web Dashboard arayüzünü başlatır."""
    from sp611e_cli.server import start_server_async

    click.echo(f"SP611E Web Dashboard başlatılıyor (http://{host}:{port})...")
    try:
        asyncio.run(start_server_async(host=host, port=port, open_browser=not no_browser))
    except KeyboardInterrupt:
        click.secho("\nSunucu durduruldu.", fg="yellow")
    except Exception as exc:
        click.secho(f"\nSunucu hatası: {exc}", fg="red", err=True)
        sys.exit(1)


OPENRGB_BUILTIN_DEFAULTS = {
    "host": "127.0.0.1",
    "port": 6742,
    "device": None,
    "zone": None,
    "pick": "avg",
    "fps": 10.0,
    "brightness": 255,
    "idle_timeout": 30.0,
    "power_on": True,
}


def _resolve_openrgb_settings(cli_values: dict) -> dict:
    """Effective settings = CLI value, else [openrgb] config, else built-in default."""
    saved = get_openrgb_defaults()
    effective = {}
    for key, builtin in OPENRGB_BUILTIN_DEFAULTS.items():
        value = cli_values.get(key)
        if value is None:
            value = saved.get(key, builtin)
        effective[key] = value
    return effective


async def _run_bridge_with_stop_watch(bridge, pid: int) -> None:
    """Run the bridge; stop it gracefully when the PID file disappears (sp611e openrgb --stop)."""
    from sp611e_cli.background import stop_requested

    async def _watch() -> None:
        while not stop_requested(pid):
            await asyncio.sleep(0.5)
        bridge.stop()

    watcher = asyncio.create_task(_watch())
    try:
        await bridge.run()
    finally:
        watcher.cancel()


@main.command("openrgb")
@click.option("--mac", "-m", default=None, help="Hedef SP611E cihazının Bluetooth MAC adresi.")
@click.option("--host", default=None, help="OpenRGB SDK sunucu adresi.  [varsayılan: 127.0.0.1]")
@click.option("--port", type=int, default=None, help="OpenRGB SDK sunucu portu.  [varsayılan: 6742]")
@click.option("--device", "-d", default=None, metavar="NAME|INDEX", help="Takip edilecek OpenRGB cihazı (ad parçası veya indeks). Tek cihaz varsa gerekmez.")
@click.option("--zone", "-z", default=None, metavar="NAME|INDEX", help="Sadece bu zone'u takip et (ad parçası veya indeks).")
@click.option("--pick", default=None, metavar="avg|first|brightest|N", help="LED'lerden tek renk seçme yöntemi (N = LED indeksi).  [varsayılan: avg]")
@click.option("--fps", type=float, default=None, help="OpenRGB'yi saniyede kaç kez sorgula (BLE üst sınırı ~15).  [varsayılan: 10]")
@click.option("--brightness", "-b", default=None, metavar="LEVEL", help="Şeride uygulanacak parlaklık: 0-255 veya yüzde ('80%').  [varsayılan: 255]")
@click.option("--idle-timeout", type=float, default=None, help="Renk bu kadar saniye değişmezse BLE bağlantısını bırak (0 = hiç bırakma).  [varsayılan: 30]")
@click.option("--power-on/--no-power-on", default=None, help="Bağlanınca cihazı açma komutu gönder / gönderme.  [varsayılan: gönder]")
@click.option("--save", is_flag=True, default=False, help="Verilen seçenekleri ~/.sp611e/config.toml [openrgb] bölümüne varsayılan olarak kaydet ve çık.")
@click.option("--list", "list_only", is_flag=True, default=False, help="OpenRGB cihaz/zone listesini göster ve çık.")
@click.option("--background", is_flag=True, default=False, help="Köprüyü penceresiz bir arka plan süreci olarak başlat ve terminale dön.")
@click.option("--stop", is_flag=True, default=False, help="Arka planda çalışan köprüyü durdur.")
@click.option("--status", is_flag=True, default=False, help="Arka plan köprüsü, otomatik başlatma ve kayıtlı ayarların durumunu göster.")
@click.option("--install-startup", is_flag=True, default=False, help="Windows oturum açılışında köprüyü otomatik başlat (Görev Zamanlayıcı).")
@click.option("--uninstall-startup", is_flag=True, default=False, help="Otomatik başlatma görevini kaldır.")
@click.pass_context
def cmd_openrgb(
    ctx: click.Context,
    mac: Optional[str],
    host: Optional[str],
    port: Optional[int],
    device: Optional[str],
    zone: Optional[str],
    pick: Optional[str],
    fps: Optional[float],
    brightness: Optional[str],
    idle_timeout: Optional[float],
    power_on: Optional[bool],
    save: bool,
    list_only: bool,
    background: bool,
    stop: bool,
    status: bool,
    install_startup: bool,
    uninstall_startup: bool,
) -> None:
    """OpenRGB'deki bir cihazın rengini SP611E'ye canlı aynalar (SDK köprüsü).

    OpenRGB'de Settings > SDK Server açık olmalıdır. Verilmeyen seçenekler
    config.toml [openrgb] bölümünden, o da yoksa varsayılanlardan alınır.

    \b
    Örnekler:
      sp611e openrgb --list
      sp611e openrgb -d "ASUS Aura" -z "RGB Header" -b 12% --save   # varsayılanları kaydet
      sp611e openrgb --background                                    # arka planda başlat
      sp611e openrgb --status / --stop
      sp611e openrgb --install-startup                               # oturum açılışında başlat
    """
    from sp611e_cli import background as bg
    from sp611e_cli.openrgb_bridge import (
        BridgeConfig,
        BridgeConfigError,
        OpenRGBBridge,
        describe_devices,
    )

    try:
        level = parse_brightness_value(brightness) if brightness is not None else None
    except ValueError as exc:
        click.secho(f"Hata: {exc}", fg="red", err=True)
        sys.exit(1)

    cli_values = {
        "host": host,
        "port": port,
        "device": device,
        "zone": zone,
        "pick": pick,
        "fps": fps,
        "brightness": level,
        "idle_timeout": idle_timeout,
        "power_on": power_on,
    }
    settings = _resolve_openrgb_settings(cli_values)

    # --- management flags (no BLE) -----------------------------------------
    if stop:
        try:
            pid = bg.stop_background()
        except bg.BackgroundError as exc:
            click.secho(f"Hata: {exc}", fg="red", err=True)
            sys.exit(1)
        if pid is None:
            click.secho("Arka planda çalışan bir köprü yok.", fg="yellow")
        else:
            click.secho(f"✓ Arka plan köprüsü durduruldu (PID {pid}).", fg="green")
        return

    if status:
        pid = bg.running_pid()
        if pid is None:
            click.secho("Arka plan köprüsü: çalışmıyor", fg="yellow")
        else:
            click.secho(f"Arka plan köprüsü: çalışıyor (PID {pid})", fg="green")
        installed = bg.startup_installed()
        click.echo(f"Oturum açılışında başlatma: {'kurulu' if installed else 'kurulu değil'}"
                   + (f"  [{bg.STARTUP_TASK_NAME}]" if installed else ""))
        saved = get_openrgb_defaults()
        click.echo(f"Kayıtlı [openrgb] ayarları ({get_config_path()}): " + (", ".join(f"{k}={v}" for k, v in saved.items()) or "yok"))
        click.echo("Etkin ayarlar: " + ", ".join(f"{k}={v}" for k, v in settings.items() if v is not None))
        click.echo(f"Arka plan çıktı dosyası: {bg.OUTPUT_LOG}")
        return

    if uninstall_startup:
        try:
            removed = bg.uninstall_startup()
        except bg.BackgroundError as exc:
            click.secho(f"Hata: {exc}", fg="red", err=True)
            sys.exit(1)
        click.secho("✓ Otomatik başlatma görevi kaldırıldı." if removed else "Otomatik başlatma görevi zaten yok.",
                    fg="green" if removed else "yellow")
        return

    if save:
        try:
            saved = save_openrgb_defaults(**cli_values)
        except ValueError as exc:
            click.secho(f"Hata: {exc}", fg="red", err=True)
            sys.exit(1)
        click.secho("✓ [openrgb] varsayılanları kaydedildi: " + (", ".join(f"{k}={v}" for k, v in saved.items()) or "(boş)"), fg="green")
        click.echo(f"Yapılandırma dosyası: {get_config_path()}")
        return

    if install_startup:
        if not get_default_mac():
            click.secho("Hata: Önce varsayılan MAC kaydedin: sp611e config --set-mac <MAC>", fg="red", err=True)
            sys.exit(1)
        try:
            task = bg.install_startup()
        except bg.BackgroundError as exc:
            click.secho(f"Hata: {exc}", fg="red", err=True)
            sys.exit(1)
        click.secho(f"✓ Oturum açılışında başlatma kuruldu: [{task}]", fg="green")
        click.echo(f"  Çalıştırılacak komut: {bg.startup_command()}")
        click.echo("  Köprü, kayıtlı [openrgb] ayarlarıyla (sp611e openrgb ... --save) başlar.")
        if not get_openrgb_defaults():
            click.secho("  Uyarı: Kayıtlı [openrgb] ayarı yok; OpenRGB'de tek cihaz yoksa köprü başlayamaz.", fg="yellow")
        return

    if list_only:
        from openrgb import OpenRGBClient

        try:
            client = OpenRGBClient(address=settings["host"], port=settings["port"], name="sp611e-bridge")
        except OSError as exc:
            click.secho(
                f"OpenRGB SDK sunucusuna bağlanılamadı ({settings['host']}:{settings['port']}): {exc}\n"
                "OpenRGB açık ve Settings > SDK Server etkin mi?",
                fg="red",
                err=True,
            )
            sys.exit(1)
        try:
            click.echo(describe_devices(client.devices))
        finally:
            client.disconnect()
        return

    # --- run ---------------------------------------------------------------
    target_mac = resolve_mac(mac or ctx.obj.get("MAC"))

    if background:
        args = [a for a in sys.argv[1:] if a != "--background"]
        try:
            pid = bg.spawn_background(args)
        except bg.BackgroundError as exc:
            click.secho(f"Hata: {exc}", fg="red", err=True)
            sys.exit(1)
        click.secho(f"✓ Köprü arka planda başlatıldı (PID {pid}).", fg="green")
        click.echo(f"  Durum: sp611e openrgb --status   Durdur: sp611e openrgb --stop   Çıktı: {bg.OUTPUT_LOG}")
        return

    try:
        config = BridgeConfig(mac=target_mac, **settings)
    except BridgeConfigError as exc:
        click.secho(f"Hata: {exc}", fg="red", err=True)
        sys.exit(1)

    click.echo(f"OpenRGB köprüsü başlatılıyor: {config.host}:{config.port} -> SP611E {target_mac}")
    click.echo("Ayarlar: " + ", ".join(
        f"{k}={v}" for k, v in settings.items() if k not in ("host", "port") and v is not None
    ))
    bridge = OpenRGBBridge(config, status=lambda msg: click.secho(msg, fg="cyan"))

    if bg.is_background_child():
        pid = os.getpid()
        bg.write_pid(pid)
        try:
            asyncio.run(_run_bridge_with_stop_watch(bridge, pid))
            click.secho(f"Köprü durduruldu ({bridge.frames_sent} kare gönderildi).", fg="yellow")
        except BridgeConfigError as exc:
            click.secho(f"Hata: {exc}", fg="red", err=True)
            sys.exit(1)
        finally:
            bg.remove_pid(pid)
        return

    click.echo("Durdurmak için Ctrl+C tuşlarına basın.\n")
    try:
        asyncio.run(bridge.run())
    except KeyboardInterrupt:
        click.secho(f"\nKöprü durduruldu ({bridge.frames_sent} kare gönderildi).", fg="yellow")
    except BridgeConfigError as exc:
        click.secho(f"\nHata: {exc}", fg="red", err=True)
        sys.exit(1)
    except Exception as exc:
        click.secho(f"\n[Beklenmeyen Hata] {exc}", fg="red", err=True)
        sys.exit(1)


@main.command("logs")
@click.option(
    "--lines",
    "-n",
    type=int,
    default=40,
    show_default=True,
    help="Gösterilecek son satır sayısı.",
)
@click.option(
    "--clear",
    is_flag=True,
    default=False,
    help="Log dosyasının içeriğini temizle.",
)
def cmd_logs(lines: int, clear: bool) -> None:
    """SP611E hata ayıklama (debug) loglarını görüntüler (~/.sp611e/sp611e.log)."""
    log_file = get_log_path()
    if clear:
        if log_file.is_file():
            log_file.write_text("", encoding="utf-8")
            click.secho("✓ Log dosyası temizlendi.", fg="green")
        else:
            click.echo("Log dosyası zaten boş veya henüz oluşturulmamış.")
        return

    click.echo(f"Log Dosyası: {log_file}")
    if not log_file.is_file():
        click.secho("Henüz oluşturulmuş bir log kaydı bulunamadı.", fg="yellow")
        return

    try:
        content = log_file.read_text(encoding="utf-8", errors="replace").strip()
        if not content:
            click.secho("Log dosyası boş.", fg="yellow")
            return

        all_lines = content.splitlines()
        tail = all_lines[-lines:] if len(all_lines) > lines else all_lines
        click.echo("=" * 70)
        for line in tail:
            if " [ERROR] " in line:
                click.secho(line, fg="red")
            elif " [WARNING] " in line:
                click.secho(line, fg="yellow")
            elif " [DEBUG] " in line:
                click.secho(line, fg="cyan")
            else:
                click.echo(line)
        click.echo("=" * 70)
        click.echo(f"Toplam {len(all_lines)} satırdan son {len(tail)} tanesi gösterildi.")
    except Exception as exc:
        click.secho(f"Log dosyası okunamadı: {exc}", fg="red", err=True)


if __name__ == "__main__":
    main()
