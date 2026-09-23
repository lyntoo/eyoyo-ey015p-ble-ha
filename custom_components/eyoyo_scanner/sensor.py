"""Sensor entity for the Eyoyo Barcode Scanner integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .models import EyoyoConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EyoyoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor entity from the config entry."""
    entry_data = entry.runtime_data
    async_add_entities([EyoyoLastScanSensor(entry_data)])


class EyoyoLastScanSensor(SensorEntity):
    """Displays the last code scanned by the Eyoyo EY-015P."""

    _attr_has_entity_name = True
    _attr_name = "Last Scanned Code"
    _attr_icon = "mdi:barcode-scan"
    _attr_should_poll = False

    def __init__(self, entry_data) -> None:
        self._entry_data = entry_data
        self._coordinator = entry_data.coordinator
        self._attr_unique_id = f"{entry_data.address}_last_scanned_code"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_data.address)},
            connections={(CONNECTION_BLUETOOTH, entry_data.address)},
            name="Eyoyo EY-015P",
            manufacturer="Eyoyo",
            model="EY-015P",
        )

    async def async_added_to_hass(self) -> None:
        self._coordinator.async_add_listener(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.async_remove_listener(self._handle_update)

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> str | None:
        return self._coordinator.last_code

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "last_scanned_at": self._coordinator.last_scanned_at,
            "connected": self._coordinator.connected,
            "address": self._coordinator.address,
        }
