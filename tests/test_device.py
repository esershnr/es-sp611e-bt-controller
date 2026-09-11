"""Unit tests for SP611EController transport behaviour (mocked BleakClient)."""

import asyncio
from typing import List
from unittest.mock import patch

from bleak.exc import BleakError
import pytest

from sp611e_cli import device as device_mod
from sp611e_cli.device import (
    SP611E_WRITE_CHAR_UUID,
    SP611ECommandError,
    SP611EConnectionError,
    SP611EController,
)


class _FakeBleakClient:
    """Minimal async-context BleakClient stand-in recording connections and writes."""

    instances: List["_FakeBleakClient"] = []
    active_connections: int = 0
    max_concurrent: int = 0

    def __init__(self, address: str, timeout: float = 10.0) -> None:
        self.address = address
        self.timeout = timeout
        self.writes: List[tuple] = []
        _FakeBleakClient.instances.append(self)

    async def __aenter__(self) -> "_FakeBleakClient":
        await self.connect()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        _FakeBleakClient.active_connections += 1
        _FakeBleakClient.max_concurrent = max(
            _FakeBleakClient.max_concurrent, _FakeBleakClient.active_connections
        )
        self.is_connected = True
        await asyncio.sleep(0)  # yield so concurrent callers can interleave

    async def disconnect(self) -> None:
        if self.is_connected:
            _FakeBleakClient.active_connections -= 1
            self.is_connected = False

    is_connected: bool = False

    async def write_gatt_char(self, uuid: str, data: bytes, response: bool = False) -> None:
        self.writes.append((uuid, bytes(data), response))
        await asyncio.sleep(0.01)

    @classmethod
    def reset(cls) -> None:
        cls.instances = []
        cls.active_connections = 0
        cls.max_concurrent = 0


@pytest.fixture(autouse=True)
def _fake_bleak(monkeypatch: pytest.MonkeyPatch):
    _FakeBleakClient.reset()
    monkeypatch.setattr(device_mod, "BleakClient", _FakeBleakClient)
    monkeypatch.setattr(device_mod, "INTER_FRAME_DELAY", 0.0)
    yield
    _FakeBleakClient.reset()


def test_send_commands_uses_single_connection_in_order() -> None:
    """Multiple frames are written sequentially over ONE connection."""
    frames = [bytes([0xA0, 0x63, 0x01, 0xBE]), bytes([0xA0, 0x69, 0x04, 1, 2, 3, 4])]
    controller = SP611EController("aa:bb:cc:dd:ee:ff")

    asyncio.run(controller.send_commands(frames))

    assert len(_FakeBleakClient.instances) == 1
    client = _FakeBleakClient.instances[0]
    assert client.address == "AA:BB:CC:DD:EE:FF"
    assert [w[1] for w in client.writes] == frames
    assert all(w[0] == SP611E_WRITE_CHAR_UUID for w in client.writes)
    assert all(w[2] is False for w in client.writes)


def test_send_command_delegates_to_send_commands() -> None:
    """send_command() is the single-frame convenience wrapper."""
    controller = SP611EController("AA:BB:CC:DD:EE:FF")
    asyncio.run(controller.send_command(bytes([0xA0, 0x62, 0x01, 0x01])))

    assert len(_FakeBleakClient.instances) == 1
    assert _FakeBleakClient.instances[0].writes[0][1] == bytes([0xA0, 0x62, 0x01, 0x01])


def test_send_commands_empty_is_noop() -> None:
    controller = SP611EController("AA:BB:CC:DD:EE:FF")
    asyncio.run(controller.send_commands([]))
    assert _FakeBleakClient.instances == []


def test_concurrent_sends_are_serialized() -> None:
    """Parallel callers never hold two BLE connections at once (device supports one)."""
    controller = SP611EController("AA:BB:CC:DD:EE:FF")

    async def _run() -> None:
        await asyncio.gather(
            *(controller.send_command(bytes([0xA0, 0x66, 0x01, i])) for i in range(6))
        )

    asyncio.run(_run())

    assert len(_FakeBleakClient.instances) == 6
    assert _FakeBleakClient.max_concurrent == 1


