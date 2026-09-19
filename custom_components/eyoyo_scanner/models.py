"""Data models for the Eyoyo Barcode Scanner integration."""

from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry

from .coordinator import EyoyoScannerCoordinator

EyoyoConfigEntry = ConfigEntry["EyoyoData"]


@dataclass
class EyoyoState:
    """Last known state of the scanner."""

    last_code: str | None = None
    last_scanned_at: str | None = None
    connected: bool = False


@dataclass
class EyoyoData:
    """Runtime data stored on the config entry."""

    address: str
    coordinator: EyoyoScannerCoordinator
    state: EyoyoState = field(default_factory=EyoyoState)
