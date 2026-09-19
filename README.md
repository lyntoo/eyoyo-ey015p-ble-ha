# Eyoyo EY-015P Barcode Scanner (BLE) for Home Assistant

A custom Home Assistant integration for the **Eyoyo EY-015P** Bluetooth barcode scanner, connected directly over **Bluetooth LE** — no phone, no companion app, no cloud.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=lyntoo&repository=eyoyo-ey015p-ble-ha&category=integration)

---

## Why

The EY-015P supports three Bluetooth modes: classic HID (keyboard emulation), BLE, and SPP. The common way to use it with Home Assistant is through a phone running a companion app that forwards scans via webhook — which means the scanner is only usable while a phone is present and awake. This integration talks to the scanner directly over BLE from Home Assistant itself (or through any ESPHome Bluetooth proxy in range), so scans work anywhere in range of your Bluetooth mesh, with zero phone dependency.

The BLE data channel is undocumented by the manufacturer and was reverse-engineered by capturing and analyzing the raw Bluetooth HCI traffic between the scanner and a phone during a real scan.

---

## Features

- **Fully local** — BLE only, no companion app, no account, no internet dependency
- **Works through ESPHome Bluetooth proxies** — not limited to the range of a single adapter
- **Automatic discovery** — the scanner shows up for one-tap setup when advertising; manual selection also supported
- **Real-time via GATT notifications** — no polling loop; scans are pushed instantly by the scanner
- **Entity:** `sensor` — last scanned code, with `last_scanned_at`, `connected`, and `address` attributes
- **Event:** `eyoyo_barcode_scanned` fired on every scan (`code`, `source`, `address`) — trigger automations directly (e.g. building a grocery list) without touching the sensor

---

## Requirements

- Home Assistant Core with the built-in `bluetooth` integration enabled
- A Bluetooth adapter (or ESPHome Bluetooth proxy) within range of the scanner
- Python packages `bleak>=0.21.1` and `bleak-retry-connector>=3.0.0` (installed automatically by Home Assistant)

---

## Installation

### Via HACS (custom repository)

1. Click the badge above, or go to **HACS → Integrations → ⋮ → Custom repositories**
2. Add `https://github.com/lyntoo/eyoyo-ey015p-ble-ha` as an **Integration**
3. Search for **Eyoyo EY-015P Barcode Scanner (BLE)** and install
4. Restart Home Assistant

### Manual

1. Copy the `custom_components/eyoyo_scanner` folder into your HA `config/custom_components/` directory
2. Restart Home Assistant

---

## Setup

1. Put the scanner in BLE pairing mode (scan the "Bluetooth BLE" mode barcode in the scanner's user manual)
2. Home Assistant should auto-discover it — go to **Settings → Devices & services** and confirm the discovered device
3. If it isn't auto-discovered, go to **Settings → Devices & services → Add Integration**, search for **Eyoyo EY-015P Barcode Scanner (BLE)**, and select the device manually
4. The integration pairs/bonds with the scanner automatically on first connection — no PIN entry needed

---

## Uninstalling

**Settings → Devices & services → Eyoyo EY-015P → ⋮ → Delete**, then remove the `custom_components/eyoyo_scanner` folder (or remove it via HACS). No credentials or accounts were ever stored — the config entry only holds the device's Bluetooth address.

---

## Using scans in automations

Listen for the `eyoyo_barcode_scanned` event directly, which fires immediately on every scan regardless of the sensor's polling state:

```yaml
automation:
  - alias: "Add scanned barcode to grocery list"
    trigger:
      - platform: event
        event_type: eyoyo_barcode_scanned
    action:
      - service: todo.add_item
        target:
          entity_id: todo.grocery_list
        data:
          item: "{{ trigger.event.data.code }}"
```

---

## Protocol notes

The scanner exposes a non-standard service `0xFEEA` containing characteristic `0x2AA1` (mislabeled "Magnetic Flux Density - 3D" by generic BLE UUID databases — a standard SIG 16-bit UUID repurposed by the manufacturer). Captured via Bluetooth HCI snoop during a real scan: after the client bonds and enables the CCCD, the scanner pushes a genuine GATT **notification** (ATT opcode `0x1b`) containing the scanned value as raw ASCII text terminated by a carriage return (`0x0D`) — asynchronously, with no correlation to any read request. The characteristic's readable value is never updated; only the pushed notification carries the data. Values longer than the negotiated ATT_MTU (20-byte payload by default) arrive fragmented across multiple consecutive notification packets, which the integration buffers and reassembles up to the terminator.

---

## Disclaimer

This project is not affiliated with or endorsed by Eyoyo. It was built by reverse-engineering the scanner's Bluetooth LE protocol via packet capture, for personal, local use. Use at your own risk.
