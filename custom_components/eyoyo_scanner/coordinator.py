"""BLE coordinator for the Eyoyo EY-015P scanner.

Maintains a persistent, bonded BLE connection and subscribes to native GATT
notifications on characteristic 0x2AA1 (service 0xFEEA). Confirmed via a
Bluetooth HCI snoop capture: the scanner pushes a genuine notification (ATT
opcode 0x1b, standard NOTIFY bit) on every scan, fully asynchronously - the
attribute never reflects the data on a direct read, so no polling is needed
or useful for the scan data itself.

Data format (confirmed empirically): raw ASCII text of the scanned code,
terminated by a carriage return (0x0D). May arrive fragmented across several
notification packets when it exceeds the ATT_MTU-3 payload (20 bytes by
default) - fragments are buffered until the terminator is seen.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from bleak import BleakClient
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CHAR_UUID_SCAN_DATA,
    EVENT_BARCODE_SCANNED,
    SCAN_VALUE_TERMINATOR,
    SOURCE_BLE_DIRECT,
)

_LOGGER = logging.getLogger(__name__)

LIVENESS_CHECK_INTERVAL_SECONDS = 5


class EyoyoScannerCoordinator:
    """Manages the persistent BLE connection and the scanner's notifications."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        self.hass = hass
        self.address = address
        self._client: BleakClient | None = None
        self._notify_buffer = bytearray()
        self._liveness_unsub = None
        self._connect_lock = asyncio.Lock()
        self._stopped = False

        self.last_code: str | None = None
        self.last_scanned_at: str | None = None
        self.connected: bool = False
        self._listeners: list = []

        # HA/habluetooth can dynamically reroute to a different BLE proxy on
        # every connection attempt, without regard for which one actually
        # holds the bond - a documented upstream bug (habluetooth #628/#602).
        # We therefore pin the first source that succeeds ourselves and
        # prefer it on subsequent attempts, instead of letting HA re-pick
        # "the best" one every time.
        self._pinned_source: str | None = None

    def async_add_listener(self, callback) -> None:
        """Register a callback invoked on every newly decoded code."""
        self._listeners.append(callback)

    def async_remove_listener(self, callback) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    async def async_start(self) -> None:
        """Start the connection and the notification subscription."""
        self._stopped = False
        await self._async_ensure_connected()
        self._liveness_unsub = async_track_time_interval(
            self.hass,
            self._async_liveness_tick,
            timedelta(seconds=LIVENESS_CHECK_INTERVAL_SECONDS),
        )

    async def async_stop(self) -> None:
        """Stop the liveness check and close the connection."""
        self._stopped = True
        if self._liveness_unsub is not None:
            self._liveness_unsub()
            self._liveness_unsub = None
        if self._client is not None and self._client.is_connected:
            await self._client.disconnect()
        self._client = None
        self.connected = False

    def _handle_notification(self, _sender, data: bytearray) -> None:
        """bleak callback invoked on every incoming notification packet.

        Buffers fragments until the terminator (CR) is seen - a scanned
        code can arrive split across multiple packets when it exceeds the
        ATT_MTU-3 payload (see the HCI capture referenced in the README).
        """
        self._notify_buffer.extend(data)

        if SCAN_VALUE_TERMINATOR not in self._notify_buffer:
            return

        raw, _, remainder = bytes(self._notify_buffer).partition(SCAN_VALUE_TERMINATOR)
        self._notify_buffer = bytearray(remainder)

        code = raw.decode("ascii", errors="ignore").strip()
        if not code:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        self.last_code = code
        self.last_scanned_at = now_iso

        _LOGGER.info("Scanned code (Eyoyo BLE): %s", code)
        self.hass.bus.async_fire(
            EVENT_BARCODE_SCANNED,
            {"code": code, "source": SOURCE_BLE_DIRECT, "address": self.address},
        )
        for cb in list(self._listeners):
            cb()

    async def _async_liveness_tick(self, _now) -> None:
        """Periodically checks the connection is still alive and reconnects
        if needed - no data is read here, scan data arrives exclusively via
        _handle_notification()."""
        if self._stopped:
            return
        if self._client is not None and self._client.is_connected:
            return
        await self._async_ensure_connected()

    async def _async_ensure_connected(self) -> bool:
        """Establishes (or re-establishes) the bonded BLE connection. Returns
        True if connected."""
        if self._client is not None and self._client.is_connected:
            return True

        async with self._connect_lock:
            if self._client is not None and self._client.is_connected:
                return True

            candidates = self._async_candidate_ble_devices()
            if not candidates:
                _LOGGER.debug(
                    "Eyoyo scanner %s not currently visible (out of range or "
                    "no Bluetooth proxy sees it)", self.address
                )
                self.connected = False
                return False

            for source, ble_device in candidates:
                client = await self._async_try_connect_via(source, ble_device)
                if client is not None:
                    self._client = client
                    self._pinned_source = source
                    self._notify_buffer = bytearray()  # fresh connection = no fragment in flight
                    self.connected = True
                    _LOGGER.info(
                        "Eyoyo scanner connected, bonded and subscribed via source=%s: %s",
                        source, self.address,
                    )
                    return True

            _LOGGER.debug(
                "None of the %d available source(s) could establish a "
                "bonded connection to the Eyoyo scanner", len(candidates)
            )
            self.connected = False
            return False

    def _async_candidate_ble_devices(self) -> list[tuple[str, object]]:
        """Returns the (source, ble_device) pairs to try, pinned source first.

        HA/habluetooth can see the same device through several BLE proxies at
        once (common with multiple ESPHome proxies in the house) - we try
        them all ourselves as needed instead of letting HA automatically pick
        "the best" one (see the comment on self._pinned_source).
        """
        scanner_devices = bluetooth.async_scanner_devices_by_address(
            self.hass, self.address, connectable=True
        )
        candidates = [(sd.scanner.source, sd.ble_device) for sd in scanner_devices]

        if self._pinned_source:
            candidates.sort(key=lambda c: c[0] != self._pinned_source)

        if not candidates:
            # Fall back to the simple API if the per-scanner list is empty
            # for some reason (shouldn't happen in practice).
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if ble_device is not None:
                candidates = [("unknown", ble_device)]

        return candidates

    async def _async_try_connect_via(self, source: str, ble_device) -> BleakClient | None:
        """Attempts connect+pair+notify subscription via a given source. None
        on failure.

        Unconditional pair() confirmed necessary (validated via a side-by-side
        manual test with a generic BLE scanner app): without an explicit
        bond, the subscription succeeds without raising an exception but
        never actually receives a notification.
        """
        try:
            client = await establish_connection(BleakClient, ble_device, self.address)
        except (BleakError, TimeoutError, asyncio.TimeoutError) as err:
            _LOGGER.debug("Connection failed via source=%s: %s", source, err)
            return None

        try:
            await client.pair()
            _LOGGER.info("pair() succeeded (source=%s)", source)
        except (BleakError, NotImplementedError) as err:
            _LOGGER.debug("pair() failed or already bonded (source=%s): %s", source, err)

        try:
            await client.start_notify(CHAR_UUID_SCAN_DATA, self._handle_notification)
        except BleakError as err:
            _LOGGER.warning(
                "Failed to subscribe to 0x2AA1 notifications (source=%s): %s",
                source, err,
            )
            try:
                await client.disconnect()
            except BleakError:
                pass
            return None

        return client
