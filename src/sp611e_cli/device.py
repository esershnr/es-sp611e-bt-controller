"""BLE device management and communication using Bleak for SP611E."""

import asyncio
from dataclasses import dataclass
import logging
from typing import Iterable, List, Optional
import weakref

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import BleakDeviceNotFoundError, BleakError

logger = logging.getLogger(__name__)

# UUIDs for SP611E (BanlanX)
SP611E_SERVICE_UUID: str = "0000ffe0-0000-1000-8000-00805f9b34fb"
SP611E_WRITE_CHAR_UUID: str = "0000ffe1-0000-1000-8000-00805f9b34fb"

# Small pause between consecutive frames on the same connection so the
# controller has time to apply a mode switch before the next frame arrives.
INTER_FRAME_DELAY: float = 0.05

# The SP611E accepts only ONE BLE connection at a time. The web dashboard can
# fire several requests concurrently (slider drags, color wheel), and parallel
# BleakClient connections to the same device fail with confusing errors such as
# "Characteristic ffe1 was not found". Serialize all device access per event loop
# (the CLI spins up a fresh loop per asyncio.run(), so keep one lock per loop).
_ble_locks: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = (
    weakref.WeakKeyDictionary()
)


def _get_ble_lock() -> asyncio.Lock:
    """Return the BLE access lock bound to the currently running event loop."""
    loop = asyncio.get_running_loop()
    lock = _ble_locks.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _ble_locks[loop] = lock
    return lock


class SP611EError(Exception):
    """Base exception for SP611E communication errors."""


class SP611EDeviceNotFoundError(SP611EError):
    """Raised when the specified SP611E device cannot be found."""


class SP611EConnectionError(SP611EError):
    """Raised when connection to SP611E fails or is interrupted."""


class SP611ECommandError(SP611EError):
    """Raised when writing a command to the device fails."""


@dataclass
class DiscoveredDevice:
    """Represents a discovered BLE device."""

    address: str
    name: str
    rssi: int
    is_sp611e: bool


