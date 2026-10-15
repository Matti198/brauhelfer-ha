"""Tests für Version 0.7: Prognose, Pill-Abgleich, Glättung, Knöpfe in Push-Meldungen."""

import math
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.brauhelfer import prognose
from custom_components.brauhelfer.const import DOMAIN

from .test_integration import _fake_pill

SAMPLE = Path(__file__).parent / "kb_daten.sqlite"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def _kurve(sw, end, tage, k=1.6, mitte=2.2):
    return end + (sw - end) / (1 + math.exp(k * (tage - mitte)))


def test_prognose_trifft_simulierte_gaerung():
    start = datetime(2026, 10, 1, 12)
    wahr = next(i / 24 for i in range(5000) if _kurve(13.0, 3.0, i / 24) - 3.0 <= prognose.FERTIG_ABSTAND)
    for tage in (1.5, 2, 3):
        punkte = [(start + timedelta(hours=4 * i), _kurve(13.0, 3.0, i * 4 / 24)) for i in range(int(tage * 6) + 1)]
        r = prognose.berechnen(punkte, 13.0, 3.0, punkte[-1][0])
        assert r and not r["erreicht"]
        assert abs((r["fertig_am"] - start).total_seconds() / 86400 - wahr) < 0.3


def test_prognose_grenzfaelle():
    start = datetime(2026, 10, 1, 12)
    # Anlaufphase: noch keine Aussage
    anlauf = [(start + timedelta(hours=4 * i), 12.9 - 0.05 * i) for i in range(5)]
    assert prognose.berechnen(anlauf, 13.0, 3.0, anlauf[-1][0]) is None
    # Endwert erreicht
    fertig = [(start, 13.0), (start + timedelta(days=5), 3.1)]
    assert prognose.berechnen(fertig, 13.0, 3.0, start + timedelta(days=5))["erreicht"]
    # Steht (kein Fortschritt) -> keine Prognose
    steht = [(start + timedelta(hours=4 * i), 6.0) for i in range(10)]
    assert prognose.berechnen(steht, 13.0, 3.0, steht[-1][0]) is None


@pytest.fixture
async def setup(hass: HomeAssistant, tmp_path, hass_ws_client):
    path = tmp_path / "kb_daten.sqlite"
    shutil.copy(SAMPLE, path)
    c = sqlite3.connect(path)
    brau = dt_util.now() - timedelta(days=3)
    sid = c.execute(
        "INSERT INTO Sud (Sudname,Status,Braudatum,SWAnstellen,Vergaerungsgrad,MerklistenID) VALUES ('Weizen',1,?,12.0,75,0)",
        (brau.strftime("%Y-%m-%dT%H:%M:%S"),),
    ).lastrowid
    for i in range(0, 3 * 6):
        t = brau + timedelta(hours=4 * i)
        c.execute(
            "INSERT INTO Hauptgaerverlauf (SudID,Zeitstempel,Restextrakt,Alc,Temp) VALUES (?,?,?,0,19)",
            (sid, t.strftime("%Y-%m-%dT%H:%M:%S"), round(_kurve(12.0, 3.0, i * 4 / 24, 1.4, 2.5), 2)),
        )
    c.commit()
    c.close()
    g, t = _fake_pill(hass)
    hass.states.async_set(g, "1.0200")
    hass.states.async_set(t, "19.0", {"unit_of_measurement": "°C"})
    entry = MockConfigEntry(domain=DOMAIN, data={"path": str(path)}, options={"interval": 60, "max_age": 120, "backups": 0})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ws = await hass_ws_client(hass)
    n = {"i": 1}

    async def call(payload):
        n["i"] += 1
        await ws.send_json({"id": n["i"], **payload})
        return await ws.receive_json()

    yield {"sid": sid, "g": g, "t": t, "call": call, "entry": entry, "path": path}


def _sud(data, sid):
    return next(s for s in data["result"]["entries"][0]["gaerend"] if s["id"] == sid)


async def test_prognose_im_panel_und_sensor(hass: HomeAssistant, setup):
    data = await setup["call"]({"type": "brauhelfer/data"})
    pg = _sud(data, setup["sid"])["prognose"]
    assert pg and not pg["erreicht"]
    fertig = dt_util.parse_datetime(pg["fertig_am"])  # wie in der Datenbank: lokale Zeit ohne Zone
    jetzt = dt_util.now().replace(tzinfo=None)
    assert jetzt < fertig < jetzt + timedelta(days=5)
    st = hass.states.get("sensor.kleiner_brauhelfer_sud_weizen")
    assert st and st.attributes.get("prognose_fertig")


