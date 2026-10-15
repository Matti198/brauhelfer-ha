"""Kleiner Brauhelfer – Sude anzeigen und Gärverlauf aus der RAPT Pill eintragen."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from . import brauhelfer_db as db
from .const import (
    ATTR_BEMERKUNG,
    ATTR_DICHTE,
    ATTR_ENTRY_ID,
    ATTR_RESTEXTRAKT,
    ATTR_SUD_ID,
    ATTR_TEMPERATUR,
    BEMERKUNG_MANUELL,
    DOMAIN,
    SERVICE_MESSWERT,
)
from .coordinator import BrauhelferConfigEntry, BrauhelferCoordinator
from .panel import async_register_panel, async_register_websocket, async_remove_panel

PLATFORMS = [Platform.BUTTON, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Optional(ATTR_SUD_ID): vol.Coerce(int),
        vol.Exclusive(ATTR_RESTEXTRAKT, "extrakt"): vol.Coerce(float),
        vol.Exclusive(ATTR_DICHTE, "extrakt"): vol.Coerce(float),
        vol.Optional(ATTR_TEMPERATUR): vol.Coerce(float),
        vol.Optional(ATTR_BEMERKUNG): cv.string,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Dienst registrieren."""

    async def handle_messwert(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_coordinator(hass, call.data.get(ATTR_ENTRY_ID))
        sud_id = call.data.get(ATTR_SUD_ID)
        if sud_id is None:
            if len(coordinator.aufzeichnungen) != 1:
                raise ServiceValidationError(
                    "sud_id angeben (es läuft nicht genau eine Aufzeichnung)"
                )
            sud_id = next(iter(coordinator.aufzeichnungen))
        aufz = coordinator.aufzeichnungen.get(sud_id)

        if ATTR_RESTEXTRAKT in call.data:
            restextrakt = call.data[ATTR_RESTEXTRAKT]
        elif ATTR_DICHTE in call.data:
            restextrakt = db.dichte_to_plato(call.data[ATTR_DICHTE])
        elif aufz:
            restextrakt = coordinator.read_gravity(aufz.gravity, sud_id)
        else:
            raise ServiceValidationError("restextrakt oder dichte angeben (keine Aufzeichnung für diesen Sud)")

        if ATTR_TEMPERATUR in call.data:
            temperatur = call.data[ATTR_TEMPERATUR]
        elif aufz and aufz.temperature:
            temperatur = coordinator.read_temperature(aufz.temperature, sud_id)
        else:
            raise ServiceValidationError("temperatur angeben")

        messwert = await coordinator.async_add_messwert(
            sud_id, restextrakt, temperatur, call.data.get(ATTR_BEMERKUNG, BEMERKUNG_MANUELL)
        )
        if call.return_response:
            return {
                "sud_id": sud_id,
                "zeitstempel": messwert.zeitstempel.isoformat() if messwert.zeitstempel else None,
                "restextrakt": messwert.restextrakt,
                "alkohol": round(messwert.alc, 2),
                "temperatur": messwert.temp,
            }
        return None

    async_register_websocket(hass)
    # Zeitstempel in der Zeitzone von Home Assistant (nicht der des Containers)
    db.set_clock(dt_util.now, dt_util.get_default_time_zone)

    hass.services.async_register(
        DOMAIN,
        SERVICE_MESSWERT,
        handle_messwert,
        schema=SERVICE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


def _get_coordinator(hass: HomeAssistant, entry_id: str | None) -> BrauhelferCoordinator:
    entries = [
        e for e in hass.config_entries.async_loaded_entries(DOMAIN)
        if entry_id is None or e.entry_id == entry_id
    ]
    if not entries:
        raise ServiceValidationError("Keine geladene Brauhelfer-Integration gefunden")
    if len(entries) > 1:
        raise ServiceValidationError("Mehrere Brauhelfer-Datenbanken: config_entry_id angeben")
    return entries[0].runtime_data


async def async_setup_entry(hass: HomeAssistant, entry: BrauhelferConfigEntry) -> bool:
    coordinator = BrauhelferCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # Auswahl und Schalter aus Version 0.1/0.2 entfernen (ersetzt durch Aufzeichnung je Sud)
    ent_reg = er.async_get(hass)
    for domain, key in (("select", "pill_sud"), ("switch", "auto_log")):
        if entity_id := ent_reg.async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{key}"):
            ent_reg.async_remove(entity_id)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await async_register_panel(hass)

    coordinator.async_start_logging()
    entry.async_on_unload(coordinator.async_stop_logging)
    for dienst in (coordinator.benachrichtiger, coordinator.regler, coordinator.fasskeller, coordinator.brautag):
        dienst.async_start()
        entry.async_on_unload(dienst.async_stop)
    # Speicher beim Entladen sofort schreiben
    entry.async_on_unload(coordinator.speicher.async_jetzt_speichern)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: BrauhelferConfigEntry) -> None:
    # Intervall kann sich geändert haben
    entry.runtime_data.async_start_logging()


async def async_unload_entry(hass: HomeAssistant, entry: BrauhelferConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and not [
        e for e in hass.config_entries.async_loaded_entries(DOMAIN) if e.entry_id != entry.entry_id
    ]:
        async_remove_panel(hass)
    return unloaded
