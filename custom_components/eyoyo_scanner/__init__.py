"""The Eyoyo Barcode Scanner integration."""

from __future__ import annotations

from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant

from .coordinator import EyoyoScannerCoordinator
from .models import EyoyoConfigEntry, EyoyoData

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.BUTTON,
]


async def async_setup_entry(hass: HomeAssistant, entry: EyoyoConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    address = entry.unique_id
    assert address is not None

    coordinator = EyoyoScannerCoordinator(hass, address.upper())
    entry_data = EyoyoData(address=address, coordinator=coordinator)
    entry.runtime_data = entry_data

    await coordinator.async_start()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _async_stop(_event: Event) -> None:
        await coordinator.async_stop()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: EyoyoConfigEntry) -> bool:
    """Unload a config entry."""
    entry_data: EyoyoData = entry.runtime_data
    await entry_data.coordinator.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
