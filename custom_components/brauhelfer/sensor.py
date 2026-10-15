"""Sensoren: ein Sensor je Sud, eine Übersicht und Werte des Pill-Suds."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import brauhelfer_db as db
from .const import DOMAIN
from .coordinator import BrauhelferConfigEntry, BrauhelferCoordinator
from .entity import BrauhelferEntity


def _local(dt: datetime | None) -> datetime | None:
    """Naive Ortszeit aus der Datenbank -> zeitzonenbehaftet für HA."""
    if dt is None:
        return None
    return dt.replace(tzinfo=dt_util.get_default_time_zone())


def _sud_dict(sud: db.Sud) -> dict[str, Any]:
    data: dict[str, Any] = {
        "sud_id": sud.id,
        "name": sud.name,
        "sudnummer": sud.nummer,
        "status": sud.status_text,
        "kategorie": sud.kategorie,
        "menge_l": sud.menge,
        "stammwuerze_rezept": sud.sw_rezept,
        "ibu": sud.ibu,
        "co2": sud.co2,
    }
    if sud.status == db.STATUS_GEBRAUT:
        data["braudatum"] = sud.braudatum.isoformat() if sud.braudatum else None
        data["tage_seit_brautag"] = sud.tage_seit_brautag
        data["stammwuerze"] = round(sud.sw_ist, 2)
        data["anzahl_messwerte"] = sud.anzahl_messwerte
        mw = sud.letzter_messwert
        if mw:
            data["restextrakt"] = mw.restextrakt
            data["alkohol"] = round(mw.alc, 2)
            data["temperatur"] = mw.temp
            data["vergaerungsgrad"] = round(db.vergaerungsgrad(sud.sw_ist, mw.restextrakt), 1)
            data["letzter_messwert"] = mw.zeitstempel.isoformat() if mw.zeitstempel else None
    return data


# --------------------------------------------------------------------------
# Setup
# --------------------------------------------------------------------------

async def async_setup_entry(
    hass: HomeAssistant,
    entry: BrauhelferConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            UebersichtSensor(coordinator),
            *(PillSudSensor(coordinator, d) for d in PILL_SENSORS),
            LetzterEintragSensor(coordinator),
        ]
    )

    known: set[int] = set()
    registry = er.async_get(hass)

    @callback
    def _sync_sud_entities() -> None:
        if coordinator.data is None:
            return
        current = {s.id for s in coordinator.data.aktuell}
        new = current - known
        if new:
            known.update(new)
            async_add_entities(SudSensor(coordinator, sud_id) for sud_id in sorted(new))
        # Sude, die nicht mehr geplant/gärend sind, entfernen
        for sud_id in known - current:
            known.discard(sud_id)
            unique_id = f"{entry.entry_id}_sud_{sud_id}"
            if entity_id := registry.async_get_entity_id("sensor", DOMAIN, unique_id):
                registry.async_remove(entity_id)

    # Verwaiste Sud-Sensoren aus früheren Läufen aufräumen
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if "_sud_" in reg_entry.unique_id:
            try:
                sud_id = int(reg_entry.unique_id.rsplit("_", 1)[1])
            except ValueError:
                continue
            if coordinator.data is None or sud_id not in {s.id for s in coordinator.data.aktuell}:
                registry.async_remove(reg_entry.entity_id)

    _sync_sud_entities()
    entry.async_on_unload(coordinator.async_add_listener(_sync_sud_entities))

    # Fässer und Gärschränke aus dem HA-Speicher
    known_extra: set[str] = set()

    @callback
    def _sync_extra() -> None:
        aktuell: dict[str, SensorEntity] = {}
        for f in coordinator.speicher.data["faesser"]:
            aktuell[f"fass_{f['id']}"] = FassSensor(coordinator, f["id"])
        for sch in coordinator.speicher.data["schraenke"]:
            aktuell[f"schrank_{sch['id']}"] = SchrankSensor(coordinator, sch["id"])
        neu = [e for k, e in aktuell.items() if k not in known_extra]
        if neu:
            known_extra.update(k for k in aktuell if k not in known_extra)
            async_add_entities(neu)
        for key in list(known_extra - set(aktuell)):
            known_extra.discard(key)
            domain_key = f"{entry.entry_id}_{key}"
            if entity_id := registry.async_get_entity_id("sensor", DOMAIN, domain_key):
                registry.async_remove(entity_id)

    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        uid = reg_entry.unique_id
        for prefix, liste in (("_fass_", "faesser"), ("_schrank_", "schraenke")):
            if prefix in uid:
                eid = uid.split(prefix, 1)[1]
                if not any(x["id"] == eid for x in coordinator.speicher.data[liste]):
                    registry.async_remove(reg_entry.entity_id)

    _sync_extra()
    entry.async_on_unload(coordinator.async_add_listener(_sync_extra))


# --------------------------------------------------------------------------
# Sensor je Sud
# --------------------------------------------------------------------------

class SudSensor(BrauhelferEntity, SensorEntity):
    """Status eines geplanten (Merkliste) oder gärenden Suds."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["Geplant", "In Gärung"]

    def __init__(self, coordinator: BrauhelferCoordinator, sud_id: int) -> None:
        super().__init__(coordinator, f"sud_{sud_id}")
        self.sud_id = sud_id

    @property
    def _sud(self) -> db.Sud | None:
        if self.coordinator.data is None:
            return None
        sud = self.coordinator.data.sude.get(self.sud_id)
        return sud if sud and sud.status in (db.STATUS_REZEPT, db.STATUS_GEBRAUT) else None

    @property
    def available(self) -> bool:
        return super().available and self._sud is not None

    @property
    def name(self) -> str:
        sud = self._sud
        return f"Sud {sud.name}" if sud else f"Sud {self.sud_id}"

    @property
    def icon(self) -> str:
        sud = self._sud
        return "mdi:glass-mug-variant" if sud and sud.status == db.STATUS_GEBRAUT else "mdi:clipboard-text-outline"

    @property
    def native_value(self) -> str | None:
        sud = self._sud
        return sud.status_text if sud else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        sud = self._sud
        if sud is None:
            return {}
        data = _sud_dict(sud)
        a = self.coordinator.aufzeichnungen.get(sud.id)
        data["aufzeichnung"] = a.name if a else None
        return data


