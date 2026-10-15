"""Benachrichtigungen aufs Handy und Sprachansagen über Lautsprecher (TTS).

Jede Meldung hat einen Schlüssel. Sie wird nur einmal gesendet, bis der Zustand
sich wieder normalisiert hat (dann wird der Schlüssel gelöscht und die Meldung
kann erneut kommen). Die gesendeten Schlüssel überleben Neustarts.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components import persistent_notification
from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from . import brauhelfer_db as db

if TYPE_CHECKING:
    from .coordinator import BrauhelferCoordinator

_LOGGER = logging.getLogger(__name__)

PRUEF_INTERVALL = timedelta(minutes=5)
PANEL_URL = "/brauhelfer"
AKTION_EVENT = "mobile_app_notification_action"
AKTION_RE = re.compile(r"BRAUHELFER_(FERTIG|WARTEN)_(\d+)")
WARTEN = timedelta(days=2)


def gaer_aktionen(sud_id: int) -> list[dict[str, Any]]:
    """Knöpfe für die Push-Meldung (iOS/Android-App von Home Assistant)."""
    return [
        {"action": f"BRAUHELFER_FERTIG_{sud_id}", "title": "Gärung fertig",
         "destructive": True, "authenticationRequired": True},
        {"action": f"BRAUHELFER_WARTEN_{sud_id}", "title": "Noch 2 Tage warten"},
    ]


def notify_dienste(hass: HomeAssistant) -> list[str]:
    """Alle notify-Dienste außer den generischen."""
    dienste = hass.services.async_services().get("notify", {})
    return sorted(d for d in dienste if d not in ("send_message", "notify"))


def kann_ankuendigen(hass: HomeAssistant, entity_id: str) -> bool:
    """Unterstützt der Player den Ankündigungsmodus (Musik wird leiser statt gestoppt)?"""
    st = hass.states.get(entity_id)
    return bool(st and int(st.attributes.get("supported_features") or 0) & MediaPlayerEntityFeature.MEDIA_ANNOUNCE)


def standard_tts(hass: HomeAssistant) -> str | None:
    engines = sorted(st.entity_id for st in hass.states.async_all("tts"))
    return engines[0] if engines else None


class Benachrichtiger:
    def __init__(self, coord: BrauhelferCoordinator) -> None:
        self.coord = coord
        self.hass: HomeAssistant = coord.hass
        self._unsub = None
        self._unsub_aktion = None
        self._temp_ausserhalb_seit: dict[int, datetime] = {}

    @property
    def cfg(self) -> dict[str, Any]:
        return self.coord.speicher.benachrichtigung

    @property
    def gesendet(self) -> dict[str, str]:
        return self.coord.speicher.data["gesendet"]

    @callback
    def async_start(self) -> None:
        self._unsub = async_track_time_interval(self.hass, self._async_pruefen, PRUEF_INTERVALL, name="Brauhelfer Meldungen")
        self._unsub_aktion = self.hass.bus.async_listen(AKTION_EVENT, self._async_aktion)

    @callback
    def async_stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
        if self._unsub_aktion:
            self._unsub_aktion()
            self._unsub_aktion = None

    # ------------------------------------------------------------------ Knöpfe in der Meldung
    async def _async_aktion(self, event: Event) -> None:
        m = AKTION_RE.fullmatch(str(event.data.get("action") or ""))
        if not m:
            return
        art, sud_id = m.group(1), int(m.group(2))
        snap = self.coord.data
        sud = snap.sude.get(sud_id) if snap else None
        if sud is None or sud.status != db.STATUS_GEBRAUT:
            return
        if art == "WARTEN":
            self.coord.speicher.data["erinnern"][str(sud_id)] = (dt_util.now() + WARTEN).isoformat()
            self.coord.speicher.speichern()
            _LOGGER.info("„%s“: erinnere in %s erneut", sud.name, WARTEN)
            return
        try:
            await self.coord.async_abfuellen(sud_id, None, None)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("„%s“ konnte nicht als fertig eingetragen werden: %s", sud.name, err)
            await self.async_senden(
                f"{sud.name}: nicht eingetragen", f"Gärung fertig ging nicht: {err}", ereignis="aktion",
            )
            return
        self.coord.speicher.data["erinnern"].pop(str(sud_id), None)
        await self.async_senden(
            f"{sud.name} ist abgefüllt",
            "Gärung als fertig eingetragen. Aufzeichnung und Gärschrank-Regelung sind beendet.",
            ereignis="aktion",
        )

    # ------------------------------------------------------------------ senden
    async def async_senden(
        self, titel: str, text: str, *, ereignis: str, schluessel: str | None = None,
        ansage: bool = False, dringend: bool = False, aktionen: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Meldung senden. Mit Schlüssel nur einmal, bis `async_zuruecksetzen`."""
        if not self.cfg["ereignisse"].get(ereignis, True):
            return False
        if schluessel and schluessel in self.gesendet:
            return False
        if schluessel:
            self.gesendet[schluessel] = dt_util.now().isoformat()
            self.coord.speicher.speichern()

        ziele = list(self.cfg["ziele"])
        if not ziele and not (ansage and self.cfg["lautsprecher"]):
            # Ohne eingerichtetes Ziel wenigstens in HA anzeigen
            persistent_notification.async_create(
                self.hass, text, title=titel, notification_id=f"brauhelfer_{schluessel or ereignis}"
            )
            return True

        for ziel in ziele:
            data: dict[str, Any] = {"url": PANEL_URL, "clickAction": PANEL_URL, "group": "brauhelfer"}
            if dringend:
                data["push"] = {"interruption-level": "time-sensitive"}
            if aktionen:
                data["actions"] = aktionen
            await self._call(ziel, {"title": titel, "message": text, "data": data})
        if ansage and self.cfg["lautsprecher"]:
            await self.async_ansagen(text)
        return True

    async def async_ansagen(self, text: str) -> None:
        """Text per TTS auf den gewählten Lautsprechern ansagen.

        Mit Ankündigungsmodus (Sonos, Music Assistant) wird laufende Musik nur kurz
        leiser und läuft danach weiter.
        """
        from homeassistant.components import tts  # noqa: PLC0415 - erst laden, wenn wirklich angesagt wird

        engine = self.cfg.get("tts") or standard_tts(self.hass)
        if not engine:
            _LOGGER.warning("Keine Sprachausgabe (TTS) in Home Assistant eingerichtet, Ansage entfällt")
            return
        try:
            media_id = tts.generate_media_source_id(self.hass, text, engine=engine)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Ansage mit %s nicht möglich: %s", engine, err)
            return
        for ent in self.cfg["lautsprecher"]:
            if self.hass.states.get(ent) is None:
                _LOGGER.warning("Lautsprecher %s gibt es nicht", ent)
                continue
            data: dict[str, Any] = {"entity_id": ent, "media_content_id": media_id, "media_content_type": "music"}
            if kann_ankuendigen(self.hass, ent):
                data["announce"] = True
                if self.cfg.get("lautstaerke"):
                    data["extra"] = {"volume": self.cfg["lautstaerke"] / 100}
            try:
                await self.hass.services.async_call("media_player", "play_media", data, blocking=False)
            except Exception as err:  # noqa: BLE001 - eine fehlerhafte Ansage darf nichts blockieren
                _LOGGER.warning("Ansage auf %s fehlgeschlagen: %s", ent, err)

    async def _call(self, dienst: str, payload: dict[str, Any]) -> None:
        if not self.hass.services.has_service("notify", dienst):
            _LOGGER.warning("Benachrichtigungsdienst notify.%s gibt es nicht", dienst)
            return
        try:
            await self.hass.services.async_call("notify", dienst, payload, blocking=False)
        except Exception as err:  # noqa: BLE001 - eine fehlerhafte Meldung darf nichts blockieren
            _LOGGER.warning("Meldung über notify.%s fehlgeschlagen: %s", dienst, err)

    @callback
    def async_zuruecksetzen(self, schluessel: str) -> None:
        if self.gesendet.pop(schluessel, None) is not None:
            self.coord.speicher.speichern()

    # ------------------------------------------------------------------ prüfen
    async def _async_pruefen(self, _now: datetime | None = None) -> None:
        try:
            await self.async_pruefen()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Fehler beim Prüfen der Brauhelfer-Meldungen")

    async def async_pruefen(self) -> None:
        snap = self.coord.data
        if snap is None:
            return
        for sud in snap.gaerend:
            await self._pruefe_gaerung(sud)
        await self._pruefe_zutaten(snap)
        await self._pruefe_faesser()

    async def _pruefe_gaerung(self, sud: db.Sud) -> None:
        cfg = self.cfg
        a = self.coord.aufzeichnungen.get(sud.id)
        live = self.coord.live_werte(sud.id)

        # "Noch warten" abgelaufen: Meldungen dürfen erneut kommen
        erinnern = self.coord.speicher.data["erinnern"].get(str(sud.id))
        if erinnern and dt_util.parse_datetime(erinnern) <= dt_util.now():
            self.coord.speicher.data["erinnern"].pop(str(sud.id), None)
            self.coord.speicher.speichern()
            self.async_zuruecksetzen(f"ziel_vg:{sud.id}")
            self.async_zuruecksetzen(f"stagnation:{sud.id}")

        # Ziel-Vergärungsgrad erreicht
        if live["vg"] is not None and sud.vergaerungsgrad_rezept > 0:
            if live["vg"] >= sud.vergaerungsgrad_rezept - 1:
                await self.async_senden(
                    f"{sud.name}: Ziel erreicht",
                    f"Vergärungsgrad {live['vg']:.0f} % von {sud.vergaerungsgrad_rezept:.0f} % "
                    f"(Restextrakt {live['sre']:.1f} °P). Fertig? Dann gedrückt halten und „Gärung fertig“ wählen.",
                    ereignis="ziel_vg", schluessel=f"ziel_vg:{sud.id}", aktionen=gaer_aktionen(sud.id),
                )

        # Gärung stagniert: alle Einträge der letzten X Stunden innerhalb weniger Zehntel °P
        verlauf = [m for m in sud.verlauf if m.zeitstempel]
        if verlauf:
            fenster = timedelta(hours=cfg["stagnation_h"])
            jetzt = db.jetzt()
            im_fenster = [m for m in verlauf if jetzt - m.zeitstempel <= fenster]
            aelter = [m for m in verlauf if jetzt - m.zeitstempel > fenster]
            schluessel = f"stagnation:{sud.id}"
            if im_fenster and aelter and len(im_fenster) >= 3:
                werte = [m.restextrakt for m in im_fenster] + [aelter[-1].restextrakt]
                if max(werte) - min(werte) <= cfg["stagnation_plato"]:
                    await self.async_senden(
                        f"{sud.name}: Gärung steht",
                        f"Seit {cfg['stagnation_h']} h kaum Veränderung ({min(werte):.1f}–{max(werte):.1f} °P). "
                        "Fertig? Dann gedrückt halten und „Gärung fertig“ wählen.",
                        ereignis="stagnation", schluessel=schluessel, aktionen=gaer_aktionen(sud.id),
                    )
                else:
                    self.async_zuruecksetzen(schluessel)

        if a is None:
            return

        # Pill offline
        alter = self.coord.state_age(a.gravity)
        schluessel = f"pill_offline:{sud.id}"
        if alter is None or alter > self.coord.max_age:
            minuten = int(alter.total_seconds() // 60) if alter else None
            await self.async_senden(
                f"{a.name} meldet sich nicht",
                f"Seit {minuten} min kein Wert für „{sud.name}“. Akku, Reichweite oder Bluetooth-Proxy prüfen."
                if minuten is not None else f"Kein Wert für „{sud.name}“.",
                ereignis="pill_offline", schluessel=schluessel,
            )
        else:
            self.async_zuruecksetzen(schluessel)

        # Akku
        akku = self._akku(a.gravity)
        schluessel = f"akku:{a.gravity}"
        if akku is not None:
            if akku <= cfg["akku_prozent"]:
                await self.async_senden(
                    f"{a.name}: Akku schwach", f"Noch {akku:.0f} %. Bitte bald laden.",
                    ereignis="akku", schluessel=schluessel,
                )
            elif akku > cfg["akku_prozent"] + 5:
                self.async_zuruecksetzen(schluessel)

        # Temperatur außerhalb des Bereichs (nur wenn ein Gärschrank mit Soll regelt)
        soll = self.coord.regler.soll_fuer_sud(sud.id) if self.coord.regler else None
        ist = self.coord.regler.ist_fuer_sud(sud.id) if self.coord.regler else live["temp"]
        schluessel = f"temperatur:{sud.id}"
        if soll is not None and ist is not None:
            if abs(ist - soll) > cfg["temp_toleranz"]:
                seit = self._temp_ausserhalb_seit.setdefault(sud.id, dt_util.utcnow())
                if dt_util.utcnow() - seit >= timedelta(minutes=cfg["temp_dauer_min"]):
                    await self.async_senden(
                        f"{sud.name}: Temperatur {ist:.1f} °C",
                        f"Soll {soll:.1f} °C, Abweichung seit über {cfg['temp_dauer_min']} min. Gärschrank prüfen.",
                        ereignis="temperatur", schluessel=schluessel, dringend=True,
                    )
            else:
                self._temp_ausserhalb_seit.pop(sud.id, None)
                self.async_zuruecksetzen(schluessel)

    def _akku(self, gravity_entity: str) -> float | None:
        ent_reg = er.async_get(self.hass)
        e = ent_reg.async_get(gravity_entity)
        if e is None or not e.device_id:
            return None
        for other in er.async_entries_for_device(ent_reg, e.device_id):
            if (other.device_class or other.original_device_class) == "battery" and other.domain == "sensor":
                st = self.hass.states.get(other.entity_id)
                try:
                    return float(st.state) if st else None
                except ValueError:
                    return None
        return None

    async def _pruefe_zutaten(self, snap: db.Snapshot) -> None:
        if not self.cfg["ereignisse"].get("zutaten", True):
            return
        jetzt = db.jetzt()
        for sud in snap.gaerend:
            try:
                details = await self.hass.async_add_executor_job(db.get_sud_details, self.coord.path, sud.id)
            except db.BrauhelferError:
                continue
            for z in details["zutaten"]:
                if z["zeitpunkt"] != 0:
                    continue
                art = "Hopfen stopfen" if z["hopfen"] else "Zutat zugeben"
                if z["status"] == 0 and z.get("zugabe_datum") and datetime.fromisoformat(z["zugabe_datum"]) <= jetzt:
                    await self.async_senden(
                        f"{sud.name}: {art}",
                        f"Heute fällig: {z['menge']:.0f} {z['einheit']} {z['name']}.",
                        ereignis="zutaten", schluessel=f"zugabe:{z['id']}",
                    )
                if (
                    z["status"] == 1 and z["mit_entnahme"] and z.get("entnahme_datum")
                    and datetime.fromisoformat(z["entnahme_datum"]) <= jetzt
                ):
                    await self.async_senden(
                        f"{sud.name}: {z['name']} entnehmen",
                        f"{z['name']} war {z['dauer_tage']:.0f} Tage drin und kann jetzt raus.",
                        ereignis="zutaten", schluessel=f"entnahme:{z['id']}",
                    )

    async def _pruefe_faesser(self) -> None:
        grenze = self.cfg["fass_rest_l"]
        for f in self.coord.speicher.data["faesser"]:
            if f.get("leer"):
                continue
            schluessel = f"fass_rest:{f['id']}"
            if f["rest_l"] <= grenze:
                await self.async_senden(
                    f"Fass {f['name']} fast leer",
                    f"Noch etwa {f['rest_l']:.1f} l ({f['rest_l'] / 0.5:.0f} Gläser à 0,5 l).",
                    ereignis="fass", schluessel=schluessel,
                )
            elif f["rest_l"] > grenze + 1:
                self.async_zuruecksetzen(schluessel)
