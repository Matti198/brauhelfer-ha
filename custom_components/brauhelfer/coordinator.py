"""Coordinator: liest die Datenbank, führt Aufzeichnungen und schreibt Änderungen."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfTemperature
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import TemperatureConverter

from . import brauhelfer_db as db
from .speicher import Speicher
from .const import (
    BEMERKUNG_AUTO,
    CONF_BACKUPS,
    CONF_GRAVITY_ENTITY,
    CONF_INTERVAL,
    CONF_MAX_AGE,
    CONF_PATH,
    CONF_TEMPERATURE_ENTITY,
    DEFAULT_BACKUPS,
    DEFAULT_INTERVAL,
    DEFAULT_MAX_AGE,
    DOMAIN,
    PLATO_MAX,
    PLATO_MIN,
    SCAN_INTERVAL,
    CHECK_INTERVAL,
    SG_MAX,
    SG_MIN,
    TEMP_MAX,
    TEMP_MIN,
)

_LOGGER = logging.getLogger(__name__)


type BrauhelferConfigEntry = ConfigEntry[BrauhelferCoordinator]


@dataclass
class LogStatus:
    """Zustand der Eintragungen (für Sensoren und die Brauhelfer-Seite)."""

    letzter_eintrag: datetime | None = None
    letzter_sud: str | None = None
    letzter_fehler: str | None = None
    letzter_versuch: datetime | None = None


@dataclass
class Aufzeichnung:
    """Eine laufende Gärverlauf-Aufzeichnung: welche Pill gehört zu welchem Sud."""

    sud_id: int
    gravity: str
    temperature: str | None
    name: str
    start: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "sud_id": self.sud_id,
            "gravity": self.gravity,
            "temperature": self.temperature,
            "name": self.name,
            "start": self.start,
        }


class BrauhelferCoordinator(DataUpdateCoordinator[db.Snapshot]):
    """Hält einen Stand der Datenbank und schreibt Änderungen."""

    config_entry: BrauhelferConfigEntry

    def __init__(self, hass: HomeAssistant, entry: BrauhelferConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.path: str = entry.data[CONF_PATH]
        self.aufzeichnungen: dict[int, Aufzeichnung] = {}
        self.log_status = LogStatus()
        self.sud_status: dict[int, LogStatus] = {}
        self.speicher = Speicher(hass, entry.entry_id)
        self._write_lock = asyncio.Lock()
        self._unsub_timer: Callable[[], None] | None = None
        self._status_listeners: list[Callable[[], None]] = []
        self._last_warning: dict[int, str] = {}
        # Zusatzdienste (werden in __init__.async_setup_entry gestartet)
        from .benachrichtigung import Benachrichtiger  # noqa: PLC0415
        from .brautag import Brautag  # noqa: PLC0415
        from .fass import Fasskeller  # noqa: PLC0415
        from .gaerschrank import Regler  # noqa: PLC0415

        self.benachrichtiger = Benachrichtiger(self)
        self.regler = Regler(self)
        self.fasskeller = Fasskeller(self)
        self.brautag = Brautag(self)

    # ------------------------------------------------------------------ Optionen
    @property
    def interval(self) -> timedelta:
        return timedelta(minutes=self.config_entry.options.get(CONF_INTERVAL, DEFAULT_INTERVAL))

    @property
    def max_age(self) -> timedelta:
        return timedelta(minutes=self.config_entry.options.get(CONF_MAX_AGE, DEFAULT_MAX_AGE))

    @property
    def backups(self) -> int:
        return int(self.config_entry.options.get(CONF_BACKUPS, DEFAULT_BACKUPS))

    @property
    def pill_sud(self) -> db.Sud | None:
        """Erster gärender Sud mit laufender Aufzeichnung (für die Pill-Sensoren)."""
        if self.data is None:
            return None
        for sud_id in self.aufzeichnungen:
            sud = self.data.sude.get(sud_id)
            if sud and sud.status == db.STATUS_GEBRAUT:
                return sud
        return None

    # ------------------------------------------------------------------ Speicher
    async def async_load(self) -> None:
        await self.speicher.async_load()
        for item in self.speicher.data.get("aufzeichnungen", []):
            try:
                a = Aufzeichnung(**item)
            except TypeError:
                continue
            self.aufzeichnungen[a.sud_id] = a

    async def _async_save(self) -> None:
        self.speicher.data["aufzeichnungen"] = [a.as_dict() for a in self.aufzeichnungen.values()]
        await self.speicher.async_jetzt_speichern()

    # ------------------------------------------------------------------ Lesen
    async def _async_update_data(self) -> db.Snapshot:
        try:
            mtime = await self.hass.async_add_executor_job(_mtime, self.path)
        except OSError as err:
            raise UpdateFailed(f"Datenbank nicht erreichbar: {err}") from err
        if self.data is not None and self.data.mtime == mtime:
            return self.data
        try:
            snap = await self.hass.async_add_executor_job(db.read_snapshot, self.path)
        except db.BrauhelferError as err:
            raise UpdateFailed(str(err)) from err
        # Aufzeichnungen für Sude, die nicht mehr gären (z. B. im Desktop abgefüllt), beenden
        ended = [sid for sid in self.aufzeichnungen if (s := snap.sude.get(sid)) is None or s.status != db.STATUS_GEBRAUT]
        if ended:
            for sid in ended:
                self.aufzeichnungen.pop(sid, None)
            self.hass.async_create_task(self._async_save())
        return snap

    # ------------------------------------------------------------------ Timer
    @callback
    def async_start_logging(self) -> None:
        self.async_stop_logging()
        # Alle paar Minuten prüfen, ob ein Sud fällig ist. Fällig heißt: der jüngste
        # Eintrag im Gärverlauf (egal ob von HA, Brauhelfer oder Hand) ist älter als das
        # Intervall. So gibt es nach Start, Neustart oder Fehlschlag keine Doppel-Einträge
        # und keine langen Lücken.
        self._unsub_timer = async_track_time_interval(
            self.hass, self._async_timer, CHECK_INTERVAL, name="Brauhelfer Gärverlauf"
        )

    @callback
    def async_stop_logging(self) -> None:
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None

    @callback
    def async_add_status_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._status_listeners.append(listener)

        @callback
        def remove() -> None:
            self._status_listeners.remove(listener)

        return remove

    @callback
    def _notify_status(self) -> None:
        for listener in list(self._status_listeners):
            listener()

    def _faellig(self, sud_id: int) -> bool:
        sud = self.data.sude.get(sud_id) if self.data else None
        if sud is None or sud.status != db.STATUS_GEBRAUT:
            return False
        last = sud.letzter_messwert.zeitstempel if sud.letzter_messwert else None
        if last is None:
            return True
        # kleine Toleranz, damit ein 4-h-Intervall nicht erst nach 4 h 5 min greift
        return db.jetzt() - last >= self.interval - CHECK_INTERVAL / 2

    async def _async_timer(self, _now: datetime) -> None:
        for sud_id in list(self.aufzeichnungen):
            if not self._faellig(sud_id):
                continue
            try:
                await self.async_log(sud_id, automatic=True)
            except HomeAssistantError as err:
                # Nur bei neuem Grund ins Protokoll schreiben, nicht alle paar Minuten
                if self._last_warning.get(sud_id) != str(err):
                    self._last_warning[sud_id] = str(err)
                    _LOGGER.warning("Gärverlauf nicht eingetragen: %s", err)
            else:
                self._last_warning.pop(sud_id, None)

    # ------------------------------------------------------------------ Aufzeichnung
    async def async_start_recording(
        self, sud_id: int, gravity: str, temperature: str | None, name: str
    ) -> str | None:
        """Aufzeichnung starten und gleich einen ersten Wert eintragen.

        Gibt eine Warnung zurück, falls der erste Eintrag nicht klappte.
        """
        sud = self.data.sude.get(sud_id) if self.data else None
        if sud is None or sud.status != db.STATUS_GEBRAUT:
            raise HomeAssistantError("Aufzeichnung geht nur für Sude in Gärung")
        for other in self.aufzeichnungen.values():
            if other.gravity == gravity and other.sud_id != sud_id:
                anderer = self.data.sude.get(other.sud_id)
                raise HomeAssistantError(
                    f"{name} zeichnet schon für „{anderer.name if anderer else other.sud_id}“ auf"
                )
        self.aufzeichnungen[sud_id] = Aufzeichnung(
            sud_id=sud_id, gravity=gravity, temperature=temperature, name=name,
            start=dt_util.now().isoformat(),
        )
        await self._async_save()
        self.async_update_listeners()
        try:
            await self.async_log(sud_id, automatic=True)
        except HomeAssistantError as err:
            return str(err)
        return None

    async def async_stop_recording(self, sud_id: int) -> None:
        if self.aufzeichnungen.pop(sud_id, None) is not None:
            await self._async_save()
            self.async_update_listeners()

    # ------------------------------------------------------------------ Schreiben
    async def _async_write(self, fn: Callable[..., Any], *args: Any) -> Any:
        """Schreibzugriff mit Sicherung, nacheinander, danach neu einlesen."""

        def run() -> Any:
            db.backup(self.path, self.backups)
            return fn(self.path, *args)

        async with self._write_lock:
            try:
                result = await self.hass.async_add_executor_job(run)
            except (db.BrauhelferError, OSError) as err:
                raise HomeAssistantError(str(err)) from err
        await self.async_refresh()
        return result

    async def async_log(self, sud_id: int, automatic: bool = False) -> db.Messwert:
        """Aktuelle Pill-Werte der Aufzeichnung dieses Suds eintragen."""
        a = self.aufzeichnungen.get(sud_id)
        if a is None:
            raise self._fail(sud_id, "Für diesen Sud läuft keine Aufzeichnung")
        restextrakt = self.read_gravity(a.gravity, sud_id)
        temperatur = self.read_temperature(a.temperature, sud_id) if a.temperature else None
        if temperatur is None:
            sud = self.data.sude.get(sud_id) if self.data else None
            temperatur = sud.letzter_messwert.temp if sud and sud.letzter_messwert else 18.0
        return await self.async_add_messwert(
            sud_id, restextrakt, temperatur, BEMERKUNG_AUTO if automatic else f"{a.name} (manuell)"
        )

    async def async_add_messwert(
        self, sud_id: int, restextrakt: float, temperatur: float, bemerkung: str | None
    ) -> db.Messwert:
        st = self.sud_status.setdefault(sud_id, LogStatus())
        st.letzter_versuch = self.log_status.letzter_versuch = dt_util.now()
        if not PLATO_MIN <= restextrakt <= PLATO_MAX:
            raise self._fail(sud_id, f"Restextrakt {restextrakt:.2f} °P unplausibel")
        if not TEMP_MIN <= temperatur <= TEMP_MAX:
            raise self._fail(sud_id, f"Temperatur {temperatur:.1f} °C unplausibel")
        try:
            messwert = await self._async_write(db.add_messwert, sud_id, restextrakt, temperatur, bemerkung)
        except HomeAssistantError as err:
            raise self._fail(sud_id, str(err)) from err

        sud = self.data.sude.get(sud_id) if self.data else None
        now = dt_util.now()
        for s in (st, self.log_status):
            s.letzter_eintrag = now
            s.letzter_sud = sud.name if sud else str(sud_id)
            s.letzter_fehler = None
        _LOGGER.info(
            "Gärverlauf für Sud %s eingetragen: %.2f °P, %.1f °C, %.2f %%vol",
            st.letzter_sud, messwert.restextrakt, messwert.temp, messwert.alc,
        )
        self._notify_status()
        return messwert

    async def async_save_braudaten(
        self, sud_id: int, werte: dict, braudatum: datetime | None, bemerkung: str | None, gebraut: bool
    ) -> None:
        await self._async_write(db.save_braudaten, sud_id, werte, braudatum, bemerkung, gebraut)
        sitzung = self.speicher.data.get("brautag")
        if gebraut and sitzung and sitzung.get("sud_id") == sud_id:
            self.brautag.beenden()

    async def async_abfuellen(
        self, sud_id: int, restextrakt: float | None, temperatur: float | None
    ) -> None:
        if restextrakt is not None and not PLATO_MIN <= restextrakt <= PLATO_MAX:
            raise HomeAssistantError(f"Restextrakt {restextrakt:.2f} °P unplausibel")
        await self._async_write(db.abfuellen, sud_id, restextrakt, temperatur, "Letzter Wert (Gärung fertig)")
        await self.async_stop_recording(sud_id)

    async def async_verbraucht(self, sud_id: int) -> None:
        await self._async_write(db.verbraucht, sud_id)

    def _fail(self, sud_id: int | None, message: str) -> HomeAssistantError:
        now = dt_util.now()
        targets = [self.log_status]
        if sud_id is not None:
            targets.append(self.sud_status.setdefault(sud_id, LogStatus()))
        for s in targets:
            s.letzter_fehler = message
            s.letzter_versuch = now
        self._notify_status()
        return HomeAssistantError(message)

    # ------------------------------------------------------------------ aktuelle Werte
    def live_werte(self, sud_id: int) -> dict[str, Any]:
        """Aktueller Restextrakt/Temperatur: Pill (falls Aufzeichnung und frisch), sonst letzter Messwert."""
        sud = self.data.sude.get(sud_id) if self.data else None
        out: dict[str, Any] = {"sre": None, "temp": None, "frisch": False, "quelle": None, "sw": sud.sw_ist if sud else None}
        a = self.aufzeichnungen.get(sud_id)
        if a:
            try:
                out["sre"] = self.read_gravity_quiet(a.gravity)
                out["temp"] = self.read_temperature_quiet(a.temperature) if a.temperature else None
                out["frisch"] = True
                out["quelle"] = "pill"
            except HomeAssistantError:
                pass
        if out["sre"] is None and sud and sud.letzter_messwert:
            out["sre"] = sud.letzter_messwert.restextrakt
            out["temp"] = out["temp"] if out["temp"] is not None else sud.letzter_messwert.temp
            out["quelle"] = "datenbank"
        if out["sre"] is not None and sud and sud.sw_ist > 0:
            out["vg"] = db.vergaerungsgrad(sud.sw_ist, out["sre"])
        else:
            out["vg"] = None
        return out

    def _ohne_status(self, func: Callable[[], float]) -> float:
        """Wert lesen, ohne den Fehlerstatus für die Seite zu setzen."""
        alt = (self.log_status.letzter_fehler, self.log_status.letzter_versuch)
        try:
            return func()
        finally:
            self.log_status.letzter_fehler, self.log_status.letzter_versuch = alt

    def read_gravity_quiet(self, entity_id: str) -> float:
        return self._ohne_status(lambda: self.read_gravity(entity_id, None))

    def read_temperature_quiet(self, entity_id: str) -> float:
        return self._ohne_status(lambda: self.read_temperature(entity_id, None))

    def state_age(self, entity_id: str) -> timedelta | None:
        st = self.hass.states.get(entity_id)
        if st is None:
            return None
        rep = getattr(st, "last_reported", None) or st.last_updated
        return dt_util.utcnow() - rep

    # ------------------------------------------------------------------ Pill lesen
    def _fresh_state(self, entity_id: str, sud_id: int | None) -> State:
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE, ""):
            raise self._fail(sud_id, f"{entity_id} hat keinen gültigen Wert")
        reported = getattr(state, "last_reported", None) or state.last_updated
        age = dt_util.utcnow() - reported
        if age > self.max_age:
            minuten = int(age.total_seconds() // 60)
            raise self._fail(sud_id, f"Die Pill hat seit {minuten} min keinen Wert gesendet ({entity_id})")
        return state

    def read_gravity(self, entity_id: str, sud_id: int | None = None) -> float:
        """Dichte als scheinbarer Restextrakt in °P."""
        state = self._fresh_state(entity_id, sud_id)
        try:
            value = float(state.state)
        except ValueError as err:
            raise self._fail(sud_id, f"{entity_id}: '{state.state}' ist keine Zahl") from err
        unit = (state.attributes.get("unit_of_measurement") or "").lower()
        if unit.replace("°", "").strip() in ("p", "plato") or value > 1.5:
            return value
        if not SG_MIN <= value <= SG_MAX:
            raise self._fail(sud_id, f"Dichte {value} unplausibel")
        return db.dichte_to_plato(value)

    def read_temperature(self, entity_id: str, sud_id: int | None = None) -> float:
        state = self._fresh_state(entity_id, sud_id)
        try:
            value = float(state.state)
        except ValueError as err:
            raise self._fail(sud_id, f"{entity_id}: '{state.state}' ist keine Zahl") from err
        unit = state.attributes.get("unit_of_measurement")
        if unit and unit != UnitOfTemperature.CELSIUS:
            try:
                value = TemperatureConverter.convert(value, unit, UnitOfTemperature.CELSIUS)
            except Exception:  # noqa: BLE001 - unbekannte Einheit, Wert so übernehmen
                pass
        return value

    # ------------------------------------------------------------------ Pills finden
    @callback
    def async_find_pills(self) -> list[dict[str, Any]]:
        """RAPT Pills (bzw. Dichtesensoren) mit ihrem Temperatursensor finden."""
        ent_reg = er.async_get(self.hass)
        dev_reg = dr.async_get(self.hass)
        by_device: dict[str, list[er.RegistryEntry]] = {}
        for e in ent_reg.entities.values():
            if e.domain != "sensor" or e.disabled_by or not e.device_id or e.platform == DOMAIN:
                continue
            by_device.setdefault(e.device_id, []).append(e)

        pills: list[dict[str, Any]] = []
        for device_id, entities in by_device.items():
            def is_gravity(e: er.RegistryEntry) -> bool:
                text = f"{e.entity_id} {e.original_name or ''} {e.translation_key or ''}".lower()
                return "gravity" in text or "dichte" in text

            gravity = next((e for e in entities if is_gravity(e)), None)
            if gravity is None:
                continue
            temp = next(
                (
                    e for e in entities
                    if (e.device_class or e.original_device_class) == "temperature"
                    or "temperature" in e.entity_id
                ),
                None,
            )
            device = dev_reg.async_get(device_id)
            name = (device.name_by_user or device.name) if device else gravity.entity_id
            pills.append({"name": name, "gravity": gravity.entity_id, "temperature": temp.entity_id if temp else None})

        # Früher in den Optionen hinterlegte Entitäten weiter anbieten
        opt_g = self.config_entry.options.get(CONF_GRAVITY_ENTITY)
        if opt_g and not any(p["gravity"] == opt_g for p in pills):
            pills.append({
                "name": opt_g,
                "gravity": opt_g,
                "temperature": self.config_entry.options.get(CONF_TEMPERATURE_ENTITY),
            })
        for p in pills:
            belegt = next((a.sud_id for a in self.aufzeichnungen.values() if a.gravity == p["gravity"]), None)
            p["belegt_von"] = belegt
            # last_reported ändert sich auch, wenn die Pill denselben Wert erneut sendet
            # (last_updated nicht) – wichtig gegen Ende der Gärung, wenn die Dichte stillsteht
            st = self.hass.states.get(p["gravity"])
            rep = getattr(st, "last_reported", None) or (st.last_updated if st else None)
            p["zuletzt"] = rep.isoformat() if rep else None
        return sorted(pills, key=lambda p: p["name"].lower())


def _mtime(path: str) -> float:
    return Path(path).stat().st_mtime
