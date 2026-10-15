"""Daten, die der Brauhelfer nicht kennt: Fässer, Gärschränke, Einstellungen, Brautag-Sitzung.

Liegt im HA-Speicher (.storage/brauhelfer.<entry_id>), nicht in der Brauhelfer-Datenbank.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

STORE_VERSION = 1

STANDARD_BENACHRICHTIGUNG: dict[str, Any] = {
    "ziele": [],            # notify-Dienste für Push (z. B. mobile_app_iphone)
    "lautsprecher": [],     # media_player für Ansagen (Sonos, Music Assistant, …)
    "tts": None,            # TTS-Engine (tts.…); leer = erste vorhandene
    "lautstaerke": None,    # Lautstärke der Ansage in %, leer = wie am Lautsprecher eingestellt
    "ereignisse": {
        "stagnation": True,
        "temperatur": True,
        "pill_offline": True,
        "akku": True,
        "ziel_vg": True,
        "zutaten": True,
        "fass": True,
        "brautag": True,
        "gaerschrank": True,
    },
    "stagnation_h": 48,
    "stagnation_plato": 0.3,
    "temp_toleranz": 2.0,
    "temp_dauer_min": 30,
    "akku_prozent": 20,
    "fass_rest_l": 3.0,
}


def neue_id() -> str:
    return uuid.uuid4().hex[:10]


class Speicher:
    """Einfacher Schlüssel-Wert-Speicher mit verzögertem Schreiben."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, STORE_VERSION, f"{DOMAIN}.{entry_id}")
        self.data: dict[str, Any] = {}

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        data.setdefault("aufzeichnungen", [])
        data.setdefault("faesser", [])
        data.setdefault("tags", [])
        data.setdefault("schraenke", [])
        data.setdefault("regelung", {})
        data.setdefault("gesendet", {})
        data.setdefault("brautag", None)
        data.setdefault("lager_buchungen", {})
        e = data.setdefault("einstellungen", {})
        e.setdefault("lager", False)
        e.setdefault("einkaufsliste", None)
        e.setdefault("glaettung_min", 30)
        data.setdefault("pill_korrektur", {})   # entity_id -> {"wert", "datum", "referenz"}
        data.setdefault("erinnern", {})         # sud_id -> ISO-Zeit für "Noch warten"
        b = copy.deepcopy(STANDARD_BENACHRICHTIGUNG)
        gespeichert = data.get("benachrichtigung") or {}
        b.update({k: v for k, v in gespeichert.items() if k not in ("ereignisse", "ansage")})
        b["ereignisse"].update(gespeichert.get("ereignisse") or {})
        data["benachrichtigung"] = b
        self.data = data

    def speichern(self) -> None:
        """Verzögert speichern (fasst schnelle Änderungen zusammen)."""
        self._store.async_delay_save(lambda: self.data, 2)

    async def async_jetzt_speichern(self) -> None:
        await self._store.async_save(self.data)

    # ------------------------------------------------------------------ Helfer
    def fass(self, fass_id: str) -> dict[str, Any] | None:
        return next((f for f in self.data["faesser"] if f["id"] == fass_id), None)

    def schrank(self, schrank_id: str) -> dict[str, Any] | None:
        return next((s for s in self.data["schraenke"] if s["id"] == schrank_id), None)

    def regelung(self, sud_id: int) -> dict[str, Any] | None:
        return self.data["regelung"].get(str(sud_id))

    @property
    def einstellungen(self) -> dict[str, Any]:
        return self.data["einstellungen"]

    @property
    def benachrichtigung(self) -> dict[str, Any]:
        return self.data["benachrichtigung"]
