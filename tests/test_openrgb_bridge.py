"""Unit tests for the OpenRGB SDK bridge (fake OpenRGB client, fake BLE session)."""

import asyncio
from typing import List, Optional, Tuple

import pytest

from sp611e_cli import openrgb_bridge as bridge_mod
from sp611e_cli.device import SP611EConnectionError
from sp611e_cli.openrgb_bridge import (
    BridgeConfig,
    BridgeConfigError,
    OpenRGBBridge,
    describe_devices,
    reduce_colors,
    select_source,
)

POWER_ON = bytes([0xA0, 0x62, 0x01, 0x01])
STATIC_MODE = bytes([0xA0, 0x63, 0x01, 0xBE])


def rgb_frame(r: int, g: int, b: int, level: int = 255) -> bytes:
    return bytes([0xA0, 0x69, 0x04, r, g, b, level])


# --- fakes -----------------------------------------------------------------


class _Color:
    def __init__(self, r: int, g: int, b: int) -> None:
        self.red, self.green, self.blue = r, g, b


class _Zone:
    def __init__(self, name: str, colors: List[Tuple[int, int, int]]) -> None:
        self.name = name
        self.colors = [_Color(*c) for c in colors]
        self.leds = list(self.colors)


class _Device:
    def __init__(self, name: str, zones: List[_Zone]) -> None:
        self.name = name
        self.zones = zones
        self.updates = 0

    @property
    def colors(self) -> List[_Color]:
        return [c for z in self.zones for c in z.colors]

    @property
    def leds(self) -> List[_Color]:
        return self.colors

    def update(self) -> None:
        self.updates += 1

    def set(self, *rgb: int) -> None:
        for zone in self.zones:
            zone.colors = [_Color(*rgb) for _ in zone.colors]


class _Client:
    def __init__(self, devices: List[_Device]) -> None:
        self.devices = devices
        self.disconnected = False

    def disconnect(self) -> None:
        self.disconnected = True


class _FakeSession:
    """Records connect/disconnect/write calls; can be told to fail on connect."""

    def __init__(self) -> None:
        self.connected = False
        self.events: List[object] = []
        self.fail_connects = 0

    async def connect(self) -> None:
        if self.fail_connects:
            self.fail_connects -= 1
            raise SP611EConnectionError("cihaz meşgul")
        self.connected = True
        self.events.append("connect")

    async def disconnect(self) -> None:
        if self.connected:
            self.events.append("disconnect")
        self.connected = False

    async def write(self, frame: bytes) -> None:
        self.events.append(bytes(frame))

    async def write_many(self, frames) -> None:
        for f in frames:
            await self.write(f)


def _make_bridge(
    devices: List[_Device],
    session: Optional[_FakeSession] = None,
    **overrides,
) -> Tuple[OpenRGBBridge, _Client, _FakeSession, List[str]]:
    client = _Client(devices)
    session = session or _FakeSession()
    messages: List[str] = []
    cfg = dict(mac="AA:BB:CC:DD:EE:FF", fps=200.0, idle_timeout=0.0)
    cfg.update(overrides)
    bridge = OpenRGBBridge(
        BridgeConfig(**cfg),
        client_factory=lambda host, port: client,
        session_factory=lambda: session,
        status=messages.append,
    )
    return bridge, client, session, messages


async def _run_until(bridge: OpenRGBBridge, predicate, timeout: float = 2.0) -> None:
    task = asyncio.create_task(bridge.run())
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            bridge.stop()
            await task
            raise AssertionError("bridge did not reach expected state in time")
        await asyncio.sleep(0.005)
    bridge.stop()
    await task


# --- reduce_colors ---------------------------------------------------------


def test_reduce_avg_rounds_channel_means() -> None:
    colors = [(255, 0, 10), (0, 255, 11), (0, 0, 12)]
    assert reduce_colors(colors, "avg") == (85, 85, 11)


def test_reduce_first_and_brightest_and_index() -> None:
    colors = [_Color(1, 2, 3), _Color(200, 200, 200), _Color(9, 9, 9)]
    assert reduce_colors(colors, "first") == (1, 2, 3)
    assert reduce_colors(colors, "brightest") == (200, 200, 200)
    assert reduce_colors(colors, "2") == (9, 9, 9)


