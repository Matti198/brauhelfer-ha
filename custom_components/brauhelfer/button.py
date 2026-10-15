"""Button: aktuelle Pill-Werte sofort eintragen."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import BrauhelferConfigEntry, BrauhelferCoordinator
from .entity import BrauhelferEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BrauhelferConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([LogNowButton(entry.runtime_data)])


class LogNowButton(BrauhelferEntity, ButtonEntity):
    _attr_translation_key = "log_now"
    _attr_icon = "mdi:database-plus"

    def __init__(self, coordinator: BrauhelferCoordinator) -> None:
        super().__init__(coordinator, "log_now")

    async def async_press(self) -> None:
        """Für alle laufenden Aufzeichnungen sofort einen Messwert eintragen."""
        if not self.coordinator.aufzeichnungen:
            raise HomeAssistantError("Es läuft keine Aufzeichnung. Starte sie auf der Brauhelfer-Seite.")
        fehler = []
        for sud_id in list(self.coordinator.aufzeichnungen):
            try:
                await self.coordinator.async_log(sud_id)
            except HomeAssistantError as err:
                fehler.append(str(err))
        if fehler:
            raise HomeAssistantError("; ".join(fehler))
