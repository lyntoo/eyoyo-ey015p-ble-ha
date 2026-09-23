"""Config flow for the Eyoyo Barcode Scanner integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigEntryState, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import BLE_LOCAL_NAME_PREFIX, DOMAIN


def _is_eyoyo_scanner(service_info: BluetoothServiceInfoBleak) -> bool:
    """Return True if the BLE advertisement matches an Eyoyo EY-015P scanner."""
    return bool(service_info.name) and service_info.name.startswith(
        BLE_LOCAL_NAME_PREFIX
    )


class EyoyoScannerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for the Eyoyo scanner."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, str] = {}  # {address: name}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle automatic Bluetooth discovery by Home Assistant."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        # The scanner temporarily advertises under a different BLE address
        # while it's in pairing mode, but its advertised name stays stable
        # (e.g. "EY-015P-116722", confirmed stable across two different
        # addresses in testing). Without this check, HA would offer a
        # phantom "Discovered" card every time an already-configured
        # scanner is put back into pairing mode.
        #
        # Only blocks the new discovery if the existing entry is currently
        # LOADED - if it's in an error/disabled state, the new discovery is
        # still offered (lets you recover a broken setup). Never affects a
        # first-time install (no existing entries -> loop is a no-op) nor a
        # second, different physical scanner (its name suffix will differ).
        for entry in self._async_current_entries(include_ignore=False):
            if entry.title == discovery_info.name and entry.state == ConfigEntryState.LOADED:
                return self.async_abort(reason="already_configured")
        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm adding the automatically discovered scanner."""
        assert self._discovery_info is not None
        if user_input is not None:
            return self.async_create_entry(
                title=self._discovery_info.name,
                data={CONF_ADDRESS: self._discovery_info.address},
            )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": self._discovery_info.name},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual setup via Settings > Add Integration."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=self._discovered_devices[address], data={CONF_ADDRESS: address}
            )

        current_addresses = self._async_current_ids(include_ignore=False)
        for discovery_info in async_discovered_service_info(self.hass, False):
            address = discovery_info.address
            if address in current_addresses or address in self._discovered_devices:
                continue
            if _is_eyoyo_scanner(discovery_info):
                self._discovered_devices[address] = discovery_info.name

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_ADDRESS): vol.In(self._discovered_devices)}
            ),
        )