def test_reduce_rejects_empty_and_bad_index() -> None:
    with pytest.raises(BridgeConfigError, match="LED bulunamadı"):
        reduce_colors([], "avg")
    with pytest.raises(BridgeConfigError, match="aralık dışında"):
        reduce_colors([(1, 1, 1)], "5")


def test_config_validates_pick_fps_brightness() -> None:
    with pytest.raises(BridgeConfigError, match="pick"):
        BridgeConfig(mac="X", pick="median")
    with pytest.raises(BridgeConfigError, match="fps"):
        BridgeConfig(mac="X", fps=0)
    with pytest.raises(BridgeConfigError, match="Parlaklık"):
        BridgeConfig(mac="X", brightness=300)
    BridgeConfig(mac="X", pick="3")  # LED index is fine


# --- select_source ---------------------------------------------------------


def _two_devices() -> List[_Device]:
    return [
        _Device("ASUS Aura Motherboard", [_Zone("Backplate", [(0, 0, 0)]), _Zone("RGB Header", [(0, 0, 0)] * 3)]),
        _Device("Corsair Vengeance RAM", [_Zone("DRAM", [(0, 0, 0)] * 8)]),
    ]


def test_select_single_device_without_selector() -> None:
    assert select_source(_two_devices()[:1], None, None) == (0, None)


def test_select_requires_selector_when_multiple() -> None:
    with pytest.raises(BridgeConfigError, match="--device"):
        select_source(_two_devices(), None, None)


def test_select_by_index_name_fragment_and_zone() -> None:
    devices = _two_devices()
    assert select_source(devices, "1", None) == (1, None)
    assert select_source(devices, "corsair", None) == (1, None)
    assert select_source(devices, "aura", "header") == (0, 1)
    assert select_source(devices, "ASUS Aura Motherboard", "0") == (0, 0)


def test_select_reports_unknown_and_ambiguous() -> None:
    devices = _two_devices()
    with pytest.raises(BridgeConfigError, match="bulunamadı"):
        select_source(devices, "nanoleaf", None)
    with pytest.raises(BridgeConfigError, match="birden fazla"):
        select_source(devices, "a", None)  # matches both names
    with pytest.raises(BridgeConfigError, match="zone"):
        select_source(devices, "corsair", "7")


def test_describe_devices_lists_zones() -> None:
    text = describe_devices(_two_devices())
    assert "[0] ASUS Aura Motherboard  (4 LED)" in text
    assert "zone [1] RGB Header  (3 LED)" in text
    assert describe_devices([]) == "OpenRGB'de hiç cihaz yok."


# --- bridge loop -----------------------------------------------------------


def test_bridge_sends_setup_then_color_and_dedupes() -> None:
    device = _Device("Strip", [_Zone("Z", [(255, 0, 0), (255, 0, 0)])])
    bridge, client, session, _ = _make_bridge([device])

    async def _run() -> None:
        # First color pushed once, then several polls with no change -> nothing more.
        await _run_until(bridge, lambda: device.updates >= 5)

    asyncio.run(_run())

    assert session.events == ["connect", POWER_ON, STATIC_MODE, rgb_frame(255, 0, 0), "disconnect"]
    assert bridge.frames_sent == 3
    assert client.disconnected is True


def test_bridge_pushes_only_rgb_on_change_and_uses_brightness() -> None:
    device = _Device("Strip", [_Zone("Z", [(0, 0, 255)])])
    bridge, _, session, _ = _make_bridge([device], brightness=128, power_on=False)

    async def _run() -> None:
        task = asyncio.create_task(bridge.run())
        while rgb_frame(0, 0, 255, 128) not in session.events:
            await asyncio.sleep(0.005)
        device.set(0, 255, 0)
        while rgb_frame(0, 255, 0, 128) not in session.events:
            await asyncio.sleep(0.005)
        bridge.stop()
        await task

    asyncio.run(_run())

    assert session.events == [
        "connect",
        STATIC_MODE,
        rgb_frame(0, 0, 255, 128),
        rgb_frame(0, 255, 0, 128),
        "disconnect",
    ]


