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

Battery level: the standard GATT service (0x180F/0x2A19) is an unusable
firmware stub (always 100%). The real level arrives over the SAME
notification channel as scans, in reply to a command written to 0x2AA2 (see
const.py) - distinguished from a real scan by a strict pattern match.
Refreshed via a debounced background task (15s after the last scan, never
during a burst) plus an on-demand button - never on every single scan, which
was found in production to permanently wedge the BLE connection.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone

from bleak import BleakClient
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later, async_track_time_interval

from .const import (
    BATTERY_REFRESH_DEBOUNCE_SECONDS,
    BATTERY_REPLY_PATTERN,
    CHAR_UUID_COMMAND,
    CHAR_UUID_SCAN_DATA,
    CMD_QUERY_BATTERY,
    COMMAND_WRITE_TIMEOUT_SECONDS,
    EVENT_BARCODE_SCANNED,
    SCAN_VALUE_TERMINATOR,
    SOURCE_BLE_DIRECT,
)

_BATTERY_REPLY_RE = re.compile(BATTERY_REPLY_PATTERN)

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
        self._command_lock = asyncio.Lock()
        self._battery_refresh_unsub = None
        self._stopped = False

        self.last_code: str | None = None
        self.last_scanned_at: str | None = None
        self.connected: bool = False
        self.battery_level: int | None = None
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
        if self._battery_refresh_unsub is not None:
            self._battery_refresh_unsub()
            self._battery_refresh_unsub = None
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

        if _BATTERY_REPLY_RE.match(code):
            # Reply to the "Battery Remaining" configuration command - not a
            # real scanned code, do not touch last_code/EVENT_BARCODE_SCANNED.
            self.battery_level = int(code.rstrip("%"))
            _LOGGER.info("Battery level (Eyoyo BLE): %s", code)
            for cb in list(self._listeners):
                cb()
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

        # Refresh the battery level after 15s of INACTIVITY, not after every
        # scan - an earlier "refresh on every scan" approach caused
        # overlapping 0x2AA2 writes during a rapid scanning burst that
        # permanently wedged the BLE connection (confirmed in production:
        # zero timeout/error logged, the write task simply never returned).
        # This scheduling never blocks or delays the scan itself.
        self._schedule_battery_refresh()

    def _schedule_battery_refresh(self) -> None:
        """Schedules a battery refresh 15s after the LATEST scan (debounce)
        - postponed on every new scan, so it only fires once the scanner
        has gone quiet. Guarantees at most one write from this mechanism is
        ever in flight."""
        if self._battery_refresh_unsub is not None:
            self._battery_refresh_unsub()
        self._battery_refresh_unsub = async_call_later(
            self.hass, BATTERY_REFRESH_DEBOUNCE_SECONDS, self._async_battery_refresh_callback
        )

    @callback
    def _async_battery_refresh_callback(self, _now) -> None:
        self._battery_refresh_unsub = None
        if self._client is not None and self._client.is_connected:
            self.hass.async_create_task(self._async_write_command(self._client, CMD_QUERY_BATTERY))

    async def async_send_command(self, command: bytes) -> bool:
        """Public API for configuration entities (select/switch/button):
        sends a raw command to the scanner. Returns True on success, False
        if not connected, on failure, or on timeout."""
        if self._client is None or not self._client.is_connected:
            _LOGGER.warning("Cannot send command %s: scanner not connected", command)
            return False
        return await self._async_write_command(self._client, command)

    async def _async_write_command(self, client: BleakClient, command: bytes) -> bool:
        """Writes a configuration command to 0x2AA2 (used for battery and
        for every setting decoded from the official manual: beep/vibration,
        sleep timer, scanning mode).

        Never documented by the manufacturer - protected by a strict
        timeout to never block indefinitely.

        Serialized via _command_lock: at most one write in flight on this
        connection at a time (concurrent writes were able to permanently
        wedge the BLE connection - see const.py's note on
        BATTERY_REFRESH_DEBOUNCE_SECONDS).
        """
        async with self._command_lock:
            _LOGGER.info("Sending command %s to 0x2AA2...", command)
            try:
                await asyncio.wait_for(
                    client.write_gatt_char(CHAR_UUID_COMMAND, command, response=True),
                    timeout=COMMAND_WRITE_TIMEOUT_SECONDS,
                )
                _LOGGER.info("Command %s written successfully to 0x2AA2", command)
                return True
            except asyncio.TimeoutError:
                _LOGGER.warning(
                    "Write to 0x2AA2 (%s) timed out after %ds - connection likely "
                    "compromised, forcing a disconnect for a clean reconnect",
                    command, COMMAND_WRITE_TIMEOUT_SECONDS,
                )
                try:
                    await asyncio.wait_for(client.disconnect(), timeout=5)
                except (BleakError, asyncio.TimeoutError):
                    pass  # best-effort - the liveness tick will detect is_connected=False either way
                return False
            except BleakError as err:
                _LOGGER.warning("Failed to write to 0x2AA2 (%s): %s", command, err)
                return False

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

        # Refresh the battery level right away on connection.
        await self._async_write_command(client, CMD_QUERY_BATTERY)

        return client
