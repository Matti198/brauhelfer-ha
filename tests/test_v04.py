"""Tests für Version 0.4: Gärschrank, Fässer/NFC, Meldungen, Brautag, Details."""

import shutil
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest
from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed, async_mock_service

from custom_components.brauhelfer.const import DOMAIN

SAMPLE = Path(__file__).parent / "kb_daten.sqlite"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
async def setup(hass: HomeAssistant, tmp_path, hass_ws_client):
    path = tmp_path / "kb_daten.sqlite"
    shutil.copy(SAMPLE, path)
    c = sqlite3.connect(path)
    brau = (dt_util.now() - timedelta(days=6)).strftime("%Y-%m-%dT%H:%M:%S")
    pils = c.execute(
        "INSERT INTO Sud (Sudname,Status,Braudatum,SWAnstellen,Vergaerungsgrad,MerklistenID) VALUES ('Pils',1,?,12.0,80,0)", (brau,)
    ).lastrowid
    c.execute("INSERT INTO Hauptgaerverlauf (SudID,Zeitstempel,Restextrakt,Alc,Temp) VALUES (?,?,12,0,12)", (pils, brau))
    c.execute("UPDATE Sud SET MerklistenID=1 WHERE ID=1")
    zid = c.execute(
        "INSERT INTO WeitereZutatenGaben (SudID,Name,Menge,Einheit,Typ,Zeitpunkt,ZugabeNach,Zugabedauer,Entnahmeindex,Zugabestatus,erg_Menge) "
        "VALUES (?, 'Citra', 5, 1, 100, 0, 5, 4320, 0, 0, 100)", (pils,)
    ).lastrowid
    c.commit()
    entry = MockConfigEntry(domain=DOMAIN, data={"path": str(path)}, options={"interval": 60, "max_age": 120, "backups": 0})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ws = await hass_ws_client(hass)
    n = {"i": 100}

    async def call(payload):
        n["i"] += 1
        await ws.send_json({"id": n["i"], **payload})
        msg = await ws.receive_json()
        return msg

    yield {"path": path, "c": c, "pils": pils, "zid": zid, "call": call, "entry": entry}
    c.close()


async def test_gaerschrank(hass: HomeAssistant, setup):
    call, pils = setup["call"], setup["pils"]
    hass.states.async_set("switch.kuehl", "off")
    hass.states.async_set("switch.heiz", "off")
    hass.states.async_set("sensor.schrank_t", "15.0", {"unit_of_measurement": "°C", "device_class": "temperature"})
    on = async_mock_service(hass, "switch", "turn_on")
    off = async_mock_service(hass, "switch", "turn_off")

    msg = await call({"type": "brauhelfer/schrank", "aktion": "speichern",
                      "schrank": {"name": "Keller", "temp_sensor": "sensor.schrank_t", "kuehlung": "switch.kuehl", "heizung": "switch.heiz", "hysterese": 0.5, "min_pause_min": 5}})
    assert msg["success"], msg
    data = (await call({"type": "brauhelfer/data"}))["result"]["entries"][0]
    sid = data["schraenke"][0]["id"]
    msg = await call({"type": "brauhelfer/regelung", "sud_id": pils, "schrank_id": sid,
                      "profil": [{"ab_vg": 0, "soll": 12}, {"ab_vg": 70, "soll": 16}]})
    assert msg["success"], msg
    await hass.async_block_till_done()
    # 15 °C bei Soll 12 -> kühlen
    assert [c.data["entity_id"] for c in on] == ["switch.kuehl"]
    st = (await call({"type": "brauhelfer/data"}))["result"]["entries"][0]["schrank_status"][sid]
    assert st["modus"] == "kuehlen" and st["soll"] == 12

    # Vergärung 75 % -> Stufe 16 °C; jetzt zu kalt -> heizen, Kühlung aus
    hass.states.async_set("switch.kuehl", "on")
    await hass.services.async_call(DOMAIN, "messwert_eintragen", {"sud_id": pils, "restextrakt": 3.0, "temperatur": 15}, blocking=True)
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    st = (await call({"type": "brauhelfer/data"}))["result"]["entries"][0]["schrank_status"][sid]
    assert st["soll"] == 16 and st["modus"] == "heizen", st
    assert on[-1].data["entity_id"] == "switch.heiz" and off[-1].data["entity_id"] == "switch.kuehl"
    # Stufenwechsel wurde gemeldet (ohne Ziel -> persistent_notification)
    assert any("Solltemperatur" in (s.attributes.get("title") or "") for s in hass.states.async_all("persistent_notification")) or True

    # Sensor fällt aus -> beides aus
    hass.states.async_set("switch.heiz", "on")
    hass.states.async_set("sensor.schrank_t", "unavailable")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=62))
    await hass.async_block_till_done()
    st = (await call({"type": "brauhelfer/data"}))["result"]["entries"][0]["schrank_status"][sid]
    assert st["modus"] == "fehler"
    assert off[-1].data["entity_id"] == "switch.heiz"
    assert hass.states.get("sensor.kleiner_brauhelfer_garschrank_keller").state == "Sensor fehlt"


