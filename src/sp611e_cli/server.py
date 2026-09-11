"""Local web server and REST API for SP611E Web Dashboard using aiohttp."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional
import webbrowser

from aiohttp import web

from sp611e_cli.config import get_default_mac, save_default_mac
from sp611e_cli.device import (
    SP611ECommandError,
    SP611EConnectionError,
    SP611EController,
    SP611EDeviceNotFoundError,
    SP611EError,
    scan_devices,
)
from sp611e_cli.logging_config import get_log_path, setup_logging
from sp611e_cli.protocol import (
    create_set_brightness_command,
    create_set_effect_command,
    create_set_speed_command,
    create_set_static_color_commands,
    create_turn_off_command,
    create_turn_on_command,
)

logger = logging.getLogger("sp611e_cli.server")
WEB_DIR: Path = Path(__file__).parent / "web"


def _get_target_mac(data: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Extract MAC from request data or fall back to default saved MAC."""
    if data and "mac" in data and data["mac"]:
        return str(data["mac"]).strip().upper()
    return get_default_mac()


async def handle_index(request: web.Request) -> web.Response:
    """Serve main index.html file."""
    index_file = WEB_DIR / "index.html"
    if not index_file.is_file():
        return web.Response(text="Web interface files not found.", status=404)
    return web.FileResponse(index_file)


async def handle_style(request: web.Request) -> web.Response:
    """Serve style.css file."""
    style_file = WEB_DIR / "style.css"
    if not style_file.is_file():
        return web.Response(text="CSS file not found.", status=404)
    return web.FileResponse(style_file)


async def handle_script(request: web.Request) -> web.Response:
    """Serve app.js file."""
    script_file = WEB_DIR / "app.js"
    if not script_file.is_file():
        return web.Response(text="JS file not found.", status=404)
    return web.FileResponse(script_file)


async def handle_get_status(request: web.Request) -> web.Response:
    """Return controller status and active MAC."""
    mac = get_default_mac()
    return web.json_response({
        "success": True,
        "mac": mac,
        "is_configured": bool(mac),
    })


async def handle_post_config(request: web.Request) -> web.Response:
    """Save default MAC address."""
    try:
        data = await request.json()
        mac = str(data.get("mac", "")).strip().upper()
        if not mac:
            return web.json_response({"success": False, "error": "MAC adresi boş olamaz."}, status=400)
        save_default_mac(mac)
        return web.json_response({"success": True, "mac": mac, "message": "Varsayılan MAC kaydedildi."})
    except Exception as exc:
        return web.json_response({"success": False, "error": str(exc)}, status=400)


async def handle_post_power(request: web.Request) -> web.Response:
    """Turn device on or off."""
    try:
        data = await request.json()
        state = str(data.get("state", "")).lower()
        mac = _get_target_mac(data)
        if not mac:
            return web.json_response({"success": False, "error": "Hedef MAC adresi bulunamadı."}, status=400)

        controller = SP611EController(mac_address=mac)
        if state == "on":
            cmd = create_turn_on_command()
        elif state == "off":
            cmd = create_turn_off_command()
        else:
            return web.json_response({"success": False, "error": "Geçersiz durum (on veya off olmalı)."}, status=400)

        await controller.send_command(cmd)
        return web.json_response({"success": True, "state": state, "mac": mac})
    except SP611EError as exc:
        return web.json_response({"success": False, "error": str(exc)}, status=500)
    except ValueError as exc:
        return web.json_response({"success": False, "error": f"Geçersiz değer: {exc}"}, status=400)
    except Exception as exc:
        return web.json_response({"success": False, "error": f"Beklenmeyen hata: {exc}"}, status=500)


async def handle_post_brightness(request: web.Request) -> web.Response:
    """Set brightness level (0-255)."""
    try:
        data = await request.json()
        level = int(data.get("level", 255))
        mac = _get_target_mac(data)
        if not mac:
            return web.json_response({"success": False, "error": "Hedef MAC adresi bulunamadı."}, status=400)

        if not (0 <= level <= 255):
            return web.json_response({"success": False, "error": "Parlaklık 0-255 arasında olmalıdır."}, status=400)

        controller = SP611EController(mac_address=mac)
        cmd = create_set_brightness_command(level)
        await controller.send_command(cmd)
        return web.json_response({"success": True, "level": level, "mac": mac})
    except SP611EError as exc:
        return web.json_response({"success": False, "error": str(exc)}, status=500)
    except ValueError as exc:
        return web.json_response({"success": False, "error": f"Geçersiz değer: {exc}"}, status=400)
    except Exception as exc:
        return web.json_response({"success": False, "error": f"Beklenmeyen hata: {exc}"}, status=500)


