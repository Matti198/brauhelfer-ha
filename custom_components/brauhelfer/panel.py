"""Seitenleisten-Panel „Brauhelfer“ und die Websocket-Schnittstelle dafür."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from . import brauhelfer_db as db, prognose
from .const import DOMAIN

PANEL_URL = "brauhelfer"
STATIC_URL = "/brauhelfer_static"
FRONTEND_DIR = Path(__file__).parent / "frontend"
_DATA_STATIC = f"{DOMAIN}_static_registered"


def _version() -> str:
    """Cache-Buster: jüngste Änderung aller Frontend-Dateien.

    Die Version steckt im Pfad (nicht nur im Query-String), damit auch die per
    import nachgeladenen Module nach einem Update neu geholt werden – sonst hält
    z. B. die iOS-App alte Module im Cache.
    """
    try:
        return str(max(int(f.stat().st_mtime) for f in FRONTEND_DIR.glob("*.js")))
    except (OSError, ValueError):
        return "0"


async def async_register_panel(hass: HomeAssistant) -> None:
    version = await hass.async_add_executor_job(_version)
    pfad = f"{STATIC_URL}/{version}"
    registriert: set[str] = hass.data.setdefault(_DATA_STATIC, set())
    if pfad not in registriert:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(pfad, str(FRONTEND_DIR), cache_headers=True)]
        )
        registriert.add(pfad)
    if PANEL_URL in hass.data.get(frontend.DATA_PANELS, {}):
        return
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL,
        webcomponent_name="brauhelfer-panel",
        sidebar_title="Brauhelfer",
        sidebar_icon="mdi:glass-mug-variant",
        module_url=f"{pfad}/brauhelfer-panel.js",
        require_admin=False,
        config={},
    )


@callback
def async_remove_panel(hass: HomeAssistant) -> None:
    frontend.async_remove_panel(hass, PANEL_URL)


# --------------------------------------------------------------------------
# Websocket
# --------------------------------------------------------------------------

@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    for cmd in (ws_data, ws_braudaten, ws_braudaten_speichern, ws_aufzeichnung_starten,
                ws_aufzeichnung_beenden, ws_eintragen, ws_abfuellen, ws_verbraucht,
                ws_details, ws_zutat, ws_hefe, ws_schnellgaer, ws_nachgaer, ws_bewertung,
                ws_fass, ws_tag, ws_schrank, ws_regelung, ws_einstellungen, ws_test_meldung,
                ws_auswahl, ws_brautag, ws_brautag_aktion, ws_lager_bedarf, ws_lager_abziehen,
                ws_einkaufsliste, ws_pill_abgleich):
        websocket_api.async_register_command(hass, cmd)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _messwert(m: db.Messwert) -> dict[str, Any]:
    return {
        "zeit": _iso(m.zeitstempel),
        "restextrakt": m.restextrakt,
        "alkohol": round(m.alc, 2),
        "temperatur": m.temp,
        "bemerkung": m.bemerkung,
    }


def _sud(sud: db.Sud) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": sud.id,
        "name": sud.name,
        "nummer": sud.nummer,
        "status": sud.status,
        "kategorie": sud.kategorie,
        "menge": sud.menge,
        "sw_rezept": sud.sw_rezept,
        "sw": round(sud.sw_ist, 2),
        "ibu": sud.ibu,
        "co2": sud.co2,
        "ebc": sud.farbe_ebc,
        "alkohol_rezept": round(sud.alkohol_rezept, 2),
        "vg_rezept": sud.vergaerungsgrad_rezept,
        "sre_erwartet": round(sud.sre_erwartet, 2),
        "hefe": sud.hefe,
        "kommentar": sud.kommentar,
        "lager_fehlt": sud.lager_fehlt,
    }
    if sud.status >= db.STATUS_GEBRAUT:
        data["braudatum"] = _iso(sud.braudatum)
        data["verlauf"] = [_messwert(m) for m in sud.verlauf]
        data["sre_schnellgaer"] = sud.sre_schnellgaer
    if sud.status == db.STATUS_GEBRAUT:
        pg = prognose.fuer_sud(sud, db.jetzt())
        data["prognose"] = {"fertig_am": _iso(pg["fertig_am"]), "erreicht": pg["erreicht"], "endwert": round(pg["endwert"], 2)} if pg else None
    if sud.status >= db.STATUS_ABGEFUELLT:
        data["abfuelldatum"] = _iso(sud.abfuelldatum)
    return data


def _status(st) -> dict[str, Any]:
    return {
        "letzter_eintrag": _iso(st.letzter_eintrag),
        "fehler": st.letzter_fehler,
        "letzter_versuch": _iso(st.letzter_versuch),
    }


def _coordinator(hass: HomeAssistant, entry_id: str | None):
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        if entry_id is None or entry.entry_id == entry_id:
            return entry.runtime_data
    return None


def _ws_handler(schema: dict):
    """Dekorator: Coordinator holen, Fehler als Websocket-Fehler melden."""

    def wrap(func):
        @websocket_api.websocket_command({**schema, vol.Optional("entry_id"): str})
        @websocket_api.async_response
        async def handler(hass, connection, msg):
            coord = _coordinator(hass, msg.get("entry_id"))
            if coord is None:
                connection.send_error(msg["id"], "not_loaded", "Brauhelfer-Integration nicht geladen")
                return
            try:
                result = await func(hass, coord, msg)
            except (HomeAssistantError, db.BrauhelferError) as err:
                connection.send_error(msg["id"], "brauhelfer_error", str(err))
                return
            connection.send_result(msg["id"], result or {})

        return handler

    return wrap


@websocket_api.websocket_command({vol.Required("type"): "brauhelfer/data"})
@callback
def ws_data(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    result = []
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        coord = entry.runtime_data
        snap = coord.data
        if snap is None:
            continue
        result.append(
            {
                "entry_id": entry.entry_id,
                "title": entry.title,
                "path": coord.path,
                "db_version": snap.db_version,
                "geaendert": datetime.fromtimestamp(snap.mtime).astimezone().isoformat(),
                "intervall_min": int(coord.interval.total_seconds() // 60),
                "max_alter_min": int(coord.max_age.total_seconds() // 60),
                "aufzeichnungen": {str(k): a.as_dict() for k, a in coord.aufzeichnungen.items()},
                "sud_status": {str(k): _status(v) for k, v in coord.sud_status.items()},
                "pills": coord.async_find_pills(),
                "entities": _entity_ids(hass, entry.entry_id),
                "faesser": [{k: v for k, v in f.items() if k != "historie"} for f in coord.speicher.data["faesser"]],
                "tags": coord.speicher.data["tags"],
                "schraenke": coord.speicher.data["schraenke"],
                "schrank_status": coord.regler.status(),
                "regelung": coord.speicher.data["regelung"],
                "regel_soll": {str(s_.id): coord.regler.soll_fuer_sud(s_.id) for s_ in snap.gaerend},
                "benachrichtigung": coord.speicher.benachrichtigung,
                "einstellungen": coord.speicher.einstellungen,
                "korrekturen": coord.speicher.data["pill_korrektur"],
                "brautag": coord.speicher.data.get("brautag"),
                "fass_lernen": _lernen(coord),
                "letzter_scan": coord.fasskeller.letzter_scan,
                "geplant": [_sud(s) for s in snap.geplant],
                "gaerend": [_sud(s) for s in snap.gaerend],
                "abgefuellt": [_sud(s) for s in snap.abgefuellt],
            }
        )
    connection.send_result(msg["id"], {"entries": result})


def _entity_ids(hass: HomeAssistant, entry_id: str) -> dict[str, str | None]:
    reg = er.async_get(hass)
    lookup = {
        "button": ("button", "log_now"),
        "letzter_eintrag": ("sensor", "letzter_eintrag"),
        "uebersicht": ("sensor", "uebersicht"),
    }
    return {
        key: reg.async_get_entity_id(domain, DOMAIN, f"{entry_id}_{suffix}")
        for key, (domain, suffix) in lookup.items()
    }


@_ws_handler({vol.Required("type"): "brauhelfer/braudaten", vol.Required("sud_id"): int})
async def ws_braudaten(hass, coord, msg):
    return await hass.async_add_executor_job(db.get_braudaten, coord.path, msg["sud_id"])


@_ws_handler({
    vol.Required("type"): "brauhelfer/braudaten_speichern",
    vol.Required("sud_id"): int,
    vol.Required("werte"): {vol.In(list(db.BRAUDATEN_FELDER)): vol.Coerce(float)},
    vol.Optional("braudatum"): vol.Any(None, str),
    vol.Optional("bemerkung"): vol.Any(None, str),
    vol.Optional("gebraut", default=False): bool,
})
async def ws_braudaten_speichern(hass, coord, msg):
    braudatum = None
    if msg.get("braudatum"):
        try:
            braudatum = datetime.fromisoformat(msg["braudatum"]).replace(tzinfo=None, second=0, microsecond=0)
        except ValueError as err:
            raise HomeAssistantError("Braudatum ungültig") from err
    await coord.async_save_braudaten(msg["sud_id"], msg["werte"], braudatum, msg.get("bemerkung"), msg["gebraut"])


@_ws_handler({
    vol.Required("type"): "brauhelfer/aufzeichnung_starten",
    vol.Required("sud_id"): int,
    vol.Required("gravity"): str,
    vol.Optional("temperature"): vol.Any(None, str),
    vol.Optional("name"): str,
})
async def ws_aufzeichnung_starten(hass, coord, msg):
    warnung = await coord.async_start_recording(
        msg["sud_id"], msg["gravity"], msg.get("temperature"), msg.get("name") or msg["gravity"]
    )
    return {"warnung": warnung}


@_ws_handler({vol.Required("type"): "brauhelfer/aufzeichnung_beenden", vol.Required("sud_id"): int})
async def ws_aufzeichnung_beenden(hass, coord, msg):
    await coord.async_stop_recording(msg["sud_id"])


@_ws_handler({vol.Required("type"): "brauhelfer/eintragen", vol.Required("sud_id"): int})
async def ws_eintragen(hass, coord, msg):
    m = await coord.async_log(msg["sud_id"])
    return _messwert(m)


@_ws_handler({
    vol.Required("type"): "brauhelfer/abfuellen",
    vol.Required("sud_id"): int,
    vol.Optional("restextrakt"): vol.Any(None, vol.Coerce(float)),
    vol.Optional("dichte"): vol.Any(None, vol.Coerce(float)),
    vol.Optional("temperatur"): vol.Any(None, vol.Coerce(float)),
})
async def ws_abfuellen(hass, coord, msg):
    sre = msg.get("restextrakt")
    if sre is None and msg.get("dichte") is not None:
        sg = msg["dichte"]
        if not 0.98 <= sg <= 1.15:
            raise HomeAssistantError(f"Dichte {sg} unplausibel (SG zwischen 0,980 und 1,150)")
        sre = db.dichte_to_plato(sg)
    await coord.async_abfuellen(msg["sud_id"], sre, msg.get("temperatur"))


@_ws_handler({vol.Required("type"): "brauhelfer/verbraucht", vol.Required("sud_id"): int})
async def ws_verbraucht(hass, coord, msg):
    await coord.async_verbraucht(msg["sud_id"])


# --------------------------------------------------------------------------
# Version 0.4: Details, Zugaben, Proben, Verkostung, Fässer, Gärschrank,
# Benachrichtigungen, Brautag-Assistent
# --------------------------------------------------------------------------

def _lernen(coord) -> dict[str, Any] | None:
    l = coord.fasskeller.lernen
    if not l:
        return None
    return {"fass_id": l["fass_id"], "glas_l": l["glas_l"], "bis": l["bis"].isoformat()}


async def _schreiben(coord, fn, *args):
    """DB-Schreibzugriff über den Coordinator (Sicherung, Sperre, neu einlesen)."""
    return await coord._async_write(fn, *args)  # noqa: SLF001


def _sre(msg: dict[str, Any]) -> float:
    if msg.get("restextrakt") is not None:
        return float(msg["restextrakt"])
    if msg.get("dichte") is not None:
        sg = float(msg["dichte"])
        if not 0.98 <= sg <= 1.15:
            raise HomeAssistantError(f"Dichte {sg} unplausibel (SG zwischen 0,980 und 1,150)")
        return db.dichte_to_plato(sg)
    raise HomeAssistantError("Restextrakt oder Dichte angeben")


@_ws_handler({vol.Required("type"): "brauhelfer/details", vol.Required("sud_id"): int})
async def ws_details(hass, coord, msg):
    d = await hass.async_add_executor_job(db.get_sud_details, coord.path, msg["sud_id"])
    d["faesser"] = [f for f in coord.speicher.data["faesser"] if f["sud_id"] == msg["sud_id"]]
    d["regelung"] = coord.speicher.regelung(msg["sud_id"])
    d["lager_buchungen"] = coord.speicher.data["lager_buchungen"].get(str(msg["sud_id"]), [])
    return d


@_ws_handler({vol.Required("type"): "brauhelfer/zutat", vol.Required("zutat_id"): int,
              vol.Required("aktion"): vol.In(["zugeben", "entnehmen"])})
async def ws_zutat(hass, coord, msg):
    fn = db.zutat_zugeben if msg["aktion"] == "zugeben" else db.zutat_entnehmen
    await _schreiben(coord, fn, msg["zutat_id"])
    key = ("zugabe:" if msg["aktion"] == "zugeben" else "entnahme:") + str(msg["zutat_id"])
    coord.benachrichtiger.async_zuruecksetzen(key)


@_ws_handler({vol.Required("type"): "brauhelfer/hefe", vol.Required("hefe_id"): int})
async def ws_hefe(hass, coord, msg):
    await _schreiben(coord, db.hefe_zugeben, msg["hefe_id"])


@_ws_handler({vol.Required("type"): "brauhelfer/schnellgaer", vol.Required("sud_id"): int,
              vol.Optional("restextrakt"): vol.Any(None, vol.Coerce(float)),
              vol.Optional("dichte"): vol.Any(None, vol.Coerce(float)),
              vol.Required("temperatur"): vol.Coerce(float)})
async def ws_schnellgaer(hass, coord, msg):
    await _schreiben(coord, db.add_schnellgaer, msg["sud_id"], _sre(msg), msg["temperatur"])


@_ws_handler({vol.Required("type"): "brauhelfer/nachgaer", vol.Required("sud_id"): int,
              vol.Required("druck"): vol.All(vol.Coerce(float), vol.Range(min=-1, max=10)),
              vol.Required("temperatur"): vol.All(vol.Coerce(float), vol.Range(min=-5, max=40))})
async def ws_nachgaer(hass, coord, msg):
    await _schreiben(coord, db.add_nachgaer, msg["sud_id"], msg["druck"], msg["temperatur"])


@_ws_handler({vol.Required("type"): "brauhelfer/bewertung", vol.Required("sud_id"): int,
              vol.Required("werte"): dict})
async def ws_bewertung(hass, coord, msg):
    return {"id": await _schreiben(coord, db.add_bewertung, msg["sud_id"], msg["werte"])}


@_ws_handler({
    vol.Required("type"): "brauhelfer/fass",
    vol.Required("aktion"): vol.In(["anlegen", "bearbeiten", "loeschen", "wiegen", "glas"]),
    vol.Optional("fass_id"): str,
    vol.Optional("sud_id"): int,
    vol.Optional("name"): str,
    vol.Optional("tara_kg"): vol.Any(None, vol.Coerce(float)),
    vol.Optional("inhalt_l"): vol.Any(None, vol.Coerce(float)),
    vol.Optional("rest_l"): vol.Any(None, vol.Coerce(float)),
    vol.Optional("waage"): vol.Any(None, str),
    vol.Optional("brutto_kg"): vol.Any(None, vol.Coerce(float)),
    vol.Optional("liter"): vol.Any(None, vol.Coerce(float)),
})
async def ws_fass(hass, coord, msg):
    k = coord.fasskeller
    a = msg["aktion"]
    if a == "anlegen":
        f = k.anlegen(msg["sud_id"], msg.get("name", "Fass"), msg.get("tara_kg") or 0.0, msg.get("inhalt_l") or 0.0, msg.get("waage"))
    elif a == "bearbeiten":
        k.bearbeiten(msg["fass_id"], name=msg.get("name"), tara_kg=msg.get("tara_kg"), waage=msg.get("waage"), rest_l=msg.get("rest_l"))
        f = coord.speicher.fass(msg["fass_id"])
    elif a == "loeschen":
        k.loeschen(msg["fass_id"])
        return {}
    elif a == "wiegen":
        f = k.wiegen(msg["fass_id"], msg.get("brutto_kg"))
    else:
        f = k.glas(msg["fass_id"], msg.get("liter") or 0.5, "Von Hand")
    if a in ("wiegen", "glas") and f.get("leer"):
        await k._leer_melden(f)  # noqa: SLF001
    return {"fass": f}


@_ws_handler({
    vol.Required("type"): "brauhelfer/tag",
    vol.Required("aktion"): vol.In(["zuordnen", "entfernen", "lernen", "lernen_abbrechen"]),
    vol.Optional("fass_id"): str, vol.Optional("tag_id"): str,
    vol.Optional("glas_l"): vol.Coerce(float), vol.Optional("name"): str,
})
async def ws_tag(hass, coord, msg):
    k = coord.fasskeller
    a = msg["aktion"]
    if a == "zuordnen":
        k.tag_zuordnen(msg["fass_id"], msg["tag_id"], msg.get("glas_l", 0.5), msg.get("name", ""))
    elif a == "entfernen":
        k.tag_entfernen(msg["tag_id"])
    elif a == "lernen":
        k.lernen_starten(msg["fass_id"], msg.get("glas_l", 0.5), msg.get("name", ""))
    else:
        k.lernen = None


SCHRANK_SCHEMA = vol.Schema({
    vol.Optional("id"): str,
    vol.Required("name"): vol.All(str, vol.Length(min=1)),
    vol.Optional("temp_sensor"): vol.Any(None, str),
    vol.Optional("kuehlung"): vol.Any(None, str),
    vol.Optional("heizung"): vol.Any(None, str),
    vol.Optional("hysterese", default=0.5): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=5)),
    vol.Optional("min_pause_min", default=5): vol.All(vol.Coerce(float), vol.Range(min=0, max=60)),
}, extra=vol.REMOVE_EXTRA)


@_ws_handler({vol.Required("type"): "brauhelfer/schrank", vol.Required("aktion"): vol.In(["speichern", "loeschen"]),
              vol.Optional("schrank"): dict, vol.Optional("schrank_id"): str})
async def ws_schrank(hass, coord, msg):
    from .speicher import neue_id  # noqa: PLC0415

    liste = coord.speicher.data["schraenke"]
    if msg["aktion"] == "loeschen":
        alt = coord.speicher.schrank(msg["schrank_id"])
        if alt:
            for ent in (alt.get("kuehlung"), alt.get("heizung")):
                if ent:
                    await coord.regler._schalten(ent, False)  # noqa: SLF001
        coord.speicher.data["schraenke"] = [x for x in liste if x["id"] != msg["schrank_id"]]
        for r in coord.speicher.data["regelung"].values():
            if r.get("schrank_id") == msg["schrank_id"]:
                r["schrank_id"] = None
    else:
        try:
            sch = SCHRANK_SCHEMA(msg.get("schrank") or {})
        except vol.Invalid as err:
            raise HomeAssistantError(f"Gärschrank: {err}") from err
        if not sch.get("kuehlung") and not sch.get("heizung"):
            raise HomeAssistantError("Mindestens Kühlung oder Heizung auswählen")
        if sch.get("kuehlung") and sch.get("kuehlung") == sch.get("heizung"):
            raise HomeAssistantError("Kühlung und Heizung müssen verschiedene Steckdosen sein")
        if sch.get("id") and coord.speicher.schrank(sch["id"]):
            coord.speicher.schrank(sch["id"]).update(sch)
        else:
            sch["id"] = neue_id()
            liste.append(sch)
    coord.speicher.speichern()
    coord.async_update_listeners()
    await coord.regler.async_jetzt()


@_ws_handler({vol.Required("type"): "brauhelfer/regelung", vol.Required("sud_id"): int,
              vol.Optional("schrank_id"): vol.Any(None, str),
              vol.Optional("profil"): [{vol.Required("ab_vg"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
                                        vol.Required("soll"): vol.All(vol.Coerce(float), vol.Range(min=-2, max=40))}],
              vol.Optional("aktiv"): bool})
async def ws_regelung(hass, coord, msg):
    sid = str(msg["sud_id"])
    reg = coord.speicher.data["regelung"]
    if msg.get("schrank_id") is None and "schrank_id" in msg:
        reg.pop(sid, None)
    else:
        r = reg.setdefault(sid, {"aktiv": True, "profil": [{"ab_vg": 0, "soll": 18}]})
        if msg.get("schrank_id"):
            if not coord.speicher.schrank(msg["schrank_id"]):
                raise HomeAssistantError("Gärschrank nicht gefunden")
            for other_sid, other in reg.items():
                if other_sid != sid and other.get("schrank_id") == msg["schrank_id"]:
                    sud = coord.data.sude.get(int(other_sid)) if coord.data else None
                    if sud and sud.status == db.STATUS_GEBRAUT:
                        raise HomeAssistantError(f"Dieser Gärschrank regelt schon „{sud.name}“")
            r["schrank_id"] = msg["schrank_id"]
        if "profil" in msg:
            if not msg["profil"]:
                raise HomeAssistantError("Mindestens eine Temperaturstufe angeben")
            r["profil"] = sorted(msg["profil"], key=lambda x: x["ab_vg"])
        if "aktiv" in msg:
            r["aktiv"] = msg["aktiv"]
    coord.speicher.speichern()
    coord.async_update_listeners()
    await coord.regler.async_jetzt()


@_ws_handler({vol.Required("type"): "brauhelfer/einstellungen", vol.Optional("benachrichtigung"): dict,
              vol.Optional("einstellungen"): dict})
async def ws_einstellungen(hass, coord, msg):
    e = msg.get("einstellungen") or {}
    if "lager" in e:
        coord.speicher.einstellungen["lager"] = bool(e["lager"])
    if "einkaufsliste" in e:
        coord.speicher.einstellungen["einkaufsliste"] = e["einkaufsliste"] or None
    if "glaettung_min" in e:
        coord.speicher.einstellungen["glaettung_min"] = max(0, min(240, int(e["glaettung_min"] or 0)))
    neu = msg.get("benachrichtigung") or {}
    cfg = coord.speicher.benachrichtigung
    for k in ("ziele", "lautsprecher"):
        if k in neu:
            cfg[k] = [str(x) for x in neu[k]]
    if "tts" in neu:
        cfg["tts"] = str(neu["tts"]) if neu["tts"] else None
    if "lautstaerke" in neu:
        cfg["lautstaerke"] = max(5, min(100, int(neu["lautstaerke"]))) if neu["lautstaerke"] else None
    for k, (lo, hi) in {"stagnation_h": (6, 240), "stagnation_plato": (0.05, 2), "temp_toleranz": (0.3, 10),
                        "temp_dauer_min": (5, 240), "akku_prozent": (1, 90), "fass_rest_l": (0, 50)}.items():
        if k in neu and neu[k] is not None:
            cfg[k] = max(lo, min(hi, float(neu[k])))
    if isinstance(neu.get("ereignisse"), dict):
        for k, v in neu["ereignisse"].items():
            if k in cfg["ereignisse"]:
                cfg["ereignisse"][k] = bool(v)
    coord.speicher.speichern()


@_ws_handler({vol.Required("type"): "brauhelfer/test_meldung", vol.Optional("ansage"): bool})
async def ws_test_meldung(hass, coord, msg):
    if msg.get("ansage"):
        if not coord.speicher.benachrichtigung["lautsprecher"]:
            raise HomeAssistantError("Erst einen Lautsprecher auswählen")
        await coord.benachrichtiger.async_ansagen("Hallo vom Brauhelfer. So klingen die Ansagen am Brautag.")
        return
    await coord.benachrichtiger.async_senden(
        "Brauhelfer", "Testmeldung: So sehen Meldungen vom Brauhelfer aus.",
        ereignis="test", ansage=bool(msg.get("ansage")),
    )


PLATTFORMEN = {"sonos": "Sonos", "music_assistant": "Music Assistant", "cast": "Chromecast", "squeezebox": "Squeezebox",
               "snapcast": "Snapcast", "dlna_dmr": "DLNA", "airplay": "AirPlay", "apple_tv": "Apple TV", "mpd": "MPD"}


@_ws_handler({vol.Required("type"): "brauhelfer/auswahl"})
async def ws_auswahl(hass, coord, msg):
    """Entitäten für die Auswahlmenüs."""
    from .benachrichtigung import kann_ankuendigen, notify_dienste  # noqa: PLC0415

    def name(st) -> str:
        return st.attributes.get("friendly_name") or st.entity_id

    from homeassistant.helpers import entity_registry as er  # noqa: PLC0415

    ent_reg = er.async_get(hass)
    schalter, temperatur, waage, todo, lautsprecher, tts = [], [], [], [], [], []
    for st in hass.states.async_all():
        dom = st.domain
        if dom == "todo":
            todo.append({"id": st.entity_id, "name": name(st)})
        elif dom == "media_player":
            reg = ent_reg.async_get(st.entity_id)
            quelle = PLATTFORMEN.get(reg.platform, reg.platform.replace("_", " ").title()) if reg else ""
            lautsprecher.append({"id": st.entity_id, "name": name(st), "quelle": quelle,
                                 "ankuendigen": kann_ankuendigen(hass, st.entity_id)})
        elif dom == "tts":
            tts.append({"id": st.entity_id, "name": name(st)})
        if dom in ("switch", "input_boolean", "light"):
            schalter.append({"id": st.entity_id, "name": name(st)})
        elif dom == "sensor":
            dc = st.attributes.get("device_class")
            unit = (st.attributes.get("unit_of_measurement") or "").lower()
            if dc == "temperature" or unit in ("°c", "°f"):
                temperatur.append({"id": st.entity_id, "name": name(st)})
            elif dc == "weight" or unit in ("kg", "g"):
                waage.append({"id": st.entity_id, "name": name(st)})
    key = lambda x: x["name"].lower()  # noqa: E731
    return {
        "schalter": sorted(schalter, key=key),
        "temperatur": sorted(temperatur, key=key),
        "waage": sorted(waage, key=key),
        "notify": notify_dienste(hass),
        "todo": sorted(todo, key=key),
        "lautsprecher": sorted(lautsprecher, key=key),
        "tts": sorted(tts, key=key),
    }


@_ws_handler({vol.Required("type"): "brauhelfer/brautag", vol.Required("sud_id"): int})
async def ws_brautag(hass, coord, msg):
    from .brautag import schritte  # noqa: PLC0415

    d = await hass.async_add_executor_job(db.get_sud_details, coord.path, msg["sud_id"])
    if d["status"] != db.STATUS_REZEPT:
        raise HomeAssistantError("Der Brautag-Assistent geht nur für geplante Sude")
    sitzung = coord.brautag.starten(msg["sud_id"])
    braudaten = await hass.async_add_executor_job(db.get_braudaten, coord.path, msg["sud_id"])
    return {"sitzung": sitzung, "schritte": schritte(d), "braudaten": braudaten, "hefe": d["hefe"]}


@_ws_handler({vol.Required("type"): "brauhelfer/brautag_aktion",
              vol.Required("aktion"): vol.In(["schritt", "timer_starten", "timer_stoppen", "beenden"]),
              vol.Optional("schritt"): str, vol.Optional("minuten"): vol.Coerce(float)})
async def ws_brautag_aktion(hass, coord, msg):
    from .brautag import schritte  # noqa: PLC0415

    bt = coord.brautag
    a = msg["aktion"]
    if a == "schritt":
        bt.schritt(msg["schritt"])
    elif a == "timer_starten":
        s = bt.sitzung
        if not s:
            raise HomeAssistantError("Kein Brautag aktiv")
        d = await hass.async_add_executor_job(db.get_sud_details, coord.path, s["sud_id"])
        step = next((x for x in schritte(d) if x["key"] == msg["schritt"]), None)
        if step is None:
            raise HomeAssistantError("Schritt nicht gefunden")
        minuten = msg.get("minuten") or step.get("timer_min")
        if not minuten:
            raise HomeAssistantError("Dieser Schritt hat keinen Timer")
        bt.timer_starten(step["key"], minuten, step["titel"], step.get("timer_text", f"{step['titel']} fertig."), step.get("ereignisse"))
    elif a == "timer_stoppen":
        bt.timer_stoppen()
    else:
        bt.beenden()
    return {"sitzung": bt.sitzung}


# --------------------------------------------------------------------------
# Lager
# --------------------------------------------------------------------------

POSTEN_SCHEMA = vol.Schema([{
    vol.Required("typ"): vol.In(list(db.LAGER_TABELLE)),
    vol.Required("name"): str,
    vol.Required("menge"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100000)),
}], extra=vol.REMOVE_EXTRA)


@_ws_handler({vol.Required("type"): "brauhelfer/lager_bedarf", vol.Optional("sud_id"): int,
              vol.Optional("art"): vol.In(["zutat", "hefe"]), vol.Optional("item_id"): int})
async def ws_lager_bedarf(hass, coord, msg):
    if msg.get("art"):
        posten = await hass.async_add_executor_job(db.lager_bedarf_zugabe, coord.path, msg["art"], msg["item_id"])
    else:
        posten = await hass.async_add_executor_job(db.lager_bedarf, coord.path, msg["sud_id"])
    bisher = coord.speicher.data["lager_buchungen"].get(str(msg.get("sud_id")), []) if msg.get("sud_id") else []
    return {"posten": posten, "schon_gebucht": [b for b in bisher if b.get("anlass") == "brautag"]}


@_ws_handler({vol.Required("type"): "brauhelfer/lager_abziehen", vol.Required("sud_id"): int,
              vol.Required("anlass"): str, vol.Required("posten"): list, vol.Optional("zurueck", default=False): bool})
async def ws_lager_abziehen(hass, coord, msg):
    from homeassistant.util import dt as dt_util  # noqa: PLC0415

    try:
        posten = POSTEN_SCHEMA(msg["posten"])
    except vol.Invalid as err:
        raise HomeAssistantError(f"Ungültige Posten: {err}") from err
    gebucht = await _schreiben(coord, db.lager_abziehen, posten, msg["zurueck"])
    if gebucht:
        coord.speicher.data["lager_buchungen"].setdefault(str(msg["sud_id"]), []).append({
            "zeit": dt_util.now().isoformat(), "anlass": msg["anlass"], "zurueck": msg["zurueck"],
            "posten": [{"typ": g["typ"], "name": g["name"], "menge": g["menge"]} for g in gebucht],
        })
        coord.speicher.speichern()
    return {"gebucht": gebucht}


@_ws_handler({vol.Required("type"): "brauhelfer/einkaufsliste", vol.Required("sud_id"): int})
async def ws_einkaufsliste(hass, coord, msg):
    ziel = coord.speicher.einstellungen.get("einkaufsliste")
    if not ziel:
        ziele = [st.entity_id for st in hass.states.async_all("todo")]
        ziel = "todo.shopping_list" if "todo.shopping_list" in ziele else (ziele[0] if len(ziele) == 1 else None)
    if not ziel or hass.states.get(ziel) is None:
        raise HomeAssistantError("Keine Einkaufsliste gewählt. In den Brauhelfer-Einstellungen eine To-do-Liste auswählen.")
    sud = coord.data.sude.get(msg["sud_id"]) if coord.data else None
    if sud is None or not sud.lager_fehlt:
        raise HomeAssistantError("Für diesen Sud fehlt nichts im Lager")

    def menge(p: dict) -> str:
        if not p["gefunden"]:
            return ""
        v = p["fehlt"]
        text = f"{v:.2f}".rstrip("0").rstrip(".") if p["einheit"] == "kg" else f"{v:.0f}"
        return f"{text.replace('.', ',')} {p['einheit']} "

    vorhanden = set()
    try:
        r = await hass.services.async_call("todo", "get_items", {"entity_id": ziel}, blocking=True, return_response=True)
        vorhanden = {i["summary"] for i in (r or {}).get(ziel, {}).get("items", []) if i.get("status") == "needs_action"}
    except Exception:  # noqa: BLE001
        pass
    neu = 0
    for p in sud.lager_fehlt:
        text = f"{menge(p)}{p['name']}".strip()
        if text in vorhanden:
            continue
        await hass.services.async_call("todo", "add_item", {
            "entity_id": ziel, "item": text, "description": f"Für {sud.name} (Brauhelfer)",
        }, blocking=True)
        neu += 1
    return {"neu": neu, "liste": ziel}


@_ws_handler({
    vol.Required("type"): "brauhelfer/pill_abgleich",
    vol.Required("sud_id"): int,
    vol.Optional("restextrakt"): vol.Any(None, vol.Coerce(float)),
    vol.Optional("dichte"): vol.Any(None, vol.Coerce(float)),
    vol.Optional("temperatur"): vol.Any(None, vol.Coerce(float)),
    vol.Optional("eintragen", default=True): bool,
    vol.Optional("zuruecksetzen", default=False): bool,
    vol.Optional("referenz"): vol.Any(None, str),
})
async def ws_pill_abgleich(hass, coord, msg):
    """Pill mit einer Referenzmessung (Spindel/Refraktometer) abgleichen."""
    a = coord.aufzeichnungen.get(msg["sud_id"])
    if a is None:
        raise HomeAssistantError("Für diesen Sud läuft keine Aufzeichnung")
    korr = coord.speicher.data["pill_korrektur"]
    if msg["zuruecksetzen"]:
        korr.pop(a.gravity, None)
        if a.temperature:
            korr.pop(a.temperature, None)
        coord.speicher.speichern()
        coord.async_update_listeners()
        return {"dichte": 0.0, "temperatur": 0.0}
    ref = msg.get("restextrakt")
    if ref is None and msg.get("dichte") is not None:
        sg = msg["dichte"]
        if not 0.98 <= sg <= 1.15:
            raise HomeAssistantError(f"Dichte {sg} unplausibel (SG zwischen 0,980 und 1,150)")
        ref = db.dichte_to_plato(sg)
    if ref is None and msg.get("temperatur") is None:
        raise HomeAssistantError("Bitte einen Referenzwert eintragen")
    jetzt = dt_util.now().isoformat()
    out: dict[str, float | None] = {"dichte": None, "temperatur": None}
    if ref is not None:
        if not -5 <= ref <= 35:
            raise HomeAssistantError(f"Restextrakt {ref:.2f} °P unplausibel")
        roh = await coord.async_geglaettet(a.gravity, msg["sud_id"], lambda e, s: coord.read_gravity(e, s, roh=True))
        wert = round(ref - roh, 3)
        if abs(wert) > 3:
            raise HomeAssistantError(f"Die Pill weicht um {wert:+.1f} °P ab. Das ist mehr als ein Abgleich ausgleichen sollte – Messung prüfen")
        korr[a.gravity] = {"wert": wert, "datum": jetzt, "referenz": msg.get("referenz") or None}
        out["dichte"] = wert
    if msg.get("temperatur") is not None and a.temperature:
        roh_t = coord.read_temperature(a.temperature, msg["sud_id"], roh=True)
        wert_t = round(msg["temperatur"] - roh_t, 2)
        if abs(wert_t) > 5:
            raise HomeAssistantError(f"Die Temperatur weicht um {wert_t:+.1f} °C ab – Messung prüfen")
        korr[a.temperature] = {"wert": wert_t, "datum": jetzt, "referenz": msg.get("referenz") or None}
        out["temperatur"] = wert_t
    coord.speicher.speichern()
    if ref is not None and msg["eintragen"]:
        temp = msg.get("temperatur")
        if temp is None:
            try:
                temp = coord.read_temperature(a.temperature, msg["sud_id"]) if a.temperature else None
            except HomeAssistantError:
                temp = None
        sud = coord.data.sude.get(msg["sud_id"]) if coord.data else None
        if temp is None:
            temp = sud.letzter_messwert.temp if sud and sud.letzter_messwert else 18.0
        art = msg.get("referenz") or "Referenz"
        await coord.async_add_messwert(msg["sud_id"], ref, temp, f"{art} (Pill-Abgleich)")
    coord.async_update_listeners()
    return out