async def test_pill_abgleich(hass: HomeAssistant, setup):
    call, sid, g, t = setup["call"], setup["sid"], setup["g"], setup["t"]
    coord = setup["entry"].runtime_data
    r = await call({"type": "brauhelfer/aufzeichnung_starten", "sud_id": sid, "gravity": g, "temperature": t, "name": "Pill"})
    assert r["success"], r
    roh = coord.read_gravity(g)
    # Spindel zeigt 0,4 °P mehr, Thermometer 0,5 °C weniger
    r = await call({"type": "brauhelfer/pill_abgleich", "sud_id": sid, "restextrakt": roh + 0.4, "temperatur": 18.5,
                    "referenz": "Spindel"})
    assert r["success"], r
    assert r["result"]["dichte"] == pytest.approx(0.4, abs=0.01)
    assert r["result"]["temperatur"] == pytest.approx(-0.5, abs=0.01)
    assert coord.read_gravity(g) == pytest.approx(roh + 0.4, abs=0.01)
    assert coord.read_temperature(t) == pytest.approx(18.5, abs=0.01)
    # Spindelwert steht im Gärverlauf
    c = sqlite3.connect(setup["path"])
    bem = c.execute("SELECT Bemerkung, Restextrakt FROM Hauptgaerverlauf WHERE SudID=? ORDER BY ID DESC LIMIT 1", (sid,)).fetchone()
    c.close()
    assert "Pill-Abgleich" in bem[0] and bem[1] == pytest.approx(roh + 0.4, abs=0.01)
    data = await call({"type": "brauhelfer/data"})
    assert g in data["result"]["entries"][0]["korrekturen"]
    # Unplausibel große Abweichung wird abgelehnt
    r = await call({"type": "brauhelfer/pill_abgleich", "sud_id": sid, "restextrakt": roh + 6})
    assert not r["success"]
    # Zurücksetzen
    r = await call({"type": "brauhelfer/pill_abgleich", "sud_id": sid, "zuruecksetzen": True})
    assert r["success"]
    assert coord.read_gravity(g) == pytest.approx(roh, abs=0.001)


async def test_glaettung_median(hass: HomeAssistant, setup, monkeypatch):
    coord = setup["entry"].runtime_data
    g = setup["g"]
    hass.config.components.add("recorder")

    async def historie(entity_id, fenster):
        # ein Ausreißer (1.050) zwischen ruhigen Werten
        return ["1.0200", "1.0202", "1.0500", "1.0198", "1.0201"]

    monkeypatch.setattr(coord, "_async_historie", historie)
    wert = await coord.async_geglaettet(g, None, coord.read_gravity)
    assert wert == pytest.approx(coord.read_gravity(g), abs=0.05)  # Ausreißer ignoriert
    coord.speicher.einstellungen["glaettung_min"] = 0
    assert await coord.async_geglaettet(g, None, coord.read_gravity) == coord.read_gravity(g)


async def test_push_knoepfe(hass: HomeAssistant, setup):
    call, sid = setup["call"], setup["sid"]
    coord = setup["entry"].runtime_data
    pushes = async_mock_service(hass, "notify", "mobile_app_iphone")
    await call({"type": "brauhelfer/einstellungen", "benachrichtigung": {"ziele": ["mobile_app_iphone"]}})
    sud = coord.data.sude[sid]
    await coord.benachrichtiger.async_senden("t", "x", ereignis="stagnation", schluessel=f"stagnation:{sid}",
                                             aktionen=__import__("custom_components.brauhelfer.benachrichtigung",
                                                                 fromlist=["gaer_aktionen"]).gaer_aktionen(sid))
    await hass.async_block_till_done()
    acts = pushes[-1].data["data"]["actions"]
    assert [a["action"] for a in acts] == [f"BRAUHELFER_FERTIG_{sid}", f"BRAUHELFER_WARTEN_{sid}"]

    # "Noch warten": Erinnerung gespeichert
    hass.bus.async_fire("mobile_app_notification_action", {"action": f"BRAUHELFER_WARTEN_{sid}"})
    await hass.async_block_till_done()
    assert str(sid) in coord.speicher.data["erinnern"]
    # Erinnerung fällig -> Schlüssel werden zurückgesetzt
    coord.speicher.data["erinnern"][str(sid)] = (dt_util.now() - timedelta(minutes=1)).isoformat()
    await coord.benachrichtiger._pruefe_gaerung(sud)
    assert str(sid) not in coord.speicher.data["erinnern"]

    # "Gärung fertig": Sud wird abgefüllt, Bestätigung kommt
    hass.bus.async_fire("mobile_app_notification_action", {"action": f"BRAUHELFER_FERTIG_{sid}"})
    await hass.async_block_till_done()
    assert coord.data.sude[sid].status == 2
    assert any("abgefüllt" in p.data["title"] for p in pushes)
    # Fremde Aktionen werden ignoriert
    hass.bus.async_fire("mobile_app_notification_action", {"action": "IRGENDWAS_ANDERES"})
    await hass.async_block_till_done()
