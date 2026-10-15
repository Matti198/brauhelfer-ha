"""Gemeinsame Basis für alle Entitäten."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BrauhelferCoordinator


class BrauhelferEntity(CoordinatorEntity[BrauhelferCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: BrauhelferCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Kleiner Brauhelfer",
            manufacturer="kleiner-brauhelfer",
            model=f"Datenbank v{coordinator.data.db_version}" if coordinator.data else "Datenbank",
            entry_type=DeviceEntryType.SERVICE,
        )