# --------------------------------------------------------------------------
# Übersicht für Dashboard-Karten
# --------------------------------------------------------------------------

class UebersichtSensor(BrauhelferEntity, SensorEntity):
    """Anzahl aktueller Sude; Listen als Attribute (für Markdown-Karten)."""

    _attr_translation_key = "uebersicht"
    _attr_icon = "mdi:barley"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: BrauhelferCoordinator) -> None:
        super().__init__(coordinator, "uebersicht")

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return len(self.coordinator.data.aktuell)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        snap = self.coordinator.data
        if snap is None:
            return {}
        return {
            "gaerend": [_sud_dict(s) for s in snap.gaerend],
            "geplant": [_sud_dict(s) for s in snap.geplant],
            "abgefuellt": [{"sud_id": s.id, "name": s.name, "abfuelldatum": s.abfuelldatum.isoformat() if s.abfuelldatum else None} for s in snap.abgefuellt],
            "datenbank": self.coordinator.path,
            "db_version": snap.db_version,
            "datei_geaendert": dt_util.utc_from_timestamp(snap.mtime).isoformat(),
        }


# --------------------------------------------------------------------------
# Werte des Suds, dem die Pill zugeordnet ist (aus der Datenbank)
# --------------------------------------------------------------------------

@dataclass(frozen=True, kw_only=True)
class PillSensorDescription(SensorEntityDescription):
    value_fn: Callable[[db.Sud], Any]


def _mw(attr: str) -> Callable[[db.Sud], Any]:
    def fn(sud: db.Sud) -> Any:
        return getattr(sud.letzter_messwert, attr) if sud.letzter_messwert else None

    return fn


PILL_SENSORS: tuple[PillSensorDescription, ...] = (
    PillSensorDescription(
        key="restextrakt",
        translation_key="restextrakt",
        native_unit_of_measurement="°P",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:water-opacity",
        value_fn=_mw("restextrakt"),
    ),
    PillSensorDescription(
        key="alkohol",
        translation_key="alkohol",
        native_unit_of_measurement="% vol",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:percent-outline",
        value_fn=_mw("alc"),
    ),
    PillSensorDescription(
        key="temperatur",
        translation_key="temperatur",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_mw("temp"),
    ),
    PillSensorDescription(
        key="vergaerungsgrad",
        translation_key="vergaerungsgrad",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:chart-bell-curve-cumulative",
        value_fn=lambda s: db.vergaerungsgrad(s.sw_ist, s.letzter_messwert.restextrakt) if s.letzter_messwert else None,
    ),
    PillSensorDescription(
        key="stammwuerze",
        translation_key="stammwuerze",
        native_unit_of_measurement="°P",
        suggested_display_precision=1,
        icon="mdi:water",
        value_fn=lambda s: s.sw_ist,
    ),
    PillSensorDescription(
        key="gaertage",
        translation_key="gaertage",
        native_unit_of_measurement="d",
        icon="mdi:calendar-clock",
        value_fn=lambda s: s.tage_seit_brautag,
    ),
)


