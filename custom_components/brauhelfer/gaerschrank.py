"""Gärschrank-Regelung: Kühlen und Heizen über schaltbare Steckdosen.

Pro Gärschrank: Temperatursensor, Kühlung, Heizung, Hysterese und Mindestpause
für den Kompressor. Pro Sud: zugeordneter Gärschrank und ein Profil
„ab X % Vergärungsgrad → Y °C“ (z. B. 0 % → 12 °C, 70 % → 16 °C Diacetylrast).

Sicherheit: Fällt der Sensor aus, wird beides ausgeschaltet. Kühlung und
Heizung sind nie gleichzeitig an.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import TemperatureConverter

from . import brauhelfer_db as db

if TYPE_CHECKING:
    from .coordinator import BrauhelferCoordinator

_LOGGER = logging.getLogger(__name__)

REGEL_INTERVALL = timedelta(seconds=30)
SENSOR_MAX_ALTER = timedelta(minutes=30)

MODUS_TEXT = {
    "kuehlen": "Kühlt",
    "heizen": "Heizt",
    "aus": "Im Sollbereich",
    "pause": "Kompressorpause",
    "fehler": "Sensor fehlt",
    "frei": "Keine Regelung",
}


class Regler:
    def __init__(self, coord: BrauhelferCoordinator) -> None:
        self.coord = coord
        self.hass: HomeAssistant = coord.hass
        self._unsub = None
        # Laufzeitzustand je Schrank
        self.zustand: dict[str, dict[str, Any]] = {}
        self._listeners: list = []

    @property
    def speicher(self):
        return self.coord.speicher

    @callback
    def async_start(self) -> None:
        self._unsub = async_track_time_interval(self.hass, self._async_tick, REGEL_INTERVALL, name="Brauhelfer Gärschrank")

    @callback
    def async_stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @callback
    def async_add_listener(self, listener) -> Any:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    # ------------------------------------------------------------------ Abfragen
    def sud_fuer_schrank(self, schrank_id: str) -> int | None:
        for sud_id, r in self.speicher.data["regelung"].items():
            if r.get("schrank_id") == schrank_id and r.get("aktiv", True):
                sud = self.coord.data.sude.get(int(sud_id)) if self.coord.data else None
                if sud and sud.status == db.STATUS_GEBRAUT:
                    return int(sud_id)
        return None

    def soll_fuer_sud(self, sud_id: int) -> float | None:
        r = self.speicher.regelung(sud_id)
        if not r or not r.get("aktiv", True) or not r.get("profil"):
            return None
        stufe = self.aktuelle_stufe(sud_id)
        return stufe["soll"] if stufe else None

    def aktuelle_stufe(self, sud_id: int) -> dict[str, Any] | None:
        r = self.speicher.regelung(sud_id)
        if not r or not r.get("profil"):
            return None
        vg = self.coord.live_werte(sud_id).get("vg") or 0.0
        stufen = sorted(r["profil"], key=lambda s: s["ab_vg"])
        aktiv = stufen[0]
        for s in stufen:
            if vg >= s["ab_vg"]:
                aktiv = s
        return aktiv

    def ist_fuer_sud(self, sud_id: int) -> float | None:
        r = self.speicher.regelung(sud_id)
        if not r:
            return None
        schrank = self.speicher.schrank(r.get("schrank_id"))
        return self._ist(schrank, sud_id) if schrank else None

    def _ist(self, schrank: dict[str, Any], sud_id: int | None) -> float | None:
        ent = schrank.get("temp_sensor")
        if ent:
            st = self.hass.states.get(ent)
            if st is None or st.state in (STATE_UNKNOWN, STATE_UNAVAILABLE, ""):
                return None
            alter = self.coord.state_age(ent)
            if alter is not None and alter > SENSOR_MAX_ALTER and not schrank.get("sensor_ohne_altersgrenze"):
                return None
            try:
                wert = float(st.state)
            except ValueError:
                return None
            einheit = st.attributes.get("unit_of_measurement")
            if einheit and einheit != UnitOfTemperature.CELSIUS:
                try:
                    wert = TemperatureConverter.convert(wert, einheit, UnitOfTemperature.CELSIUS)
                except Exception:  # noqa: BLE001
                    pass
            return wert
        # ohne eigenen Sensor: Temperatur der Pill im Sud
        if sud_id is not None:
            a = self.coord.aufzeichnungen.get(sud_id)
            if a and a.temperature:
                try:
                    return self.coord.read_temperature_quiet(a.temperature)
                except Exception:  # noqa: BLE001
                    return None
        return None

    def status(self) -> dict[str, Any]:
        out = {}
        for schrank in self.speicher.data["schraenke"]:
            z = self.zustand.get(schrank["id"], {})
            out[schrank["id"]] = {
                "modus": z.get("modus", "frei"),
                "modus_text": MODUS_TEXT.get(z.get("modus", "frei"), ""),
                "ist": z.get("ist"),
                "soll": z.get("soll"),
                "sud_id": z.get("sud_id"),
                "stufe": z.get("stufe"),
            }
        return out

    # ------------------------------------------------------------------ Regeln
    async def _async_tick(self, _now: datetime | None = None) -> None:
        for schrank in list(self.speicher.data["schraenke"]):
            try:
                await self._regeln(schrank)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Fehler in der Regelung von %s", schrank.get("name"))
        for listener in list(self._listeners):
            listener()

    async def async_jetzt(self) -> None:
        await self._async_tick()

    async def _schalten(self, entity_id: str | None, an: bool) -> None:
        if not entity_id:
            return
        st = self.hass.states.get(entity_id)
        if st is not None and (st.state == STATE_ON) == an:
            return
        domain = entity_id.split(".", 1)[0]
        dienst = "turn_on" if an else "turn_off"
        if not self.hass.services.has_service(domain, dienst):
            domain = "homeassistant"
        await self.hass.services.async_call(domain, dienst, {"entity_id": entity_id}, blocking=True)

    async def _regeln(self, schrank: dict[str, Any]) -> None:
        sid = schrank["id"]
        z = self.zustand.setdefault(sid, {"modus": "frei", "kuehlung_aus_seit": None})
        sud_id = self.sud_fuer_schrank(sid)
        kuehlung, heizung = schrank.get("kuehlung"), schrank.get("heizung")

        if sud_id is None:
            if z.get("modus") not in ("frei", None):
                # Regelung beendet (Sud fertig oder entfernt) -> sicher ausschalten
                await self._schalten(kuehlung, False)
                await self._schalten(heizung, False)
            z.update(modus="frei", sud_id=None, soll=None, ist=self._ist(schrank, None), stufe=None)
            return

        stufe = self.aktuelle_stufe(sud_id)
        soll = stufe["soll"] if stufe else None
        ist = self._ist(schrank, sud_id)
        alte_stufe, alter_sud = z.get("stufe"), z.get("sud_id")
        z.update(sud_id=sud_id, soll=soll, ist=ist, stufe=stufe)

        # Stufenwechsel melden (z. B. Diacetylrast)
        if stufe and alte_stufe and stufe != alte_stufe and alter_sud == sud_id and self.coord.benachrichtiger:
            sud = self.coord.data.sude.get(sud_id)
            await self.coord.benachrichtiger.async_senden(
                f"{sud.name if sud else 'Sud'}: neue Solltemperatur",
                f"Ab {stufe['ab_vg']:.0f} % Vergärung jetzt {stufe['soll']:.1f} °C im {schrank['name']}.",
                ereignis="gaerschrank",
            )

        if soll is None:
            return
        if ist is None:
            await self._schalten(kuehlung, False)
            await self._schalten(heizung, False)
            if z.get("modus") != "fehler" and self.coord.benachrichtiger:
                await self.coord.benachrichtiger.async_senden(
                    f"{schrank['name']}: kein Temperaturwert",
                    "Kühlung und Heizung sind aus Sicherheitsgründen ausgeschaltet.",
                    ereignis="gaerschrank", schluessel=f"schrank_fehler:{sid}", dringend=True,
                )
            z["modus"] = "fehler"
            return
        if self.coord.benachrichtiger:
            self.coord.benachrichtiger.async_zuruecksetzen(f"schrank_fehler:{sid}")

        h = float(schrank.get("hysterese", 0.5))
        pause = timedelta(minutes=float(schrank.get("min_pause_min", 5)))
        modus = z.get("modus")
        jetzt = dt_util.utcnow()

        if ist > soll + h and kuehlung:
            ziel = "kuehlen"
        elif ist < soll - h and heizung:
            ziel = "heizen"
        elif modus == "kuehlen" and ist > soll:
            ziel = "kuehlen"
        elif modus == "heizen" and ist < soll:
            ziel = "heizen"
        else:
            ziel = "aus"

        if ziel == "kuehlen":
            aus_seit = z.get("kuehlung_aus_seit")
            if modus != "kuehlen" and aus_seit and jetzt - aus_seit < pause:
                await self._schalten(heizung, False)
                z["modus"] = "pause"
                return
            await self._schalten(heizung, False)
            await self._schalten(kuehlung, True)
        elif ziel == "heizen":
            if modus == "kuehlen":
                z["kuehlung_aus_seit"] = jetzt
            await self._schalten(kuehlung, False)
            await self._schalten(heizung, True)
        else:
            if modus == "kuehlen":
                z["kuehlung_aus_seit"] = jetzt
            await self._schalten(kuehlung, False)
            await self._schalten(heizung, False)
        z["modus"] = ziel
