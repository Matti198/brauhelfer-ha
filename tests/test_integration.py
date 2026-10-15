"""Tests in einer echten HA-Testinstanz."""

import shutil
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest
from freezegun import freeze_time
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.brauhelfer.const import DOMAIN

SAMPLE = Path(__file__).parent / "kb_daten.sqlite"
OPTIONS = {"interval": 60, "max_age": 120, "backups": 3}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def dbfile(tmp_path):
    path = tmp_path / "kb_daten.sqlite"
    shutil.copy(SAMPLE, path)
    c = sqlite3.connect(path)
    pils = c.execute(
        "INSERT INTO Sud (Sudname,Status,Braudatum,SWAnstellen,MerklistenID) VALUES ('Pils',1,'2026-10-10T09:00:00',12.5,0)"
    ).lastrowid
    c.execute("INSERT INTO Sud (Sudname,Status,MerklistenID) VALUES ('Nicht gemerkt',0,0)")
    c.execute("UPDATE Sud SET MerklistenID=1 WHERE ID=1")  # Beispielsud auf die Merkliste
    c.commit()
    c.close()
    return path, pils


def _fake_pill(hass, name="Keller RAPT Pill AB12", slug="keller_rapt_pill_ab12"):
    """Gerät mit Dichte- und Temperatursensor wie von rapt_ble."""
    other = MockConfigEntry(domain="rapt_ble")
    other.add_to_hass(hass)
    dev = dr.async_get(hass).async_get_or_create(
        config_entry_id=other.entry_id, identifiers={("rapt_ble", slug)}, name=name
    )
    reg = er.async_get(hass)
    g = reg.async_get_or_create("sensor", "rapt_ble", f"{slug}_sg", device_id=dev.id,
                                suggested_object_id=f"{slug}_specific_gravity", original_name="Specific gravity")
    t = reg.async_get_or_create("sensor", "rapt_ble", f"{slug}_t", device_id=dev.id,
                                suggested_object_id=f"{slug}_temperature", original_device_class="temperature")
    return g.entity_id, t.entity_id


async def _ws(client, i, payload):
    await client.send_json({"id": i, **payload})
    return await client.receive_json()


