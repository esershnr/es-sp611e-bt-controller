"""Unit tests for SP611EController transport behaviour (mocked BleakClient)."""

import asyncio
from typing import List
from unittest.mock import patch

from bleak.exc import BleakError
import pytest

from sp611e_cli import device as device_mod
from sp611e_cli.device import SP611E_WRITE_CHAR_UUID, SP611ECommandError, SP611EController


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
        _FakeBleakClient.active_connections += 1
        _FakeBleakClient.max_concurrent = max(
            _FakeBleakClient.max_concurrent, _FakeBleakClient.active_connections
        )
        await asyncio.sleep(0)  # yield so concurrent callers can interleave
        return self

    async def __aexit__(self, *exc) -> None:
        _FakeBleakClient.active_connections -= 1

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