class SP611EController:
    """Handles BLE connection and command dispatching to an SP611E controller."""

    def __init__(self, mac_address: str, timeout: float = 10.0) -> None:
        """Initialize controller with target device MAC address.

        Args:
            mac_address: Bluetooth MAC address (e.g. 'AA:BB:CC:DD:EE:FF').
            timeout: Connection/operation timeout in seconds.
        """
        self.mac_address = mac_address.strip().upper()
        self.timeout = timeout
        self._client: Optional[BleakClient] = None

    async def send_command(self, command_bytes: bytes) -> None:
        """Connect to device, send a single command frame, and disconnect.

        Args:
            command_bytes: Raw bytes to send to the write characteristic.

        Raises:
            SP611EDeviceNotFoundError: If device is not found in range.
            SP611EConnectionError: If connection fails (e.g. app already connected).
            SP611ECommandError: If GATT write operation fails.
        """
        await self.send_commands([command_bytes])

    async def send_commands(self, frames: Iterable[bytes]) -> None:
        """Connect once, send every frame in order, then disconnect.

        Multi-frame sequences (e.g. "switch to static mode" + "set color") must go
        over a single connection: each connect/disconnect cycle costs 1-4 seconds
        on this controller and the device may drop state between them.

        Args:
            frames: Raw frames to send sequentially to the write characteristic.

        Raises:
            SP611EDeviceNotFoundError: If device is not found in range.
            SP611EConnectionError: If connection fails (e.g. app already connected).
            SP611ECommandError: If GATT write operation fails.
        """
        frames = [bytes(f) for f in frames]
        if not frames:
            return

        async with _get_ble_lock():
            logger.info("Cihaza bağlanılıyor: %s (Timeout: %ss)", self.mac_address, self.timeout)
            for frame in frames:
                logger.debug("Gönderilecek veri (Hex): %s (Uzunluk: %d byte)", frame.hex(' ').upper(), len(frame))
            try:
                async with BleakClient(self.mac_address, timeout=self.timeout) as client:
                    logger.info("BLE bağlantısı kuruldu -> %s", self.mac_address)
                    for index, frame in enumerate(frames):
                        if index > 0:
                            await asyncio.sleep(INTER_FRAME_DELAY)
                        await self._write_frame(client, frame)
                        logger.info("Komut başarıyla iletildi: %s", frame.hex(' ').upper())

            except (BleakDeviceNotFoundError, asyncio.TimeoutError, BleakError) as exc:
                raise self._translate_connect_error(exc) from exc

    def session(self) -> "SP611ESession":
        """Return a long-lived connection handle (see SP611ESession)."""
        return SP611ESession(self)

    def _translate_connect_error(self, exc: BaseException) -> SP611EError:
        """Map Bleak/asyncio connection failures to user-facing SP611E exceptions."""
        if isinstance(exc, BleakDeviceNotFoundError):
            logger.error("Cihaz bulunamadı: %s", self.mac_address)
            return SP611EDeviceNotFoundError(
                f"'{self.mac_address}' adresli cihaz kapsama alanında bulunamadı.\n"
                "Lütfen cihazın açık, menzil içinde ve Bluetooth'unuzun aktif olduğundan emin olun."
            )

        if isinstance(exc, asyncio.TimeoutError):
            logger.error("Bağlantı zaman aşımı: %s", self.mac_address)
            return SP611EConnectionError(
                f"'{self.mac_address}' adresli cihaza bağlanırken zaman aşımı oluştu.\n"
                "Cihaz meşgul olabilir veya sinyal çok zayıf olabilir."
            )

        logger.error("Bleak hatası (%s): %s", self.mac_address, exc)
        err_msg = str(exc).lower()
        if "not powered on" in err_msg or "powered_off" in err_msg:
            return SP611EConnectionError(
                "Bilgisayarınızın Bluetooth'u kapalı görünüyor.\n"
                "Lütfen Bluetooth'u açın ve tekrar deneyin."
            )
        return SP611EConnectionError(
            f"Cihaza bağlanılamadı ({exc}).\n\n"
            "ÖNEMLİ: SP611E aynı anda yalnızca TEK BİR Bluetooth bağlantısını destekler!\n"
            "Eğer telefonunuzda BanlanX uygulaması açıksa veya cihaza başka bir telefon/bilgisayar "
            "bağlıysa, lütfen o bağlantıyı kapatıp tekrar deneyin."
        )

    @staticmethod
    async def _write_frame(client: BleakClient, frame: bytes) -> None:
        """Write one frame to the SP611E characteristic, falling back to write-with-response."""
        # SP611E characteristics typically use write without response
        try:
            await client.write_gatt_char(SP611E_WRITE_CHAR_UUID, frame, response=False)
        except BleakError as write_err:
            logger.warning("Write without response başarısız oldu, response=True deneniyor: %s", write_err)
            try:
                await client.write_gatt_char(SP611E_WRITE_CHAR_UUID, frame, response=True)
            except Exception as fallback_err:
                logger.error("Komut yazma hatası: %s", fallback_err)
                raise SP611ECommandError(f"Komut gönderilemedi: {fallback_err}") from write_err