async def test_config_flow(hass: HomeAssistant, dbfile):
    path, _ = dbfile
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    bad = await hass.config_entries.flow.async_configure(result["flow_id"], {"path": "/nope.sqlite"})
    assert bad["errors"] == {"path": "not_found"}
    ok = await hass.config_entries.flow.async_configure(result["flow_id"], {"path": str(path)})
    assert ok["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    opt = await hass.config_entries.options.async_init(entry.entry_id)
    opt = await hass.config_entries.options.async_configure(opt["flow_id"], OPTIONS)
    assert opt["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["interval"] == 60


async def test_brauen_bis_leer(hass: HomeAssistant, dbfile, hass_ws_client, hass_client):
    path, pils = dbfile
    g, t = _fake_pill(hass)
    entry = MockConfigEntry(domain=DOMAIN, data={"path": str(path)}, options=OPTIONS)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    from homeassistant.components import frontend
    assert "brauhelfer" in hass.data[frontend.DATA_PANELS]
    url = hass.data[frontend.DATA_PANELS]["brauhelfer"].config["_panel_custom"]["module_url"]
    client = await hass_client()
    resp = await client.get(url)
    assert resp.status == 200
    for modul in ("lib.js", "styles.js", "view-sud.js", "dialoge.js"):
        assert (await client.get(url.rsplit("/", 1)[0] + "/" + modul)).status == 200

    ws = await hass_ws_client(hass)
    c = sqlite3.connect(path)
    n_hgv = lambda sid: c.execute("SELECT count(*) FROM Hauptgaerverlauf WHERE SudID=?", (sid,)).fetchone()[0]

    # Übersicht
    msg = await _ws(ws, 1, {"type": "brauhelfer/data"})
    assert msg["success"], msg
    e = msg["result"]["entries"][0]
    assert [s["name"] for s in e["geplant"]] == ["Beispielsud Sierra Nevada Pale Ale"]
    assert [s["name"] for s in e["gaerend"]] == ["Pils"]
    assert e["pills"] == [{"name": "Keller RAPT Pill AB12", "gravity": g, "temperature": t, "belegt_von": None, "zuletzt": None}]
    assert e["aufzeichnungen"] == {}

    # Keine Aufzeichnung -> Timer trägt nichts ein
    hass.states.async_set(g, "1.012", {})
    hass.states.async_set(t, "18.0", {"unit_of_measurement": "°C"})
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=61))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert n_hgv(pils) == 0

    # ---------- Brautag
    msg = await _ws(ws, 2, {"type": "brauhelfer/braudaten", "sud_id": 1})
    assert msg["success"] and msg["result"]["werte"]["SWAnstellen"] == 13.1
    msg = await _ws(ws, 3, {"type": "brauhelfer/braudaten_speichern", "sud_id": 1,
                            "werte": {"SWKochende": 13.0, "WuerzemengeVorHopfenseihen": 20.5, "SWAnstellen": 12.8, "WuerzemengeAnstellen": 19.5},
                            "bemerkung": "Läuterung zäh"})
    assert msg["success"], msg
    row = c.execute("SELECT Status, SWAnstellen, BemerkungBrauen, erg_Sudhausausbeute FROM Sud WHERE ID=1").fetchone()
    assert row[0] == 0 and row[1] == 12.8 and row[2] == "Läuterung zäh" and row[3] > 50
    bad = await _ws(ws, 4, {"type": "brauhelfer/braudaten_speichern", "sud_id": 1, "werte": {"Quatsch": 1}})
    assert not bad["success"]
    brau = (dt_util.now() - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
    msg = await _ws(ws, 5, {"type": "brauhelfer/braudaten_speichern", "sud_id": 1, "werte": {},
                            "braudatum": brau, "gebraut": True})
    assert msg["success"], msg
    assert c.execute("SELECT Status, Braudatum FROM Sud WHERE ID=1").fetchone() == (1, brau + ":00")
    assert n_hgv(1) == 1
    await hass.async_block_till_done()
    assert hass.states.get("sensor.kleiner_brauhelfer_sud_beispielsud_sierra_nevada_pale_ale").state == "In Gärung"

    # ---------- Aufzeichnung
    msg = await _ws(ws, 6, {"type": "brauhelfer/aufzeichnung_starten", "sud_id": 1, "gravity": g, "temperature": t, "name": "Keller Pill"})
    assert msg["success"] and msg["result"]["warnung"] is None, msg
    assert n_hgv(1) == 2  # sofort ein erster Wert
    # dieselbe Pill für einen zweiten Sud -> Fehler
    msg = await _ws(ws, 7, {"type": "brauhelfer/aufzeichnung_starten", "sud_id": pils, "gravity": g})
    assert not msg["success"] and "zeichnet schon" in msg["error"]["message"]

    # kurz nach dem Start ist nichts fällig -> kein Doppel-Eintrag
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=6))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert n_hgv(1) == 2
    # nach dem Intervall (60 min) fällig
    hass.states.async_set(g, "1.010", {})
    with freeze_time(dt_util.utcnow() + timedelta(minutes=70)):
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done(wait_background_tasks=True)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert n_hgv(1) == 3 and n_hgv(pils) == 0

    # Aufzeichnung übersteht Neuladen
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    msg = await _ws(ws, 8, {"type": "brauhelfer/data"})
    assert "1" in msg["result"]["entries"][0]["aufzeichnungen"]
    assert msg["result"]["entries"][0]["pills"][0]["belegt_von"] == 1
    assert hass.states.get("select.kleiner_brauhelfer_brew_for_rapt_pill") is None

    msg = await _ws(ws, 9, {"type": "brauhelfer/eintragen", "sud_id": 1})
    assert msg["success"] and n_hgv(1) == 4

    # Dienst ohne sud_id: genau eine Aufzeichnung
    await hass.services.async_call(DOMAIN, "messwert_eintragen", {"restextrakt": 3.0, "temperatur": 19}, blocking=True)
    assert n_hgv(1) == 5

    # ---------- Gärung fertig
    msg = await _ws(ws, 11, {"type": "brauhelfer/abfuellen", "sud_id": 1, "dichte": 1.011, "temperatur": 4})
    assert msg["success"], msg
    row = c.execute("SELECT Status, SWJungbier, Abfuelldatum FROM Sud WHERE ID=1").fetchone()
    assert row[0] == 2 and row[1] == pytest.approx(2.82, abs=0.02) and row[2]
    assert c.execute("SELECT count(*) FROM Nachgaerverlauf WHERE SudID=1").fetchone()[0] == 1
    msg = await _ws(ws, 12, {"type": "brauhelfer/data"})
    e = msg["result"]["entries"][0]
    assert e["aufzeichnungen"] == {} and [s["name"] for s in e["abgefuellt"]] == ["Beispielsud Sierra Nevada Pale Ale"]
    await hass.async_block_till_done()
    assert hass.states.get("sensor.kleiner_brauhelfer_sud_beispielsud_sierra_nevada_pale_ale") is None

    # Ohne letzten Wert abfüllen
    msg = await _ws(ws, 13, {"type": "brauhelfer/abfuellen", "sud_id": pils})
    assert msg["success"] and n_hgv(pils) == 0

    # ---------- Leer
    msg = await _ws(ws, 14, {"type": "brauhelfer/verbraucht", "sud_id": 1})
    assert msg["success"]
    assert c.execute("SELECT Status FROM Sud WHERE ID=1").fetchone()[0] == 3
    msg = await _ws(ws, 15, {"type": "brauhelfer/verbraucht", "sud_id": 1})
    assert not msg["success"]
    c.close()

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert "brauhelfer" not in hass.data[frontend.DATA_PANELS]


async def test_button_ohne_aufzeichnung(hass: HomeAssistant, dbfile):
    path, _ = dbfile
    entry = MockConfigEntry(domain=DOMAIN, data={"path": str(path)}, options=OPTIONS)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    with pytest.raises(HomeAssistantError, match="keine Aufzeichnung"):
        await hass.services.async_call("button", "press", {"entity_id": "button.kleiner_brauhelfer_log_running_recordings_now"}, blocking=True)