async def handle_post_color(request: web.Request) -> web.Response:
    """Set static RGB color.

    Always switches the controller into solid-color mode first; otherwise a
    running dynamic effect keeps playing and the new color is never shown.
    """
    try:
        data = await request.json()
        r = int(data.get("r", 255))
        g = int(data.get("g", 255))
        b = int(data.get("b", 255))
        brightness = int(data.get("brightness", 255))
        mac = _get_target_mac(data)

        if not mac:
            return web.json_response({"success": False, "error": "Hedef MAC adresi bulunamadı."}, status=400)

        controller = SP611EController(mac_address=mac)
        frames = create_set_static_color_commands(r, g, b, brightness=brightness)
        await controller.send_commands(frames)
        return web.json_response({
            "success": True,
            "r": r,
            "g": g,
            "b": b,
            "brightness": brightness,
            "mac": mac,
        })
    except SP611EError as exc:
        return web.json_response({"success": False, "error": str(exc)}, status=500)
    except ValueError as exc:
        return web.json_response({"success": False, "error": f"Geçersiz değer: {exc}"}, status=400)
    except Exception as exc:
        return web.json_response({"success": False, "error": f"Beklenmeyen hata: {exc}"}, status=500)


async def handle_post_effect(request: web.Request) -> web.Response:
    """Set dynamic effect and optional speed."""
    try:
        data = await request.json()
        effect_id = int(data.get("effect_id", 1))
        speed = data.get("speed")
        mac = _get_target_mac(data)

        if not mac:
            return web.json_response({"success": False, "error": "Hedef MAC adresi bulunamadı."}, status=400)

        controller = SP611EController(mac_address=mac)
        frames = [create_set_effect_command(effect_id)]
        if speed is not None:
            frames.append(create_set_speed_command(int(speed)))
        # Effect + speed go over one connection (a reconnect costs seconds).
        await controller.send_commands(frames)

        return web.json_response({
            "success": True,
            "effect_id": effect_id,
            "speed": speed,
            "mac": mac,
        })
    except SP611EError as exc:
        return web.json_response({"success": False, "error": str(exc)}, status=500)
    except ValueError as exc:
        return web.json_response({"success": False, "error": f"Geçersiz değer: {exc}"}, status=400)
    except Exception as exc:
        return web.json_response({"success": False, "error": f"Beklenmeyen hata: {exc}"}, status=500)


async def handle_post_speed(request: web.Request) -> web.Response:
    """Set effect speed (1-10)."""
    try:
        data = await request.json()
        speed = int(data.get("speed", 5))
        mac = _get_target_mac(data)

        if not mac:
            return web.json_response({"success": False, "error": "Hedef MAC adresi bulunamadı."}, status=400)

        controller = SP611EController(mac_address=mac)
        cmd = create_set_speed_command(speed)
        await controller.send_command(cmd)
        return web.json_response({"success": True, "speed": speed, "mac": mac})
    except SP611EError as exc:
        return web.json_response({"success": False, "error": str(exc)}, status=500)
    except ValueError as exc:
        return web.json_response({"success": False, "error": f"Geçersiz değer: {exc}"}, status=400)
    except Exception as exc:
        return web.json_response({"success": False, "error": f"Beklenmeyen hata: {exc}"}, status=500)


async def handle_get_scan(request: web.Request) -> web.Response:
    """Perform BLE scan and return discovered devices."""
    try:
        timeout = float(request.query.get("timeout", "4.0"))
        devices = await scan_devices(timeout=timeout)
        device_list = [
            {
                "address": d.address,
                "name": d.name,
                "rssi": d.rssi,
                "is_sp611e": d.is_sp611e,
            }
            for d in devices
        ]
        return web.json_response({"success": True, "devices": device_list})
    except SP611EError as exc:
        return web.json_response({"success": False, "error": str(exc)}, status=500)
    except Exception as exc:
        return web.json_response({"success": False, "error": f"Tarama hatası: {exc}"}, status=500)


def create_app() -> web.Application:
    """Create and configure the aiohttp web application."""
    setup_logging()
    app = web.Application()

    # API routes
    app.router.add_get("/api/status", handle_get_status)
    app.router.add_post("/api/config", handle_post_config)
    app.router.add_post("/api/power", handle_post_power)
    app.router.add_post("/api/brightness", handle_post_brightness)
    app.router.add_post("/api/color", handle_post_color)
    app.router.add_post("/api/effect", handle_post_effect)
    app.router.add_post("/api/speed", handle_post_speed)
    app.router.add_get("/api/scan", handle_get_scan)

    # Static and frontend routes
    app.router.add_get("/", handle_index)
    if WEB_DIR.is_dir():
        app.router.add_get("/style.css", handle_style)
        app.router.add_get("/app.js", handle_script)
        app.router.add_static("/static/", path=WEB_DIR, name="static")

    return app


async def start_server_async(host: str = "127.0.0.1", port: int = 8080, open_browser: bool = True) -> None:
    """Start the web server asynchronously."""
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    url = f"http://{host}:{port}"
    print(f"\n✨ SP611E Web Dashboard yayında: {url}")
    print("Durdurmak için Ctrl+C tuşlarına basın.\n")

    if open_browser:
        # Give server a moment to start before opening browser
        await asyncio.sleep(0.3)
        webbrowser.open(url)

    # Keep running until cancelled
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await runner.cleanup()
