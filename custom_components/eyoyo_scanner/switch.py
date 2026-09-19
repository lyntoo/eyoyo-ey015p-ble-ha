"""Switch entity for the Eyoyo EY-015P scanner's vibration setting.

Write-only on the device side - optimistic state (see select.py)."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CMD_VIBRATION_OFF, CMD_VIBRATION_ON, DOMAIN
from .models import EyoyoConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EyoyoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch entity from the config entry."""
    entry_data = entry.runtime_data
    async_add_entities([EyoyoVibrationSwitch(entry_data)])


class EyoyoVibrationSwitch(SwitchEntity):
    """Turns the scanner's vibration-on-scan feature on or off."""

    _attr_has_entity_name = True
    _attr_name = "Vibration"
    _attr_icon = "mdi:vibrate"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_should_poll = False

    def __init__(self, entry_data) -> None:
        self._coordinator = entry_data.coordinator
        self._attr_is_on = True
        self._attr_unique_id = f"{entry_data.address}_vibration"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_data.address)},
            name="Eyoyo EY-015P",
            manufacturer="Eyoyo",
            model="EY-015P",
        )

    async def async_turn_on(self, **kwargs) -> None:
        if await self._coordinator.async_send_command(CMD_VIBRATION_ON):
            self._attr_is_on = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        if await self._coordinator.async_send_command(CMD_VIBRATION_OFF):
            self._attr_is_on = False
            self.async_write_ha_state()
