"""Button entities for one-shot actions on the Eyoyo EY-015P scanner."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CMD_QUERY_BATTERY, CMD_SLEEP_NOW, DOMAIN
from .models import EyoyoConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EyoyoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the button entities from the config entry."""
    entry_data = entry.runtime_data
    async_add_entities(
        [
            EyoyoCommandButton(entry_data, "Sleep Now", "mdi:sleep", CMD_SLEEP_NOW),
            EyoyoCommandButton(entry_data, "Battery Status", "mdi:battery-sync", CMD_QUERY_BATTERY),
        ]
    )


class EyoyoCommandButton(ButtonEntity):
    """Generic button: writes a fixed BLE command when pressed."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry_data, name: str, icon: str, command: bytes) -> None:
        self._coordinator = entry_data.coordinator
        self._command = command
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"{entry_data.address}_{name.lower().replace(' ', '_')}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_data.address)},
            connections={(CONNECTION_BLUETOOTH, entry_data.address)},
            name="Eyoyo EY-015P",
            manufacturer="Eyoyo",
            model="EY-015P",
        )

    async def async_press(self) -> None:
        await self._coordinator.async_send_command(self._command)
