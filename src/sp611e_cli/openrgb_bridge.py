"""OpenRGB SDK bridge: mirror an OpenRGB device's color onto the SP611E.

OpenRGB's SDK lets clients *read and control* the devices OpenRGB already
knows about; it cannot register new devices. So instead of appearing inside
OpenRGB, the SP611E follows one of its devices (or a single zone of it): the
bridge polls the SDK server, reduces the LED colors to one RGB value and
pushes it to the strip over a persistent BLE session (see SP611ESession).

The OpenRGB client library (openrgb-python) is synchronous; its blocking calls
are run in a worker thread via asyncio.to_thread so the BLE side stays async.
"""

import asyncio
from dataclasses import dataclass
import logging
import time
from typing import Any, Callable, Optional, Sequence, Tuple

from sp611e_cli.device import SP611EController, SP611EError, SP611ESession
from sp611e_cli.protocol import (
    create_set_rgb_command,
    create_static_color_mode_command,
    create_turn_on_command,
)

logger = logging.getLogger(__name__)

RGB = Tuple[int, int, int]

PICK_STRATEGIES: Tuple[str, ...] = ("avg", "first", "brightest")

# Wait this long before retrying after the OpenRGB server or the BLE link fails.
OPENRGB_RETRY_DELAY: float = 3.0
BLE_RETRY_DELAY: float = 2.0


class BridgeConfigError(ValueError):
    """Raised for invalid bridge settings or unresolvable device/zone selection."""


@dataclass
class BridgeConfig:
    """User-facing settings for one bridge run."""

    mac: str
    host: str = "127.0.0.1"
    port: int = 6742
    device: Optional[str] = None      # OpenRGB device: index or (partial) name; None = the only device
    zone: Optional[str] = None        # zone of that device: index or (partial) name; None = whole device
    pick: str = "avg"                 # avg | first | brightest | LED index
    fps: float = 10.0                 # OpenRGB poll rate (upper bound of BLE update rate)
    brightness: int = 255             # level byte folded into the RGB frame
    idle_timeout: float = 30.0        # release BLE after N s without a color change; 0 = keep forever
    power_on: bool = True             # send "power on" when the BLE session is (re)opened

    def __post_init__(self) -> None:
        if self.fps <= 0:
            raise BridgeConfigError("fps 0'dan büyük olmalıdır.")
        if not (0 <= self.brightness <= 255):
            raise BridgeConfigError("Parlaklık 0 ile 255 arasında olmalıdır.")
        if self.idle_timeout < 0:
            raise BridgeConfigError("idle-timeout negatif olamaz.")
        if self.pick not in PICK_STRATEGIES and not self.pick.isdigit():
            raise BridgeConfigError(
                f"Geçersiz --pick değeri: '{self.pick}'. Seçenekler: {', '.join(PICK_STRATEGIES)} veya LED indeksi."
            )


def reduce_colors(colors: Sequence[Any], pick: str) -> RGB:
    """Collapse a list of OpenRGB LED colors into the single color the strip will show.

    Args:
        colors: Objects with .red/.green/.blue attributes (openrgb RGBColor) or (r, g, b) tuples.
        pick: "avg" (channel mean), "first", "brightest" (highest R+G+B) or a LED index.

    Raises:
        BridgeConfigError: On empty input or an out-of-range LED index.
    """
    triples = [_as_triple(c) for c in colors]
    if not triples:
        raise BridgeConfigError("Kaynak cihazda LED bulunamadı.")

    if pick == "avg":
        n = len(triples)
        return tuple(int(round(sum(t[i] for t in triples) / n)) for i in range(3))  # type: ignore[return-value]
    if pick == "first":
        return triples[0]
    if pick == "brightest":
        return max(triples, key=sum)
    if pick.isdigit():
        index = int(pick)
        if index >= len(triples):
            raise BridgeConfigError(f"LED indeksi {index} aralık dışında (cihazda {len(triples)} LED var).")
        return triples[index]
    raise BridgeConfigError(f"Geçersiz pick stratejisi: '{pick}'")


def _as_triple(color: Any) -> RGB:
    if isinstance(color, tuple):
        r, g, b = color
    else:
        r, g, b = color.red, color.green, color.blue
    return int(r), int(g), int(b)