class PillSudSensor(BrauhelferEntity, SensorEntity):
    entity_description: PillSensorDescription

    def __init__(self, coordinator: BrauhelferCoordinator, description: PillSensorDescription) -> None:
        super().__init__(coordinator, f"pill_{description.key}")
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        sud = self.coordinator.pill_sud
        return self.entity_description.value_fn(sud) if sud else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        sud = self.coordinator.pill_sud
        return {"sud": sud.name, "sud_id": sud.id} if sud else {}


class LetzterEintragSensor(BrauhelferEntity, SensorEntity):
    """Zeitpunkt des letzten Eintrags durch HA, mit Fehlermeldung als Attribut."""

    _attr_translation_key = "letzter_eintrag"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:database-clock"

    def __init__(self, coordinator: BrauhelferCoordinator) -> None:
        super().__init__(coordinator, "letzter_eintrag")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_status_listener(self.async_write_ha_state))

    @property
    def native_value(self) -> datetime | None:
        sud = self.coordinator.pill_sud
        if self.coordinator.log_status.letzter_eintrag:
            return self.coordinator.log_status.letzter_eintrag
        # Nach Neustart: letzter Messwert aus der Datenbank
        if sud and sud.letzter_messwert:
            return _local(sud.letzter_messwert.zeitstempel)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        st = self.coordinator.log_status
        return {
            "sud": st.letzter_sud,
            "fehler": st.letzter_fehler,
            "letzter_versuch": st.letzter_versuch.isoformat() if st.letzter_versuch else None,
            "aufzeichnungen": [a.name for a in self.coordinator.aufzeichnungen.values()],
            "intervall_min": int(self.coordinator.interval.total_seconds() // 60),
        }


# --------------------------------------------------------------------------
# Fässer und Gärschränke
# --------------------------------------------------------------------------

class FassSensor(BrauhelferEntity, SensorEntity):
    """Restmenge eines Fasses in Litern."""

    _attr_native_unit_of_measurement = "L"
    _attr_device_class = SensorDeviceClass.VOLUME_STORAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:keg"

    def __init__(self, coordinator: BrauhelferCoordinator, fass_id: str) -> None:
        super().__init__(coordinator, f"fass_{fass_id}")
        self.fass_id = fass_id

    @property
    def _fass(self) -> dict[str, Any] | None:
        return self.coordinator.speicher.fass(self.fass_id)

    @property
    def available(self) -> bool:
        return self._fass is not None

    @property
    def name(self) -> str:
        f = self._fass
        return f"Fass {f['name']}" if f else "Fass"

    @property
    def native_value(self) -> float | None:
        f = self._fass
        return round(f["rest_l"], 2) if f else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        f = self._fass
        if not f:
            return {}
        sud = self.coordinator.data.sude.get(f["sud_id"]) if self.coordinator.data else None
        tags = [t for t in self.coordinator.speicher.data["tags"] if t["fass_id"] == self.fass_id]
        return {
            "sud": sud.name if sud else None,
            "sud_id": f["sud_id"],
            "inhalt_l": f["inhalt_l"],
            "leer": f.get("leer", False),
            "tara_kg": f["tara_kg"],
            "glaeser_0_5": int(f["rest_l"] / 0.5),
            "tags": [{"name": t["name"], "glas_l": t["glas_l"]} for t in tags],
            "letzte_wiegung": (f.get("letzte_wiegung") or {}).get("zeit"),
        }


class SchrankSensor(BrauhelferEntity, SensorEntity):
    """Zustand der Gärschrank-Regelung."""

    _attr_icon = "mdi:fridge-industrial-outline"

    def __init__(self, coordinator: BrauhelferCoordinator, schrank_id: str) -> None:
        super().__init__(coordinator, f"schrank_{schrank_id}")
        self.schrank_id = schrank_id

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.regler.async_add_listener(self.async_write_ha_state))

    @property
    def _schrank(self) -> dict[str, Any] | None:
        return self.coordinator.speicher.schrank(self.schrank_id)

    @property
    def available(self) -> bool:
        return self._schrank is not None

    @property
    def name(self) -> str:
        sch = self._schrank
        return f"Gärschrank {sch['name']}" if sch else "Gärschrank"

    @property
    def native_value(self) -> str | None:
        st = self.coordinator.regler.status().get(self.schrank_id)
        return st["modus_text"] if st else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        st = self.coordinator.regler.status().get(self.schrank_id) or {}
        sud = self.coordinator.data.sude.get(st.get("sud_id")) if self.coordinator.data and st.get("sud_id") else None
        return {"soll": st.get("soll"), "ist": st.get("ist"), "sud": sud.name if sud else None, "modus": st.get("modus")}