def test_bridge_follows_zone_only() -> None:
    device = _Device("Board", [_Zone("A", [(255, 255, 255)]), _Zone("B", [(10, 20, 30)])])
    bridge, _, session, messages = _make_bridge([device], zone="B")

    asyncio.run(_run_until(bridge, lambda: rgb_frame(10, 20, 30) in session.events))

    assert rgb_frame(255, 255, 255) not in session.events
    assert any("zone [1] B" in m for m in messages)


def test_bridge_idle_timeout_releases_ble_and_reconnects_on_change() -> None:
    device = _Device("Strip", [_Zone("Z", [(1, 2, 3)])])
    bridge, _, session, messages = _make_bridge([device], idle_timeout=0.05)

    async def _run() -> None:
        task = asyncio.create_task(bridge.run())
        while session.events.count("disconnect") < 1:
            await asyncio.sleep(0.005)
        assert not session.connected
        device.set(4, 5, 6)
        while rgb_frame(4, 5, 6) not in session.events:
            await asyncio.sleep(0.005)
        bridge.stop()
        await task

    asyncio.run(_run())

    assert session.events == [
        "connect", POWER_ON, STATIC_MODE, rgb_frame(1, 2, 3),
        "disconnect",  # idle
        "connect", POWER_ON, STATIC_MODE, rgb_frame(4, 5, 6),  # mode re-sent on reconnect
        "disconnect",  # stop
    ]
    assert any("renk değişmedi" in m for m in messages)


def test_bridge_retries_after_ble_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge_mod, "BLE_RETRY_DELAY", 0.01)
    device = _Device("Strip", [_Zone("Z", [(7, 7, 7)])])
    session = _FakeSession()
    session.fail_connects = 2
    bridge, _, session, messages = _make_bridge([device], session=session)

    asyncio.run(_run_until(bridge, lambda: rgb_frame(7, 7, 7) in session.events))

    assert sum(1 for m in messages if "BLE hatası" in m) == 2
    assert session.events[:4] == ["connect", POWER_ON, STATIC_MODE, rgb_frame(7, 7, 7)]


def test_bridge_retries_when_openrgb_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge_mod, "OPENRGB_RETRY_DELAY", 0.01)
    device = _Device("Strip", [_Zone("Z", [(9, 8, 7)])])
    client = _Client([device])
    attempts = {"n": 0}

    def _factory(host: str, port: int) -> _Client:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionRefusedError("no server")
        return client

    session = _FakeSession()
    messages: List[str] = []
    bridge = OpenRGBBridge(
        BridgeConfig(mac="AA:BB:CC:DD:EE:FF", fps=200.0, idle_timeout=0),
        client_factory=_factory,
        session_factory=lambda: session,
        status=messages.append,
    )

    asyncio.run(_run_until(bridge, lambda: rgb_frame(9, 8, 7) in session.events))

    assert attempts["n"] == 3
    assert sum(1 for m in messages if "bağlanılamadı" in m) == 2


def test_bridge_reconnects_when_openrgb_drops(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge_mod, "OPENRGB_RETRY_DELAY", 0.01)
    device = _Device("Strip", [_Zone("Z", [(1, 1, 1)])])
    clients: List[_Client] = []

    def _factory(host: str, port: int) -> _Client:
        c = _Client([device])
        clients.append(c)
        return c

    original_update = device.update

    def _flaky_update() -> None:
        original_update()
        if device.updates == 3:
            raise ConnectionError("socket closed")

    device.update = _flaky_update  # type: ignore[method-assign]
    session = _FakeSession()
    bridge = OpenRGBBridge(
        BridgeConfig(mac="AA:BB:CC:DD:EE:FF", fps=200.0, idle_timeout=0),
        client_factory=_factory,
        session_factory=lambda: session,
        status=lambda _m: None,
    )

    asyncio.run(_run_until(bridge, lambda: len(clients) >= 2 and device.updates >= 5))

    assert clients[0].disconnected is True
    # BLE session was closed on the OpenRGB drop and reopened afterwards.
    assert session.events.count("connect") == 2


def test_bridge_surfaces_bad_selection() -> None:
    bridge, _, _, _ = _make_bridge(_two_devices(), device="nope")
    with pytest.raises(BridgeConfigError, match="bulunamadı"):
        asyncio.run(bridge.run())