def describe_devices(devices: Sequence[Any]) -> str:
    """Render the OpenRGB device list (with zones) for --list and error messages."""
    if not devices:
        return "OpenRGB'de hiç cihaz yok."
    lines = []
    for index, dev in enumerate(devices):
        if dev is None:
            continue
        lines.append(f"[{index}] {dev.name}  ({len(dev.leds)} LED)")
        for z_index, zone in enumerate(dev.zones):
            lines.append(f"      zone [{z_index}] {zone.name}  ({len(zone.leds)} LED)")
    return "\n".join(lines)


def select_source(devices: Sequence[Any], device_sel: Optional[str], zone_sel: Optional[str]) -> Tuple[int, Optional[int]]:
    """Resolve --device/--zone selectors to (device_index, zone_index or None).

    A selector may be an index or a case-insensitive name fragment; an exact
    name match wins over partial matches. With no --device the bridge only
    proceeds when OpenRGB exposes exactly one device.

    Raises:
        BridgeConfigError: When the selection is missing, ambiguous or unknown.
    """
    live = [(i, d) for i, d in enumerate(devices) if d is not None]
    if not live:
        raise BridgeConfigError("OpenRGB'de hiç cihaz bulunamadı. OpenRGB açık ve cihazları algılamış mı?")

    if device_sel is None:
        if len(live) != 1:
            raise BridgeConfigError(
                "Birden fazla OpenRGB cihazı var; hangisinin takip edileceğini --device ile seçin:\n"
                + describe_devices(devices)
            )
        dev_index = live[0][0]
    else:
        dev_index = _match_selector(live, device_sel, "cihaz", describe_devices(devices))

    if zone_sel is None:
        return dev_index, None

    zones = [(i, z) for i, z in enumerate(devices[dev_index].zones)]
    if not zones:
        raise BridgeConfigError(f"'{devices[dev_index].name}' cihazının hiç zone'u yok.")
    zone_index = _match_selector(zones, zone_sel, "zone", describe_devices(devices))
    return dev_index, zone_index


def _match_selector(candidates: Sequence[Tuple[int, Any]], selector: str, kind: str, listing: str) -> int:
    selector = selector.strip()
    if selector.isdigit():
        index = int(selector)
        if any(i == index for i, _ in candidates):
            return index
        raise BridgeConfigError(f"{kind} indeksi {index} bulunamadı.\n{listing}")

    needle = selector.lower()
    exact = [i for i, obj in candidates if obj.name.lower() == needle]
    if len(exact) == 1:
        return exact[0]
    partial = [i for i, obj in candidates if needle in obj.name.lower()]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        raise BridgeConfigError(f"'{selector}' adında bir {kind} bulunamadı.\n{listing}")
    raise BridgeConfigError(
        f"'{selector}' birden fazla {kind} ile eşleşiyor; daha belirgin bir ad veya indeks verin.\n{listing}"
    )


def _default_client_factory(host: str, port: int) -> Any:
    from openrgb import OpenRGBClient

    return OpenRGBClient(address=host, port=port, name="sp611e-bridge")