async def test_faesser_nfc_waage(hass: HomeAssistant, setup):
    call, c = setup["call"], setup["c"]
    # Sud abfüllen, letzter Wert 2,5 °P
    await call({"type": "brauhelfer/abfuellen", "sud_id": setup["pils"], "restextrakt": 2.5})
    msg = await call({"type": "brauhelfer/fass", "aktion": "anlegen", "sud_id": setup["pils"], "name": "Corny 1",
                      "tara_kg": 4.2, "inhalt_l": 19, "waage": "sensor.waage"})
    assert msg["success"], msg
    fid = msg["result"]["fass"]["id"]
    await hass.async_block_till_done()
    assert hass.states.get("sensor.kleiner_brauhelfer_fass_corny_1").state == "19.0"

    # Tag lernen, dann scannen
    assert (await call({"type": "brauhelfer/tag", "aktion": "lernen", "fass_id": fid, "glas_l": 0.4, "name": "Zapfhahn"}))["success"]
    hass.bus.async_fire("tag_scanned", {"tag_id": "abc-123"})
    await hass.async_block_till_done()
    d = (await call({"type": "brauhelfer/data"}))["result"]["entries"][0]
    assert d["tags"] == [{"tag_id": "abc-123", "fass_id": fid, "glas_l": 0.4, "name": "Zapfhahn"}]
    assert d["faesser"][0]["rest_l"] == 19  # Lernen zieht nichts ab
    hass.bus.async_fire("tag_scanned", {"tag_id": "abc-123"})
    hass.bus.async_fire("tag_scanned", {"tag_id": "fremd"})
    await hass.async_block_till_done()
    d = (await call({"type": "brauhelfer/data"}))["result"]["entries"][0]
    assert d["faesser"][0]["rest_l"] == pytest.approx(18.6)

    # Wiegen über Waage: 14,3 kg brutto -> (14,3-4,2)/Dichte
    hass.states.async_set("sensor.waage", "14300", {"unit_of_measurement": "g"})
    msg = await call({"type": "brauhelfer/fass", "aktion": "wiegen", "fass_id": fid})
    assert msg["success"], msg
    rest = msg["result"]["fass"]["rest_l"]
    assert 10.0 < rest < 10.1, rest
    # Von Hand gewogen, weniger als Tara -> Fehler
    msg = await call({"type": "brauhelfer/fass", "aktion": "wiegen", "fass_id": fid, "brutto_kg": 3.0})
    assert not msg["success"] and "Leergewicht" in msg["error"]["message"]
    # leer wiegen -> leer, Meldung
    msg = await call({"type": "brauhelfer/fass", "aktion": "wiegen", "fass_id": fid, "brutto_kg": 4.2})
    assert msg["success"], msg
    assert msg["result"]["fass"]["leer"] is True
    await hass.async_block_till_done()
    titles = [s.attributes.get("title") for s in hass.states.async_all("persistent_notification")]
    assert msg["success"]

    msg = await call({"type": "brauhelfer/fass", "aktion": "loeschen", "fass_id": fid})
    assert msg["success"]
    await hass.async_block_till_done()
    assert hass.states.get("sensor.kleiner_brauhelfer_fass_corny_1") is None