class SP611ESession:
    """A long-lived BLE connection for streaming many frames over time.

    send_commands() connects and disconnects per call, which costs 1-4 seconds
    on this controller. Sync/mirroring use cases (e.g. the OpenRGB bridge) need
    to push a color several times per second, so this handle keeps the
    connection open between writes. The BLE lock is held for the whole lifetime
    of the connection: the SP611E accepts a single connection, so other callers
    in this process queue until disconnect() releases it.

    Usage:
        async with controller.session() as session:
            await session.write_many(frames)
    """

    def __init__(self, controller: SP611EController) -> None:
        self._controller = controller
        self._client: Optional[BleakClient] = None
        self._lock: Optional[asyncio.Lock] = None

    @property
    def connected(self) -> bool:
        """True while the underlying BleakClient reports an active connection."""
        return self._client is not None and bool(self._client.is_connected)

    async def __aenter__(self) -> "SP611ESession":
        await self.connect()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        """Acquire the BLE lock and open the connection (no-op if already connected)."""
        if self._client is not None:
            if self._client.is_connected:
                return
            # Device dropped the link on its side; clean up before reconnecting.
            await self.disconnect()

        mac = self._controller.mac_address
        lock = _get_ble_lock()
        await lock.acquire()
        self._lock = lock
        logger.info("Kalıcı BLE oturumu açılıyor: %s (Timeout: %ss)", mac, self._controller.timeout)
        client = BleakClient(mac, timeout=self._controller.timeout)
        try:
            await client.connect()
        except (BleakDeviceNotFoundError, asyncio.TimeoutError, BleakError) as exc:
            self._release_lock()
            raise self._controller._translate_connect_error(exc) from exc
        except BaseException:
            self._release_lock()
            raise
        self._client = client
        logger.info("BLE bağlantısı kuruldu -> %s", mac)

    async def write(self, frame: bytes) -> None:
        """Write one frame over the open connection.

        Raises:
            SP611EConnectionError: If the session is not connected (or the link dropped).
            SP611ECommandError: If the GATT write fails.
        """
        if not self.connected:
            raise SP611EConnectionError(
                f"'{self._controller.mac_address}' ile aktif bir BLE oturumu yok (bağlantı kopmuş olabilir)."
            )
        frame = bytes(frame)
        logger.debug("Gönderilecek veri (Hex): %s (Uzunluk: %d byte)", frame.hex(' ').upper(), len(frame))
        await SP611EController._write_frame(self._client, frame)  # type: ignore[arg-type]

    async def write_many(self, frames: Iterable[bytes]) -> None:
        """Write frames in order, pausing INTER_FRAME_DELAY between them."""
        for index, frame in enumerate(frames):
            if index > 0:
                await asyncio.sleep(INTER_FRAME_DELAY)
            await self.write(frame)

    async def disconnect(self) -> None:
        """Close the connection and release the BLE lock (safe to call repeatedly)."""
        client, self._client = self._client, None
        if client is None:
            self._release_lock()
            return
        try:
            await client.disconnect()
            logger.info("BLE oturumu kapatıldı -> %s", self._controller.mac_address)
        except Exception as exc:  # disconnect errors are not actionable for callers
            logger.warning("BLE oturumu kapatılırken hata yok sayıldı: %s", exc)
        finally:
            self._release_lock()

    def _release_lock(self) -> None:
        lock, self._lock = self._lock, None
        if lock is not None and lock.locked():
            lock.release()


async def scan_devices(timeout: float = 5.0) -> List[DiscoveredDevice]:
    """Scan for BLE devices and identify potential SP611E controllers.

    Args:
        timeout: Scan duration in seconds.

    Returns:
        List of DiscoveredDevice objects, with identified SP611E controllers sorted first.
    """
    discovered: List[DiscoveredDevice] = []

    try:
        devices_and_adv = await BleakScanner.discover(
            timeout=timeout,
            return_adv=True,
        )
    except BleakError as exc:
        err_msg = str(exc).lower()
        if "not powered on" in err_msg or "powered_off" in err_msg:
            raise SP611EError(
                "Bilgisayarınızın Bluetooth'u kapalı görünüyor.\n"
                "Lütfen Bluetooth'u açın ve tekrar deneyin."
            ) from exc
        raise SP611EError(f"Bluetooth taraması başlatılamadı: {exc}") from exc

    for address, (device, adv) in devices_and_adv.items():
        name = adv.local_name or device.name or "Bilinmeyen Cihaz"

        # Check if service UUID or name matches SP611E characteristics
        service_uuids = [str(uuid).lower() for uuid in (adv.service_uuids or [])]
        is_sp611e = (
            "sp611e" in name.lower()
            or "banlan" in name.lower()
            or any("ffe0" in s for s in service_uuids)
        )

        discovered.append(
            DiscoveredDevice(
                address=address,
                name=name,
                rssi=adv.rssi,
                is_sp611e=is_sp611e,
            )
        )

    # Sort: SP611E devices first, then by signal strength (RSSI descending)
    discovered.sort(key=lambda d: (not d.is_sp611e, -d.rssi))
    return discovered
