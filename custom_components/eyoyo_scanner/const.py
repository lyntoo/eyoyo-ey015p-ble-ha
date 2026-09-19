"""Constants for the Eyoyo Barcode Scanner integration."""

from __future__ import annotations

DOMAIN = "eyoyo_scanner"

BLE_LOCAL_NAME_PREFIX = "EY-015P"

# Service 0xFEEA (registered to "Swirl Networks, Inc." with the Bluetooth SIG,
# but reused by the scanner's manufacturer for its own proprietary data channel)
SERVICE_UUID_DATA = "0000feea-0000-1000-8000-00805f9b34fb"

# Characteristic 0x2AA1 (officially "Magnetic Flux Density - 3D" per the
# standard SIG name, but in practice the channel that carries the scanned
# barcode as raw ASCII text, terminated by a carriage return 0x0D).
# Confirmed via Bluetooth HCI snoop capture: the scanner pushes a genuine
# GATT notification (ATT opcode 0x1b, standard NOTIFY bit) on every scan,
# fully asynchronously - the attribute never reflects the data on a direct
# read (read_gatt_char), only the pushed notification carries it.
CHAR_UUID_SCAN_DATA = "00002aa1-0000-1000-8000-00805f9b34fb"

# Characteristic 0xFEC9 (read-only, never observed to change during testing -
# likely firmware/serial info, kept for future reference)
CHAR_UUID_UNKNOWN_FEC9 = "0000fec9-0000-1000-8000-00805f9b34fb"

# End-of-scan terminator in the notification stream (carriage return). A
# scanned value can arrive fragmented across several distinct notification
# packets when it exceeds the ATT_MTU-3 payload (20 bytes by default) -
# confirmed via HCI capture: a 29-character QR code arrived as 2 successive
# notifications (20 + 9 bytes).
SCAN_VALUE_TERMINATOR = b"\r"

EVENT_BARCODE_SCANNED = "eyoyo_barcode_scanned"

SOURCE_BLE_DIRECT = "ble_direct"