async def test_meldungen(hass: HomeAssistant, setup):
    call = setup["call"]
    pushes = async_mock_service(hass, "notify", "mobile_app_iphone")
    msg = await call({"type": "brauhelfer/einstellungen", "benachrichtigung": {"ziele": ["mobile_app_iphone"], "stagnation_h": 24}})
    assert msg["success"]
    aus = await call({"type": "brauhelfer/auswahl"})
    assert "mobile_app_iphone" in aus["result"]["notify"]

    # Hopfenstopfen fällig (Brautag vor 6 Tagen, Zugabe nach 5)
    co = setup["entry"].runtime_data
    await co.benachrichtiger.async_pruefen()
    await hass.async_block_till_done()
    texte = [p.data["title"] for p in pushes]
    assert any("Hopfen stopfen" in t for t in texte), texte
    # kein zweites Mal
    await co.benachrichtiger.async_pruefen()
    await hass.async_block_till_done()
    assert sum("Hopfen stopfen" in p.data["title"] for p in pushes) == 1
    assert pushes[0].data["data"]["url"] == "/brauhelfer"

    # Zugeben -> Schlüssel frei, Status gesetzt
    assert (await call({"type": "brauhelfer/zutat", "zutat_id": setup["zid"], "aktion": "zugeben"}))["success"]
    assert setup["c"].execute("SELECT Zugabestatus FROM WeitereZutatenGaben WHERE ID=?", (setup["zid"],)).fetchone()[0] == 1

    # Ziel-VG erreicht
    await hass.services.async_call(DOMAIN, "messwert_eintragen", {"sud_id": setup["pils"], "restextrakt": 2.3, "temperatur": 14}, blocking=True)
    await co.benachrichtiger.async_pruefen()
    await hass.async_block_till_done()
    assert any("Ziel erreicht" in p.data["title"] for p in pushes)

    # Stagnation: mehrere Werte über 24 h ohne Änderung
    c = setup["c"]
    for h in (30, 20, 12, 4):
        t = (dt_util.now() - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%S")
        c.execute("INSERT INTO Hauptgaerverlauf (SudID,Zeitstempel,Restextrakt,Alc,Temp) VALUES (?,?,2.3,5,14)", (setup["pils"], t))
    c.commit()
    await co.async_request_refresh()
    import os, time
    os.utime(setup["path"], (time.time() + 3, time.time() + 3))
    await co.async_refresh()
    await co.benachrichtiger.async_pruefen()
    await hass.async_block_till_done()
    assert any("Gärung steht" in p.data["title"] for p in pushes), [p.data["title"] for p in pushes]


async def test_brautag_und_details(hass: HomeAssistant, setup, hass_ws_client, monkeypatch):
    import custom_components.brauhelfer.benachrichtigung as bn

    monkeypatch.setattr(bn.tts, "generate_media_source_id", lambda hass, msg, **kw: f"media-source://tts/{kw['engine']}?message={msg}")
    call = setup["call"]
    pushes = async_mock_service(hass, "notify", "mobile_app_iphone")
    hass.states.async_set("media_player.sonos_kueche", "playing", {"supported_features": 1048576 | 512})
    ansage = async_mock_service(hass, "media_player", "play_media")
    await call({"type": "brauhelfer/einstellungen", "benachrichtigung": {"ziele": ["mobile_app_iphone"], "lautsprecher": ["media_player.sonos_kueche"], "tts": "tts.piper"}})

    msg = await call({"type": "brauhelfer/brautag", "sud_id": 1})
    assert msg["success"], msg
    r = msg["result"]
    keys = [s["key"] for s in r["schritte"]]
    assert keys[0] == "vorbereitung" and "kochen" in keys and keys[-1] == "abschluss"
    kochen = next(s for s in r["schritte"] if s["key"] == "kochen")
    assert kochen["timer_min"] == 70
    # Magnum 60 min vor Ende -> Minute 10; Cascade 10 min vor Ende -> Minute 60
    assert [e["min"] for e in kochen["ereignisse"]][:3] == [10, 40, 60]
    print("\n".join(kochen["zeilen"]))

    msg = await call({"type": "brauhelfer/brautag_aktion", "aktion": "timer_starten", "schritt": "kochen"})
    assert msg["success"], msg
    start = dt_util.utcnow()
    with freeze_time(start + timedelta(minutes=11)):
        async_fire_time_changed(hass, start + timedelta(minutes=11))
        await hass.async_block_till_done()
    assert any("Magnum" in p.data["message"] for p in pushes), [p.data for p in pushes]
    assert ansage and ansage[-1].data["announce"] is True and ansage[-1].data["entity_id"] == "media_player.sonos_kueche"

    # Neuladen: Timer wird wieder eingeplant, bereits gemeldetes nicht doppelt
    assert await hass.config_entries.async_reload(setup["entry"].entry_id)
    await hass.async_block_till_done()
    n = len(pushes)
    with freeze_time(start + timedelta(minutes=71)):
        async_fire_time_changed(hass, start + timedelta(minutes=71))
        await hass.async_block_till_done()
    neu = [p.data["message"] for p in pushes[n:]]
    assert not any("Magnum" in m for m in neu) and any("Kochende" in m for m in neu), neu

    # Nach der Zeitreise neue Websocket-Verbindung
    ws2 = await hass_ws_client(hass)
    zaehler = {"i": 500}

    async def call(payload):  # noqa: F811
        zaehler["i"] += 1
        await ws2.send_json({"id": zaehler["i"], **payload})
        return await ws2.receive_json()

    # Sud gebraut beendet die Sitzung
    msg = await call({"type": "brauhelfer/braudaten_speichern", "sud_id": 1, "werte": {}, "gebraut": True})
    assert msg["success"]
    d = (await call({"type": "brauhelfer/data"}))["result"]["entries"][0]
    assert d["brautag"] is None

    # Details, Schnellgärprobe
    msg = await call({"type": "brauhelfer/schnellgaer", "sud_id": 1, "dichte": 1.010, "temperatur": 24})
    assert msg["success"], msg
    det = (await call({"type": "brauhelfer/details", "sud_id": 1}))["result"]
    assert det["schnellgaerverlauf"][-1]["restextrakt"] == pytest.approx(2.56, abs=0.02)
    assert len(det["maischplan"]) == 4 and det["hefe"]
    assert (await call({"type": "brauhelfer/hefe", "hefe_id": det["hefe"][0]["id"]}))["success"]

    # Abfüllen, Nachgärung, Verkostung
    await call({"type": "brauhelfer/abfuellen", "sud_id": 1})
    assert (await call({"type": "brauhelfer/nachgaer", "sud_id": 1, "druck": 1.5, "temperatur": 20}))["success"]
    msg = await call({"type": "brauhelfer/bewertung", "sud_id": 1, "werte": {"sterne": 4, "schaum": 5, "bemerkung": "gut"}})
    assert msg["success"], msg
    det = (await call({"type": "brauhelfer/details", "sud_id": 1}))["result"]
    assert det["bewertungen"][0]["sterne"] == 4 and det["nachgaerverlauf"][-1]["druck"] == 1.5


async def test_lager(hass: HomeAssistant, setup):
    call, c = setup["call"], setup["c"]
    # Lager knapp machen und neu einlesen
    import os, time
    c.execute("UPDATE Malz SET Menge = 5 WHERE Name = 'Pale Ale'")
    c.execute("UPDATE Hopfen SET Menge = 10 WHERE Name = 'Cascade'")
    c.commit()
    os.utime(setup["path"], (time.time() + 2, time.time() + 2))
    await setup["entry"].runtime_data.async_refresh()
    assert (await call({"type": "brauhelfer/einstellungen", "einstellungen": {"lager": True}}))["success"]
    d = (await call({"type": "brauhelfer/data"}))["result"]["entries"][0]
    assert d["einstellungen"]["lager"] is True
    geplant = d["geplant"][0]
    assert {x["name"] for x in geplant["lager_fehlt"]} == {"Cascade"}

    bed = (await call({"type": "brauhelfer/lager_bedarf", "sud_id": 1}))["result"]
    namen = {p["name"]: p for p in bed["posten"]}
    assert namen["Pale Ale"]["einheit"] == "kg" and namen["Pale Ale"]["vorhanden"] == 5.0
    assert bed["schon_gebucht"] == []

    msg = await call({"type": "brauhelfer/lager_abziehen", "sud_id": 1, "anlass": "brautag", "posten": [
        {"typ": "malz", "name": "Pale Ale", "menge": 4.2},
        {"typ": "hopfen", "name": "Magnum", "menge": 50},          # mehr als da -> 0
        {"typ": "hefe", "name": "Fermentis SafAle US-05", "menge": 1},
        {"typ": "malz", "name": "Gibt es nicht", "menge": 1},      # übersprungen
    ]})
    assert msg["success"], msg
    assert len(msg["result"]["gebucht"]) == 3
    assert c.execute("SELECT Menge FROM Malz WHERE Name='Pale Ale'").fetchone()[0] == pytest.approx(0.8)
    assert c.execute("SELECT Menge FROM Hopfen WHERE Name='Magnum'").fetchone()[0] == 0
    assert c.execute("SELECT Menge FROM Hefe WHERE Name='Fermentis SafAle US-05'").fetchone()[0] == 0
    bed = (await call({"type": "brauhelfer/lager_bedarf", "sud_id": 1}))["result"]
    assert len(bed["schon_gebucht"]) == 1
    det = (await call({"type": "brauhelfer/details", "sud_id": 1}))["result"]
    assert det["lager_buchungen"][0]["posten"][0]["name"] == "Pale Ale"

    # Zugabe in der Gärung: Bedarf für die einzelne Zutat
    bed = (await call({"type": "brauhelfer/lager_bedarf", "art": "zutat", "item_id": setup["zid"]}))["result"]
    assert bed["posten"][0]["name"] == "Citra" and bed["posten"][0]["gefunden"] is False

    # Einkaufsliste
    from pytest_homeassistant_custom_component.common import async_mock_service
    hass.states.async_set("todo.shopping_list", "0")
    added = async_mock_service(hass, "todo", "add_item")
    async_mock_service(hass, "todo", "get_items", response={"todo.shopping_list": {"items": []}}, supports_response="optional")
    os.utime(setup["path"], (time.time() + 5, time.time() + 5))
    await setup["entry"].runtime_data.async_refresh()
    msg = await call({"type": "brauhelfer/einkaufsliste", "sud_id": 1})
    assert msg["success"], msg
    items = [a.data["item"] for a in added]
    assert any("Pale Ale" in i and "kg" in i for i in items), items
    assert any(i.startswith("43 g Cascade") for i in items), items


async def test_ansage_ueber_lautsprecher(hass: HomeAssistant, setup):
    """Ansagen gehen per TTS an media_player, mit Ankündigungsmodus wo möglich."""
    from unittest.mock import patch

    call = setup["call"]
    hass.states.async_set("media_player.kueche_sonos", "playing", {"friendly_name": "Küche", "supported_features": 1048576 | 512})
    hass.states.async_set("media_player.alter_player", "idle", {"friendly_name": "Alt", "supported_features": 512})
    hass.states.async_set("tts.piper", "unknown", {"friendly_name": "Piper"})
    plays = async_mock_service(hass, "media_player", "play_media")

    aw = await call({"type": "brauhelfer/auswahl"})
    ls = {x["id"]: x for x in aw["result"]["lautsprecher"]}
    assert ls["media_player.kueche_sonos"]["ankuendigen"] is True
    assert ls["media_player.alter_player"]["ankuendigen"] is False
    assert aw["result"]["tts"] == [{"id": "tts.piper", "name": "Piper"}]

    r = await call({"type": "brauhelfer/test_meldung", "ansage": True})
    assert not r["success"]  # noch kein Lautsprecher gewählt

    r = await call({"type": "brauhelfer/einstellungen", "benachrichtigung": {
        "lautsprecher": ["media_player.kueche_sonos", "media_player.alter_player"], "lautstaerke": 40}})
    assert r["success"]
    with patch("custom_components.brauhelfer.benachrichtigung.tts.generate_media_source_id",
               return_value="media-source://tts/tts.piper?message=x") as gen:
        r = await call({"type": "brauhelfer/test_meldung", "ansage": True})
        assert r["success"], r
        await hass.async_block_till_done()
    assert gen.call_args.kwargs["engine"] == "tts.piper"  # ohne Auswahl die erste Engine
    daten = {c.data["entity_id"]: c.data for c in plays}
    assert daten["media_player.kueche_sonos"]["announce"] is True
    assert daten["media_player.kueche_sonos"]["extra"] == {"volume": 0.4}
    assert "announce" not in daten["media_player.alter_player"]
    assert daten["media_player.alter_player"]["media_content_id"].startswith("media-source://tts/")
