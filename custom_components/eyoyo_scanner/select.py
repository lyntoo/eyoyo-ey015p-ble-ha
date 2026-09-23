"""Select entities for the Eyoyo EY-015P scanner's configurable settings.

Write-only on the device side (no known state-readback characteristic) -
the displayed option is therefore "optimistic": the last value this
integration successfully sent, not necessarily the real state if the
scanner was reconfigured another way (e.g. a paper QR code scanned
manually).
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import AUTO_POWER_OFF_OPTIONS, BEEP_VOLUME_OPTIONS, DOMAIN, SCANNING_MODE_OPTIONS
from .models import EyoyoConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EyoyoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the select entities from the config entry."""
    entry_data = entry.runtime_data
    async_add_entities(
        [
            EyoyoCommandSelect(
                entry_data, "Beep Volume", "mdi:volume-high", BEEP_VOLUME_OPTIONS, "Medium"
            ),
            EyoyoCommandSelect(
                entry_data, "Auto Power Off", "mdi:timer-sand", AUTO_POWER_OFF_OPTIONS, "30 minutes"
            ),
            EyoyoCommandSelect(
                entry_data, "Scanning Mode", "mdi:barcode-scan", SCANNING_MODE_OPTIONS, "Manual Trigger"
            ),
        ]
    )


class EyoyoCommandSelect(SelectEntity):
    """Generic select: writes the matching BLE command on change."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_should_poll = False

    def __init__(self, entry_data, name: str, icon: str, options_map: dict, default_option: str) -> None:
        self._coordinator = entry_data.coordinator
        self._options_map = options_map
        self._attr_name = name
        self._attr_icon = icon
        self._attr_options = list(options_map.keys())
        self._attr_current_option = default_option
        self._attr_unique_id = f"{entry_data.address}_{name.lower().replace(' ', '_')}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_data.address)},
            connections={(CONNECTION_BLUETOOTH, entry_data.address)},
            name="Eyoyo EY-015P",
            manufacturer="Eyoyo",
            model="EY-015P",
        )

    async def async_select_option(self, option: str) -> None:
        command = self._options_map[option]
        if await self._coordinator.async_send_command(command):
            self._attr_current_option = option
            self.async_write_ha_state()