class OpenRGBBridge:
    """Poll OpenRGB and stream the reduced color to the SP611E until stopped."""

    def __init__(
        self,
        config: BridgeConfig,
        controller: Optional[SP611EController] = None,
        *,
        client_factory: Callable[[str, int], Any] = _default_client_factory,
        session_factory: Optional[Callable[[], SP611ESession]] = None,
        status: Callable[[str], None] = logger.info,
    ) -> None:
        self.config = config
        self._controller = controller or SP611EController(mac_address=config.mac)
        self._client_factory = client_factory
        self._session_factory = session_factory or self._controller.session
        self._status = status
        self._stop = asyncio.Event()
        self.last_color: Optional[RGB] = None
        self.frames_sent: int = 0

    def stop(self) -> None:
        """Ask run() to return after the current iteration."""
        self._stop.set()

    async def run(self) -> None:
        """Main loop: (re)connect to OpenRGB, mirror until stopped, retry on failures."""
        while not self._stop.is_set():
            try:
                client = await asyncio.to_thread(self._client_factory, self.config.host, self.config.port)
            except OSError as exc:
                self._status(
                    f"OpenRGB SDK sunucusuna bağlanılamadı ({self.config.host}:{self.config.port}): {exc}. "
                    f"{OPENRGB_RETRY_DELAY:.0f} sn sonra tekrar denenecek (OpenRGB > Settings > SDK Server açık mı?)"
                )
                await self._sleep(OPENRGB_RETRY_DELAY)
                continue

            try:
                dev_index, zone_index = select_source(client.devices, self.config.device, self.config.zone)
                self._status(f"OpenRGB kaynağı: {self._source_label(client, dev_index, zone_index)}")
                await self._mirror(client, dev_index, zone_index)
            except ConnectionError as exc:  # openrgb.utils.OpenRGBDisconnected subclasses ConnectionError
                self._status(f"OpenRGB bağlantısı koptu: {exc}. Yeniden bağlanılacak...")
                await self._sleep(OPENRGB_RETRY_DELAY)
            finally:
                try:
                    await asyncio.to_thread(client.disconnect)
                except Exception:  # best-effort cleanup of a possibly dead socket
                    pass

    async def _mirror(self, client: Any, dev_index: int, zone_index: Optional[int]) -> None:
        interval = 1.0 / self.config.fps
        session = self._session_factory()
        self.last_color = None
        last_change = time.monotonic()
        try:
            while not self._stop.is_set():
                tick = time.monotonic()
                color = await asyncio.to_thread(self._poll, client, dev_index, zone_index)

                if color != self.last_color:
                    if await self._push(session, color):
                        self.last_color = color
                        last_change = tick
                    else:
                        await self._sleep(BLE_RETRY_DELAY)
                        continue
                elif (
                    self.config.idle_timeout
                    and session.connected
                    and tick - last_change >= self.config.idle_timeout
                ):
                    await session.disconnect()
                    self._status(
                        f"{self.config.idle_timeout:.0f} sn boyunca renk değişmedi; BLE bağlantısı bırakıldı "
                        "(değişiklikte otomatik yeniden bağlanır)."
                    )

                await self._sleep(max(0.0, interval - (time.monotonic() - tick)))
        finally:
            await session.disconnect()

    def _poll(self, client: Any, dev_index: int, zone_index: Optional[int]) -> RGB:
        """Refresh the source from the SDK and reduce it to one color (runs in a worker thread)."""
        # Look the objects up fresh each time: OpenRGB may rebuild the device
        # list (DEVICE_LIST_UPDATED), which replaces the Device instances.
        try:
            device = client.devices[dev_index]
        except IndexError:
            device = None
        if device is None:
            raise ConnectionError("OpenRGB cihaz listesi değişti")
        device.update()
        source = device.zones[zone_index] if zone_index is not None else device
        return reduce_colors(source.colors, self.config.pick)

    async def _push(self, session: SP611ESession, color: RGB) -> bool:
        """Send the color; open the session (with mode setup) first if needed. Returns success."""
        frames = []
        try:
            if not session.connected:
                await session.connect()
                if self.config.power_on:
                    frames.append(create_turn_on_command())
                # Static mode must be selected once per connection, otherwise a
                # running effect keeps playing and swallows the RGB frames.
                frames.append(create_static_color_mode_command())
            frames.append(create_set_rgb_command(*color, brightness=self.config.brightness))
            await session.write_many(frames)
        except SP611EError as exc:
            self._status(f"BLE hatası: {exc}\n{BLE_RETRY_DELAY:.0f} sn sonra tekrar denenecek.")
            await session.disconnect()
            return False

        self.frames_sent += len(frames)
        logger.debug("OpenRGB -> SP611E renk: #%02X%02X%02X", *color)
        return True

    async def _sleep(self, seconds: float) -> None:
        """Sleep unless stop() is called first."""
        if seconds <= 0:
            return
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    @staticmethod
    def _source_label(client: Any, dev_index: int, zone_index: Optional[int]) -> str:
        device = client.devices[dev_index]
        if zone_index is None:
            return f"[{dev_index}] {device.name} ({len(device.leds)} LED)"
        zone = device.zones[zone_index]
        return f"[{dev_index}] {device.name} / zone [{zone_index}] {zone.name} ({len(zone.leds)} LED)"
