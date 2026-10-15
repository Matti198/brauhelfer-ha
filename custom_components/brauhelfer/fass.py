"""Fässer: Füllstand über Gläser (NFC-Tags) und Wiegen.

- Ein Sud kann auf mehrere Fässer verteilt sein.
- Jedes Fass hat ein Leergewicht (Tara) und optional eine Waage (HA-Sensor).
- NFC-Tags gehören zu einem Fass und haben je eine Glasgröße. Ein Scan in der
  HA-App zieht ein Glas ab.
- Wiegen setzt den Restbestand neu: (brutto − tara) / Dichte des Biers.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from . import brauhelfer_db as db
from .speicher import neue_id

if TYPE_CHECKING:
    from .coordinator import BrauhelferCoordinator

_LOGGER = logging.getLogger(__name__)

EVENT_TAG_SCANNED = "tag_scanned"
EVENT_GLAS = "brauhelfer_glas"
LERNEN_DAUER = timedelta(minutes=3)
HISTORIE_MAX = 400
WASSER_DICHTE = 0.998  # kg/l bei etwa 20 °C


class Fasskeller:
    def __init__(self, coord: BrauhelferCoordinator) -> None:
        self.coord = coord
        self.hass: HomeAssistant = coord.hass
        self._unsub = None
        self.lernen: dict[str, Any] | None = None
        self.letzter_scan: dict[str, Any] | None = None

    @property
    def faesser(self) -> list[dict[str, Any]]:
        return self.coord.speicher.data["faesser"]

    @property
    def tags(self) -> list[dict[str, Any]]:
        return self.coord.speicher.data["tags"]

    @callback
    def async_start(self) -> None:
        self._unsub = self.hass.bus.async_listen(EVENT_TAG_SCANNED, self._async_tag)

    @callback
    def async_stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    def _fass(self, fass_id: str) -> dict[str, Any]:
        f = self.coord.speicher.fass(fass_id)
        if f is None:
            raise HomeAssistantError("Fass nicht gefunden")
        return f

    def _historie(self, f: dict[str, Any], typ: str, liter: float, text: str = "") -> None:
        f.setdefault("historie", []).append(
            {"zeit": dt_util.now().isoformat(), "typ": typ, "liter": round(liter, 3), "rest": round(f["rest_l"], 3), "text": text}
        )
        del f["historie"][:-HISTORIE_MAX]

    def dichte(self, sud_id: int | None) -> float:
        """Dichte des Biers in kg/l aus dem scheinbaren Restextrakt."""
        sre = None
        sud = self.coord.data.sude.get(sud_id) if self.coord.data and sud_id else None
        if sud and sud.letzter_messwert:
            sre = sud.letzter_messwert.restextrakt
        sg = db.plato_to_dichte(sre) if sre is not None else 1.010
        return sg * WASSER_DICHTE

    # ------------------------------------------------------------------ Fässer
    def anlegen(self, sud_id: int, name: str, tara_kg: float, inhalt_l: float, waage: str | None) -> dict[str, Any]:
        if tara_kg < 0 or inhalt_l < 0 or inhalt_l > 200:
            raise HomeAssistantError("Ungültige Werte für Tara oder Inhalt")
        f = {
            "id": neue_id(), "sud_id": sud_id, "name": name.strip() or "Fass", "tara_kg": tara_kg,
            "inhalt_l": inhalt_l, "rest_l": inhalt_l, "waage": waage or None, "leer": False,
            "angelegt": dt_util.now().isoformat(), "historie": [],
        }
        self._historie(f, "fuellen", inhalt_l, "Abgefüllt")
        self.faesser.append(f)
        self.coord.speicher.speichern()
        self._geaendert()
        return f

    def bearbeiten(self, fass_id: str, **werte: Any) -> None:
        f = self._fass(fass_id)
        if werte.get("name"):
            f["name"] = str(werte["name"]).strip()
        if werte.get("tara_kg") is not None:
            if werte["tara_kg"] < 0:
                raise HomeAssistantError("Leergewicht kann nicht negativ sein")
            f["tara_kg"] = float(werte["tara_kg"])
        if "waage" in werte:
            f["waage"] = werte["waage"] or None
        if werte.get("rest_l") is not None:
            alt = f["rest_l"]
            f["rest_l"] = max(0.0, float(werte["rest_l"]))
            f["leer"] = f["rest_l"] <= 0.05
            self._historie(f, "korrektur", f["rest_l"] - alt, "Von Hand korrigiert")
        self.coord.speicher.speichern()
        self._geaendert()

    def loeschen(self, fass_id: str) -> None:
        self._fass(fass_id)
        self.coord.speicher.data["faesser"] = [f for f in self.faesser if f["id"] != fass_id]
        self.coord.speicher.data["tags"] = [t for t in self.tags if t["fass_id"] != fass_id]
        self.coord.speicher.speichern()
        self._geaendert()

    def wiegen(self, fass_id: str, brutto_kg: float | None = None) -> dict[str, Any]:
        """Restbestand aus Gewicht. Ohne Wert wird die Waage des Fasses gelesen."""
        f = self._fass(fass_id)
        if brutto_kg is None:
            if not f.get("waage"):
                raise HomeAssistantError("Für dieses Fass ist keine Waage hinterlegt – Gewicht bitte eintippen")
            st = self.hass.states.get(f["waage"])
            if st is None or st.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
                raise HomeAssistantError(f"Die Waage {f['waage']} liefert keinen Wert")
            try:
                brutto_kg = float(st.state)
            except ValueError as err:
                raise HomeAssistantError(f"Die Waage meldet „{st.state}“") from err
            einheit = (st.attributes.get("unit_of_measurement") or "kg").lower()
            if einheit == "g":
                brutto_kg /= 1000
            elif einheit in ("lb", "lbs"):
                brutto_kg *= 0.45359237
        netto = brutto_kg - f["tara_kg"]
        if netto < -0.3:
            raise HomeAssistantError(
                f"Gewogen {brutto_kg:.2f} kg ist weniger als das Leergewicht ({f['tara_kg']:.2f} kg). Tara prüfen."
            )
        liter = max(0.0, netto / self.dichte(f["sud_id"]))
        alt = f["rest_l"]
        f["rest_l"] = liter
        f["leer"] = liter <= 0.05
        f["letzte_wiegung"] = {"zeit": dt_util.now().isoformat(), "brutto_kg": round(brutto_kg, 3)}
        self._historie(f, "wiegen", liter - alt, f"{brutto_kg:.2f} kg gewogen")
        self.coord.speicher.speichern()
        self._geaendert()
        return f

    def glas(self, fass_id: str, liter: float, quelle: str = "") -> dict[str, Any]:
        f = self._fass(fass_id)
        if f.get("leer"):
            raise HomeAssistantError(f"Fass {f['name']} ist schon leer")
        alt = f["rest_l"]
        f["rest_l"] = max(0.0, alt - liter)
        self._historie(f, "glas", -(alt - f["rest_l"]), quelle)
        if f["rest_l"] <= 0.05:
            f["leer"] = True
        self.coord.speicher.speichern()
        self._geaendert()
        self.hass.bus.async_fire(EVENT_GLAS, {"fass_id": fass_id, "name": f["name"], "liter": liter, "rest_l": f["rest_l"]})
        return f

    # ------------------------------------------------------------------ NFC-Tags
    def tag_zuordnen(self, fass_id: str, tag_id: str, glas_l: float, name: str = "") -> None:
        self._fass(fass_id)
        if not 0.05 <= glas_l <= 5:
            raise HomeAssistantError("Glasgröße zwischen 0,05 und 5 l angeben")
        self.coord.speicher.data["tags"] = [t for t in self.tags if t["tag_id"] != tag_id]
        self.tags.append({"tag_id": tag_id, "fass_id": fass_id, "glas_l": glas_l, "name": name or f"{glas_l:g} l"})
        self.coord.speicher.speichern()
        self._geaendert()

    def tag_entfernen(self, tag_id: str) -> None:
        self.coord.speicher.data["tags"] = [t for t in self.tags if t["tag_id"] != tag_id]
        self.coord.speicher.speichern()
        self._geaendert()

    def lernen_starten(self, fass_id: str, glas_l: float, name: str = "") -> None:
        self._fass(fass_id)
        self.lernen = {"fass_id": fass_id, "glas_l": glas_l, "name": name, "bis": dt_util.utcnow() + LERNEN_DAUER}
        self._geaendert()

    @callback
    def _async_tag(self, event: Event) -> None:
        tag_id = event.data.get("tag_id")
        if not tag_id:
            return
        if self.lernen and dt_util.utcnow() < self.lernen["bis"]:
            l = self.lernen
            self.lernen = None
            self.tag_zuordnen(l["fass_id"], tag_id, l["glas_l"], l["name"])
            self.letzter_scan = {"zeit": dt_util.now().isoformat(), "tag_id": tag_id, "gelernt": True}
            return
        self.lernen = None
        tag = next((t for t in self.tags if t["tag_id"] == tag_id), None)
        if tag is None:
            return
        try:
            f = self.glas(tag["fass_id"], tag["glas_l"], f"NFC {tag['name']}")
        except HomeAssistantError as err:
            _LOGGER.info("NFC-Scan ignoriert: %s", err)
            return
        self.letzter_scan = {"zeit": dt_util.now().isoformat(), "tag_id": tag_id, "fass_id": f["id"], "rest_l": f["rest_l"]}
        if f.get("leer") and self.coord.benachrichtiger:
            self.hass.async_create_task(self._leer_melden(f))

    async def _leer_melden(self, f: dict[str, Any]) -> None:
        sud_id = f["sud_id"]
        rest = [x for x in self.faesser if x["sud_id"] == sud_id and not x.get("leer")]
        sud = self.coord.data.sude.get(sud_id) if self.coord.data else None
        text = f"Fass {f['name']} ist leer."
        if not rest and sud:
            text += f" Das war das letzte Fass von „{sud.name}“ – auf der Brauhelfer-Seite als leer markieren?"
        await self.coord.benachrichtiger.async_senden(f"Fass {f['name']} leer", text, ereignis="fass", schluessel=f"fass_leer:{f['id']}")

    def _geaendert(self) -> None:
        self.coord.async_update_listeners()
