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

# The standard Battery Service (0x180F/0x2A19) IS present on the device but
# turned out to be a firmware stub that always returns 100% (read
# independently by nRF Connect AND by this integration, never updated) -
# unusable, abandoned.
#
# The real battery level is obtained by scanning the "Battery Remaining"
# configuration QR code (official manual, section 7 "Battery & Charging"):
# the scanner then emits the percentage as ASCII text over the SAME channel
# as a normal scan (0x2AA1) - confirmed empirically. This reply is
# distinguished from a real scanned code by a strict pattern.
BATTERY_REPLY_PATTERN = r"^\d{1,3}%$"

# End-of-scan terminator in the notification stream (carriage return). A
# scanned value can arrive fragmented across several distinct notification
# packets when it exceeds the ATT_MTU-3 payload (20 bytes by default) -
# confirmed via HCI capture: a 29-character QR code arrived as 2 successive
# notifications (20 + 9 bytes).
SCAN_VALUE_TERMINATOR = b"\r"

EVENT_BARCODE_SCANNED = "eyoyo_barcode_scanned"

SOURCE_BLE_DIRECT = "ble_direct"

# Characteristic 0x2AA2 ("Language" per the manual), write-only. All
# configuration QR codes in the manual encode a text command, either in the
# "^&NNN&^" format (battery/beep/vibration/sleep) or "S_CMD_xxxx" (scanning
# mode) - decoded by reading the QR codes (pyzbar) from the official PDF
# manual. Writing these commands directly here (instead of physically
# scanning the paper QR code) works reliably and fast (<400ms, reproducible)
# - never documented by the manufacturer, protected by a timeout.
CHAR_UUID_COMMAND = "00002aa2-0000-1000-8000-00805f9b34fb"
COMMAND_WRITE_TIMEOUT_SECONDS = 8

# --- Battery (manual section 7) ---
CMD_QUERY_BATTERY = b"^&037&^"

# --- Beep & Vibration Setting (manual section 14) ---
CMD_BEEP_VOLUME_OFF = b"^&03A&^"
CMD_BEEP_VOLUME_LOW = b"^&03D&^"
CMD_BEEP_VOLUME_MEDIUM = b"^&03C&^"
CMD_BEEP_VOLUME_HIGH = b"^&03B&^"
CMD_VIBRATION_ON = b"^&039&^"
CMD_VIBRATION_OFF = b"^&038&^"

BEEP_VOLUME_OPTIONS = {
    "Off": CMD_BEEP_VOLUME_OFF,
    "Low": CMD_BEEP_VOLUME_LOW,
    "Medium": CMD_BEEP_VOLUME_MEDIUM,
    "High": CMD_BEEP_VOLUME_HIGH,
}

# --- Sleep Time Setting (manual section 15) ---
CMD_SLEEP_30S = b"^&043&^"
CMD_SLEEP_2MIN = b"^&045&^"
CMD_SLEEP_5MIN = b"^&046&^"
CMD_SLEEP_10MIN = b"^&047&^"
CMD_SLEEP_30MIN = b"^&048&^"
CMD_SLEEP_NEVER = b"^&040&^"
CMD_SLEEP_NOW = b"^&041&^"

AUTO_POWER_OFF_OPTIONS = {
    "30 seconds": CMD_SLEEP_30S,
    "2 minutes": CMD_SLEEP_2MIN,
    "5 minutes": CMD_SLEEP_5MIN,
    "10 minutes": CMD_SLEEP_10MIN,
    "30 minutes": CMD_SLEEP_30MIN,
    "Never": CMD_SLEEP_NEVER,
}

# --- Scanning Mode Setting (manual section 18) - different format (S_CMD_) ---
CMD_SCAN_MODE_MANUAL = b"S_CMD_MT00"
CMD_SCAN_MODE_CONTINUOUS = b"S_CMD_020E"
CMD_SCAN_MODE_AUTO_SENSING = b"S_CMD_020F"

SCANNING_MODE_OPTIONS = {
    "Manual Trigger": CMD_SCAN_MODE_MANUAL,
    "Continuous": CMD_SCAN_MODE_CONTINUOUS,
    "Auto-Sensing": CMD_SCAN_MODE_AUTO_SENSING,
}

# NOTE: "Restore Defaults" (^&002&^) is intentionally NOT exposed as an
# automatable command - it could reset a BLE-related setting the
# integration itself depends on. It remains a paper QR code to scan
# manually as a last resort (see images/restore_defaults_qr.png in this
# repository), never triggered from the integration.