def test_write_falls_back_to_response_true() -> None:
    """If write-without-response fails, retry with response=True."""
    controller = SP611EController("AA:BB:CC:DD:EE:FF")
    frame = bytes([0xA0, 0x62, 0x01, 0x01])

    calls: List[bool] = []

    async def _write(self, uuid, data, response=False):
        calls.append(response)
        if response is False:
            raise BleakError("nope")

    with patch.object(_FakeBleakClient, "write_gatt_char", new=_write):
        asyncio.run(controller.send_command(frame))

    assert calls == [False, True]


def test_write_failure_raises_command_error() -> None:
    controller = SP611EController("AA:BB:CC:DD:EE:FF")

    async def _write(self, uuid, data, response=False):
        raise BleakError("Characteristic was not found!")

    with patch.object(_FakeBleakClient, "write_gatt_char", new=_write):
        with pytest.raises(SP611ECommandError, match="Komut gönderilemedi"):
            asyncio.run(controller.send_command(bytes([0xA0, 0x62, 0x01, 0x01])))


# --- SP611ESession (persistent connection) ---------------------------------


def test_session_keeps_single_connection_across_writes() -> None:
    """A session connects once and streams many frames over that link."""
    controller = SP611EController("AA:BB:CC:DD:EE:FF")

    async def _run() -> None:
        async with controller.session() as session:
            assert session.connected
            await session.write(bytes([0xA0, 0x63, 0x01, 0xBE]))
            await session.write_many([bytes([0xA0, 0x69, 0x04, 1, 2, 3, 255]), bytes([0xA0, 0x69, 0x04, 4, 5, 6, 255])])
            assert session.connected
        assert not session.connected

    asyncio.run(_run())

    assert len(_FakeBleakClient.instances) == 1
    client = _FakeBleakClient.instances[0]
    assert [w[1] for w in client.writes] == [
        bytes([0xA0, 0x63, 0x01, 0xBE]),
        bytes([0xA0, 0x69, 0x04, 1, 2, 3, 255]),
        bytes([0xA0, 0x69, 0x04, 4, 5, 6, 255]),
    ]
    assert client.is_connected is False
    assert _FakeBleakClient.active_connections == 0


def test_session_holds_ble_lock_until_disconnect() -> None:
    """While a session is open, one-shot send_commands() callers wait for it."""
    controller = SP611EController("AA:BB:CC:DD:EE:FF")
    order: List[str] = []

    async def _run() -> None:
        session = controller.session()
        await session.connect()
        order.append("session-open")

        async def _oneshot() -> None:
            await controller.send_command(bytes([0xA0, 0x62, 0x01, 0x01]))
            order.append("oneshot-done")

        task = asyncio.create_task(_oneshot())
        await asyncio.sleep(0.05)
        assert "oneshot-done" not in order  # blocked behind the session
        order.append("session-close")
        await session.disconnect()
        await task

    asyncio.run(_run())

    assert order == ["session-open", "session-close", "oneshot-done"]
    assert _FakeBleakClient.max_concurrent == 1


def test_session_write_without_connection_raises() -> None:
    controller = SP611EController("AA:BB:CC:DD:EE:FF")
    session = controller.session()

    with pytest.raises(SP611EConnectionError, match="aktif bir BLE oturumu yok"):
        asyncio.run(session.write(bytes([0xA0, 0x62, 0x01, 0x01])))


def test_session_connect_failure_releases_lock() -> None:
    """A failed connect must not leave the BLE lock held (later calls would hang)."""
    controller = SP611EController("AA:BB:CC:DD:EE:FF")

    async def _boom(self) -> None:
        raise BleakError("device unreachable")

    async def _run() -> None:
        session = controller.session()
        with patch.object(_FakeBleakClient, "connect", new=_boom):
            with pytest.raises(SP611EConnectionError):
                await session.connect()
        assert not session.connected
        # Lock released: a normal send goes through without blocking.
        await asyncio.wait_for(controller.send_command(bytes([0xA0, 0x62, 0x01, 0x01])), timeout=1.0)

    asyncio.run(_run())


def test_session_disconnect_is_idempotent() -> None:
    controller = SP611EController("AA:BB:CC:DD:EE:FF")

    async def _run() -> None:
        session = controller.session()
        await session.disconnect()  # never connected
        await session.connect()
        await session.disconnect()
        await session.disconnect()
        assert not session.connected

    asyncio.run(_run())
    assert _FakeBleakClient.active_connections == 0
