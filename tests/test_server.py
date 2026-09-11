"""Unit tests for the Web Dashboard server API endpoints."""

import asyncio
from unittest.mock import AsyncMock, patch

from aiohttp.test_utils import TestClient, TestServer
import pytest

from sp611e_cli.server import create_app


def test_server_get_status() -> None:
    """Test /api/status endpoint."""
    async def _run() -> None:
        app = create_app()
        client = TestClient(TestServer(app))
        await client.start_server()
        try:
            with patch("sp611e_cli.server.get_default_mac", return_value="AA:BB:CC:DD:EE:FF"):
                resp = await client.get("/api/status")
                assert resp.status == 200
                data = await resp.json()
                assert data["success"] is True
                assert data["mac"] == "AA:BB:CC:DD:EE:FF"
        finally:
            await client.close()

    asyncio.run(_run())


def test_server_post_power() -> None:
    """Test /api/power endpoint."""
    async def _run() -> None:
        app = create_app()
        client = TestClient(TestServer(app))
        await client.start_server()
        try:
            with patch("sp611e_cli.server.SP611EController.send_command", new_callable=AsyncMock) as mock_send:
                resp = await client.post(
                    "/api/power",
                    json={"state": "on", "mac": "AA:BB:CC:DD:EE:FF"},
                )
                assert resp.status == 200
                data = await resp.json()
                assert data["success"] is True
                assert data["state"] == "on"
                mock_send.assert_awaited_once()
        finally:
            await client.close()

    asyncio.run(_run())


def test_server_post_color() -> None:
    """Test /api/color endpoint."""
    async def _run() -> None:
        app = create_app()
        client = TestClient(TestServer(app))
        await client.start_server()
        try:
            with patch("sp611e_cli.server.SP611EController.send_commands", new_callable=AsyncMock) as mock_send:
                resp = await client.post(
                    "/api/color",
                    json={"r": 255, "g": 0, "b": 100, "brightness": 200, "mac": "AA:BB:CC:DD:EE:FF"},
                )
                assert resp.status == 200
                data = await resp.json()
                assert data["success"] is True
                assert data["r"] == 255
                # One connection carrying: solid-mode switch, then the RGB frame.
                mock_send.assert_awaited_once()
                frames = list(mock_send.await_args.args[0])
                assert frames == [
                    bytes([0xA0, 0x63, 0x01, 0xBE]),
                    bytes([0xA0, 0x69, 0x04, 255, 0, 100, 200]),
                ]
        finally:
            await client.close()

    asyncio.run(_run())


def test_server_post_brightness() -> None:
    """Test /api/brightness endpoint."""
    async def _run() -> None:
        app = create_app()
        client = TestClient(TestServer(app))
        await client.start_server()
        try:
            with patch("sp611e_cli.server.SP611EController.send_command", new_callable=AsyncMock) as mock_send:
                resp = await client.post(
                    "/api/brightness",
                    json={"level": 180, "mac": "AA:BB:CC:DD:EE:FF"},
                )
                assert resp.status == 200
                data = await resp.json()
                assert data["success"] is True
                assert data["level"] == 180
                mock_send.assert_awaited_once()
        finally:
            await client.close()

    asyncio.run(_run())


def test_server_post_effect() -> None:
    """Test /api/effect endpoint."""
    async def _run() -> None:
        app = create_app()
        client = TestClient(TestServer(app))
        await client.start_server()
        try:
            with patch("sp611e_cli.server.SP611EController.send_commands", new_callable=AsyncMock) as mock_send:
                resp = await client.post(
                    "/api/effect",
                    json={"effect_id": 3, "speed": 9, "mac": "AA:BB:CC:DD:EE:FF"},
                )
                assert resp.status == 200
                data = await resp.json()
                assert data["success"] is True
                assert data["effect_id"] == 3
                # Effect + speed share a single connection.
                mock_send.assert_awaited_once()
                frames = list(mock_send.await_args.args[0])
                assert frames == [
                    bytes([0xA0, 0x63, 0x01, 0x03]),
                    bytes([0xA0, 0x67, 0x01, 0x09]),
                ]

            # Without speed only the effect frame is sent.
            with patch("sp611e_cli.server.SP611EController.send_commands", new_callable=AsyncMock) as mock_send:
                resp = await client.post("/api/effect", json={"effect_id": 7, "mac": "AA:BB:CC:DD:EE:FF"})
                assert resp.status == 200
                assert list(mock_send.await_args.args[0]) == [bytes([0xA0, 0x63, 0x01, 0x07])]
        finally:
            await client.close()

    asyncio.run(_run())


def test_server_rejects_out_of_range_values() -> None:
    """Out-of-range speed/effect values are a 400, not a 500."""
    async def _run() -> None:
        app = create_app()
        client = TestClient(TestServer(app))
        await client.start_server()
        try:
            with patch("sp611e_cli.server.SP611EController.send_commands", new_callable=AsyncMock) as mock_send:
                resp = await client.post(
                    "/api/effect",
                    json={"effect_id": 3, "speed": 42, "mac": "AA:BB:CC:DD:EE:FF"},
                )
                assert resp.status == 400
                data = await resp.json()
                assert data["success"] is False
                mock_send.assert_not_awaited()
        finally:
            await client.close()

    asyncio.run(_run())
