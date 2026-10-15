"""Brautag-Assistent: Schritte aus dem Rezept, Timer mit Erinnerungen und Ansagen.

Die Schritte entstehen aus Maischplan, Hopfengaben und weiteren Zutaten des Suds.
Die Sitzung (aktueller Schritt, laufender Timer) liegt im HA-Speicher, damit man
am Handy und am Tablet gleichzeitig mitlesen und nach einem Neustart weitermachen
kann. Timer laufen auf dem Server: die Meldungen kommen auch bei gesperrtem Handy.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from .coordinator import BrauhelferCoordinator

_LOGGER = logging.getLogger(__name__)


def _de(v: float, stellen: int = 0) -> str:
    s = f"{v:.{stellen}f}"
    return s.replace(".", ",")


def _menge_g(g: float) -> str:
    return f"{_de(g / 1000, 2)} kg" if g >= 1000 else f"{_de(g)} g"


def schritte(d: dict[str, Any]) -> list[dict[str, Any]]:
    """Ablauf des Brautags aus den Sud-Details."""
    out: list[dict[str, Any]] = []
    zutaten_maischen = [z for z in d["zutaten"] if z["zeitpunkt"] == 2]
    zutaten_kochen = [z for z in d["zutaten"] if z["zeitpunkt"] == 1]

    # 1) Vorbereitung
    zeilen = [f"Schüttung {_de(d['schuettung'], 2)} kg"] if (d.get("schuettung") or 0) > 0 else []
    zeilen += [f"{_de(m['menge_kg'], 2)} kg {m['name']}" for m in d["malz"]]
    if (d.get("hauptguss") or 0) > 0:
        zeilen.append(f"Hauptguss {_de(d['hauptguss'], 1)} l, Nachguss {_de(d['nachguss'], 1)} l")
    zeilen += [f"Zum Maischen: {_de(z['menge'])} {z['einheit']} {z['name']}" for z in zutaten_maischen]
    out.append({"key": "vorbereitung", "phase": "Vorbereitung", "titel": "Schroten und Wasser bereitstellen", "zeilen": zeilen})

    # 2) Maischplan
    for i, m in enumerate(d["maischplan"]):
        typ, name = m["typ"], m["name"]
        dauer = m["dauer"] if m["dauer"] and m["dauer"] > 1 else None
        if typ == 0:
            zeilen = [f"Hauptguss auf {_de(m['temp_wasser'])} °C erhitzen und das Malz einrühren.",
                      f"Die Maische sollte danach {_de(m['temp_rast'])} °C haben."]
        elif typ == 1:
            zeilen = [f"Auf {_de(m['temp_rast'])} °C aufheizen" + (f" und {m['dauer']} min rasten." if dauer else ".")]
        elif typ == 2:
            zeilen = [f"Wasser mit {_de(m['temp_wasser'])} °C zugeben, Maische auf {_de(m['temp_rast'])} °C bringen."]
        elif typ == 3:
            zeilen = [f"Malz zuschütten, Maische auf {_de(m['temp_rast'])} °C bringen."]
        else:
            zeilen = [
                "Teilmaische ziehen" + (f", bei {_de(m['temp_extra1'])} °C {m['dauer_extra1']} min rasten" if m["dauer_extra1"] else ""),
                f"Teilmaische {m['dauer_extra2']} min kochen" if m["dauer_extra2"] else "Teilmaische kochen",
                f"Zurückschütten, Maische auf {_de(m['temp_rast'])} °C.",
            ]
        out.append({
            "key": f"rast{i}", "phase": "Maischen", "titel": name,
            "untertitel": f"{_de(m['temp_rast'])} °C" + (f", {m['dauer']} min" if dauer else ""),
            "zeilen": zeilen, "timer_min": dauer,
            "timer_text": f"{name} ist fertig.",
        })

    # 3) Läutern
    vwh = [h for h in d["hopfen"] if h["zeitpunkt"] == 1]
    zeilen = ["Abmaischen und läutern.", f"Mit {_de(d['nachguss'], 1)} l Nachguss anschwänzen."]
    zeilen += [f"Vorderwürzehopfen in die Pfanne: {_menge_g(h['menge_g'])} {h['name']}" for h in vwh]
    out.append({"key": "laeutern", "phase": "Läutern", "titel": "Läutern",
                "zeilen": zeilen, "felder": ["WuerzemengeKochbeginn", "SWKochbeginn"]})

    # 4) Kochen mit Hopfengaben
    kd = d["kochdauer"] or 60
    ereignisse: dict[int, list[str]] = {}
    for h in d["hopfen"]:
        zp = h["zeitpunkt"]
        if zp in (0, 2, 3):
            ab = 0 if zp == 2 else max(0, kd - (h["zeit"] or 0))
        elif zp == 4:
            ab = kd
        else:
            continue
        ereignisse.setdefault(ab, []).append(f"{_menge_g(h['menge_g'])} {h['name']}")
    for z in zutaten_kochen:
        ab = max(0, kd - (z.get("kochdauer_min") or 0))
        ereignisse.setdefault(ab, []).append(f"{_de(z['menge'])} {z['einheit']} {z['name']}")
    plan = [
        {"min": ab, "text": ", ".join(t), "rest_min": kd - ab}
        for ab, t in sorted(ereignisse.items())
    ]
    zeilen = [f"{kd} min kochen."]
    for p in plan:
        if p["min"] == 0:
            wann = "Kochbeginn"
        elif p["rest_min"] == 0:
            wann = "Kochende"
        else:
            wann = f"{p['rest_min']} min vor Ende"
        zeilen.append(f"{wann}: {p['text']}")
    out.append({
        "key": "kochen", "phase": "Kochen", "titel": "Würzekochen", "untertitel": f"{kd} min",
        "zeilen": zeilen, "timer_min": kd, "ereignisse": plan, "timer_text": "Kochende – Würze ausschlagen.",
    })

    # 5) Ausschlagen / Whirlpool
    ash = [h for h in d["hopfen"] if h["zeitpunkt"] == 5]
    nach = d.get("nachisomerisierung") or 0
    zeilen = ["Würze ausschlagen" + (f", {nach} min Whirlpool/Nachisomerisierung." if nach else ".")]
    zeilen += [f"Ausschlaghopfen: {_menge_g(h['menge_g'])} {h['name']}" for h in ash]
    out.append({
        "key": "ausschlagen", "phase": "Kochen", "titel": "Ausschlagen", "zeilen": zeilen,
        "timer_min": nach or None, "timer_text": "Whirlpool fertig – Würze kühlen.",
        "felder": ["WuerzemengeVorHopfenseihen", "WuerzemengeKochende", "SWKochende"],
    })

    # 6) Anstellen
    out.append({
        "key": "anstellen", "phase": "Anstellen", "titel": "Kühlen und Anstellen",
        "zeilen": ["Würze auf Anstelltemperatur kühlen, in den Gärbehälter füllen und Hefe zugeben."],
        "felder": ["SWAnstellen", "WuerzemengeAnstellen", "VerduennungAnstellen", "Speisemenge", "MengeHefestarter", "SWHefestarter"],
        "hefe": True,
    })

    # 7) Abschluss
    out.append({"key": "abschluss", "phase": "Abschluss", "titel": "Sud gebraut", "abschluss": True,
                "zeilen": ["Braudatum und Notizen prüfen, dann den Sud auf „gebraut“ setzen."]})
    return out


class Brautag:
    def __init__(self, coord: BrauhelferCoordinator) -> None:
        self.coord = coord
        self.hass: HomeAssistant = coord.hass
        self._unsubs: list = []

    @property
    def sitzung(self) -> dict[str, Any] | None:
        return self.coord.speicher.data.get("brautag")

    def _speichern(self) -> None:
        self.coord.speicher.speichern()
        self.coord.async_update_listeners()

    @callback
    def async_start(self) -> None:
        """Nach Neustart laufenden Timer wieder einplanen."""
        s = self.sitzung
        if s and s.get("timer"):
            self._planen(s["timer"])

    @callback
    def async_stop(self) -> None:
        self._abbrechen()

    def _abbrechen(self) -> None:
        for u in self._unsubs:
            u()
        self._unsubs = []

    # ------------------------------------------------------------------ Sitzung
    def starten(self, sud_id: int) -> dict[str, Any]:
        s = self.sitzung
        if s and s["sud_id"] != sud_id and s.get("timer"):
            raise HomeAssistantError("Für einen anderen Sud läuft gerade ein Brautag mit Timer. Erst dort beenden.")
        if not s or s["sud_id"] != sud_id:
            self._abbrechen()
            self.coord.speicher.data["brautag"] = {
                "sud_id": sud_id, "schritt": "vorbereitung", "timer": None,
                "gestartet": dt_util.now().isoformat(), "erledigt": [],
            }
            self._speichern()
        return self.sitzung

    def schritt(self, key: str) -> None:
        s = self._sitzung()
        if s["schritt"] not in s["erledigt"]:
            s["erledigt"].append(s["schritt"])
        s["schritt"] = key
        self._speichern()

    def beenden(self) -> None:
        self._abbrechen()
        self.coord.speicher.data["brautag"] = None
        self._speichern()

    def _sitzung(self) -> dict[str, Any]:
        s = self.sitzung
        if not s:
            raise HomeAssistantError("Kein Brautag aktiv")
        return s

    # ------------------------------------------------------------------ Timer
    def timer_starten(self, key: str, minuten: float, titel: str, text: str, ereignisse: list[dict[str, Any]] | None) -> None:
        s = self._sitzung()
        if minuten <= 0 or minuten > 600:
            raise HomeAssistantError("Ungültige Timerdauer")
        self._abbrechen()
        start = dt_util.utcnow()
        s["timer"] = {
            "schritt": key, "titel": titel, "text": text,
            "start": start.isoformat(), "ende": (start + timedelta(minutes=minuten)).isoformat(),
            "minuten": minuten, "ereignisse": ereignisse or [], "gemeldet": [],
        }
        self._planen(s["timer"])
        self._speichern()

    def timer_stoppen(self) -> None:
        s = self._sitzung()
        self._abbrechen()
        s["timer"] = None
        self._speichern()

    def _planen(self, t: dict[str, Any]) -> None:
        start = dt_util.parse_datetime(t["start"])
        jetzt = dt_util.utcnow()
        punkte: list[tuple[datetime, str, str]] = []
        for e in t.get("ereignisse", []):
            if 0 < e["min"] < t["minuten"]:
                punkte.append((start + timedelta(minutes=e["min"]), f"e{e['min']}", f"Jetzt zugeben: {e['text']}"))
        punkte.append((dt_util.parse_datetime(t["ende"]), "ende", t["text"]))
        # Ereignis bei Minute 0 (Kochbeginn) direkt beim Start ansagen
        for e in t.get("ereignisse", []):
            if e["min"] == 0 and "e0" not in t["gemeldet"]:
                self.hass.async_create_task(self._melden(t, "e0", f"Jetzt zugeben: {e['text']}"))
        for zeit, key, text in punkte:
            if key in t["gemeldet"]:
                continue
            if zeit <= jetzt:
                # während eines Neustarts verpasst
                self.hass.async_create_task(self._melden(t, key, text))
                continue
            self._unsubs.append(
                async_track_point_in_utc_time(self.hass, self._callback(t, key, text), zeit)
            )

    def _callback(self, t: dict[str, Any], key: str, text: str):
        async def fire(_now: datetime) -> None:
            await self._melden(t, key, text)
        return fire

    async def _melden(self, t: dict[str, Any], key: str, text: str) -> None:
        if key in t["gemeldet"]:
            return
        t["gemeldet"].append(key)
        self._speichern()
        sud = self.coord.data.sude.get(self.sitzung["sud_id"]) if self.coord.data and self.sitzung else None
        if self.coord.benachrichtiger:
            await self.coord.benachrichtiger.async_senden(
                f"Brautag {sud.name if sud else ''}: {t['titel']}".strip(), text,
                ereignis="brautag", ansage=True, dringend=True,
            )
