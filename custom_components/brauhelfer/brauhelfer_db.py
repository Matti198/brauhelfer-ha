"""Zugriff auf die Datenbank des kleinen Brauhelfers (kb_daten.sqlite).

Dieses Modul hat keine Abhängigkeit zu Home Assistant und läuft synchron
(es wird aus HA heraus im Executor aufgerufen).

Die Berechnungen beim Eintragen eines Gärverlauf-Messwerts sind aus dem
kleiner-brauhelfer-core übernommen (modelhauptgaerverlauf.cpp, modelsud.cpp,
biercalc.cpp), damit die Datenbank danach so aussieht, als hätte das
Desktop-Programm den Wert selbst eingetragen.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

# Statuswerte aus brauhelfer.h (enum class SudStatus)
STATUS_REZEPT = 0
STATUS_GEBRAUT = 1
STATUS_ABGEFUELLT = 2
STATUS_VERBRAUCHT = 3

STATUS_TEXT = {
    STATUS_REZEPT: "Rezept",
    STATUS_GEBRAUT: "Gebraut",
    STATUS_ABGEFUELLT: "Abgefüllt",
    STATUS_VERBRAUCHT: "Verbraucht",
}

# Weitere Zutaten (brauhelfer.h)
_ZUSATZ_TYP_HOPFEN = 100
_ZUSATZ_ZEITPUNKT_GAERUNG = 0
_ZUSATZ_STATUS_NICHT_ZUGEGEBEN = 0
_EINHEIT_STK = 3

# Spalten, die die Integration braucht. Fehlt eine, ist die Datenbank
# zu alt oder hat ein unbekanntes Format, und es wird nichts geschrieben.
REQUIRED_COLUMNS = {
    "Sud": {
        "ID", "Sudname", "Sudnummer", "Status", "Braudatum", "MerklistenID",
        "SW", "SWAnstellen", "SWJungbier", "TemperaturJungbier",
        "TemperaturKarbonisierung", "Gespeichert", "Menge", "CO2", "IBU",
        "Kategorie", "Vergaerungsgrad", "erg_Farbe", "erg_Alkohol", "Abfuelldatum", "ReifungStart",
        "Anlage", "erg_S_Gesamt", "Kochdauer", "SWKochbeginn", "WuerzemengeKochbeginn", "SWKochende",
        "WuerzemengeVorHopfenseihen", "WuerzemengeKochende", "WuerzemengeAnstellen", "VerduennungAnstellen",
        "Speisemenge", "MengeHefestarter", "SWHefestarter", "BemerkungBrauen", "SWSchnellgaerprobe",
        "JungbiermengeAbfuellen", "erg_Sudhausausbeute", "erg_EffektiveAusbeute", "SchnellgaerprobeAktiv",
    },
    "Hauptgaerverlauf": {"ID", "SudID", "Zeitstempel", "Restextrakt", "Alc", "Temp", "Bemerkung"},
    "WeitereZutatenGaben": {"SudID", "Menge", "Einheit", "Typ", "Zeitpunkt", "Zugabestatus", "Ausbeute"},
    "Global": {"db_Version"},
    "Hefegaben": {"SudID", "Name"},
    "Schnellgaerverlauf": {"SudID", "Zeitstempel", "Restextrakt", "Alc", "Temp"},
    "Nachgaerverlauf": {"SudID", "Zeitstempel", "Druck", "Temp", "CO2"},
    "Ausruestung": {"Name", "KorrekturMenge"},
    "Maischplan": {"SudID", "Typ", "Name", "TempWasser", "TempRast", "DauerRast"},
    "Hopfengaben": {"SudID", "Name", "erg_Menge", "Zeit", "Vorderwuerze"},
    "Malzschuettung": {"SudID", "Name", "erg_Menge"},
    "Malz": {"Name", "Menge"},
    "Hopfen": {"Name", "Menge"},
    "Hefe": {"Name", "Menge"},
    "WeitereZutaten": {"Name", "Menge", "Einheit"},
    "Bewertungen": {"SudID", "Datum", "Woche", "Sterne", "Bemerkung", "Farbe", "Schaum", "Geruch",
                    "Geschmack", "Antrunk", "Haupttrunk", "Nachtrunk", "Gesamteindruck"},
}

BALLING = 2.0665

# Uhr für "jetzt" (naive Ortszeit). Home Assistant setzt hier seine eigene Zeitzone,
# damit Einträge auch dann stimmen, wenn der Container in UTC läuft.
_clock = datetime.now
_tz = lambda: None  # noqa: E731


def set_clock(func, tz_func) -> None:
    """func() -> aktuelle Zeit, tz_func() -> Zeitzone für Zeitstempel mit Offset."""
    global _clock, _tz  # noqa: PLW0603
    _clock = func
    _tz = tz_func


def jetzt() -> datetime:
    return _clock().replace(microsecond=0, tzinfo=None)
BUSY_TIMEOUT_S = 30


class BrauhelferError(Exception):
    """Allgemeiner Fehler beim Datenbankzugriff."""


class SchemaError(BrauhelferError):
    """Datenbank hat nicht das erwartete Format."""


# --------------------------------------------------------------------------
# Berechnungen (biercalc.cpp)
# --------------------------------------------------------------------------

def dichte_to_plato(sg: float) -> float:
    """Spezifische Dichte (SG) in °Plato, wie BierCalc::dichteToPlato."""
    return -616.868 + 1111.14 * sg - 630.272 * sg**2 + 135.997 * sg**3


def plato_to_dichte(plato: float) -> float:
    """°Plato in spezifische Dichte, wie BierCalc::platoToDichte."""
    return 1 + (plato / (258.6 - ((plato / 258.2) * 227.1)))


def to_tre(sw: float, sre: float) -> float:
    """Tatsächlicher Restextrakt aus Stammwürze und scheinbarem Restextrakt."""
    return 0.1808 * sw + 0.8192 * sre


def alkohol(sw: float, sre: float, alc_zusatz: float = 0.0) -> float:
    """Alkohol in %vol, wie BierCalc::alkohol."""
    if sw <= 0.0:
        return 0.0
    tre = to_tre(sw, sre)
    dichte = plato_to_dichte(tre)
    alc_gewicht = (sw - tre) / (BALLING - 0.010665 * sw)
    alc = (alc_gewicht + alc_zusatz) * dichte / 0.794
    return max(alc, 0.0)


def vergaerungsgrad(sw: float, sre: float) -> float:
    """Scheinbarer Vergärungsgrad in %."""
    if sw <= 0.0:
        return 0.0
    return (1 - sre / sw) * 100


# --------------------------------------------------------------------------
# Datenstrukturen
# --------------------------------------------------------------------------

@dataclass
class Messwert:
    zeitstempel: datetime | None
    restextrakt: float
    alc: float
    temp: float
    bemerkung: str | None


@dataclass
class Sud:
    id: int
    name: str
    nummer: int
    status: int
    kategorie: str | None
    braudatum: datetime | None
    merkliste: bool
    menge: float
    sw_rezept: float
    sw_anstellen: float
    sw_ist: float
    co2: float
    ibu: float
    vergaerungsgrad_rezept: float
    farbe_ebc: float = 0.0
    alkohol_rezept: float = 0.0
    hefe: list[str] = field(default_factory=list)
    kommentar: str | None = None
    abfuelldatum: datetime | None = None
    lager_fehlt: list[dict] = field(default_factory=list)
    sre_schnellgaer: float | None = None
    letzter_messwert: Messwert | None = None
    anzahl_messwerte: int = 0
    verlauf: list[Messwert] = field(default_factory=list)

    @property
    def sre_erwartet(self) -> float:
        """Erwarteter Restextrakt aus Rezept-Vergärungsgrad (BierCalc::sreAusVergaerungsgrad)."""
        return self.sw_ist * (100 - self.vergaerungsgrad_rezept) / 100

    @property
    def status_text(self) -> str:
        if self.status == STATUS_REZEPT:
            return "Geplant"
        if self.status == STATUS_GEBRAUT:
            return "In Gärung"
        return STATUS_TEXT.get(self.status, str(self.status))

    @property
    def tage_seit_brautag(self) -> int | None:
        if self.braudatum is None:
            return None
        return (jetzt() - self.braudatum).days


@dataclass
class Snapshot:
    db_version: int
    sude: dict[int, Sud] = field(default_factory=dict)
    mtime: float = 0.0

    @property
    def geplant(self) -> list[Sud]:
        return [s for s in self.sude.values() if s.status == STATUS_REZEPT]

    @property
    def gaerend(self) -> list[Sud]:
        return [s for s in self.sude.values() if s.status == STATUS_GEBRAUT]

    @property
    def abgefuellt(self) -> list[Sud]:
        return sorted(
            (s for s in self.sude.values() if s.status == STATUS_ABGEFUELLT),
            key=lambda s: s.abfuelldatum or s.braudatum or datetime.min,
            reverse=True,
        )

    @property
    def aktuell(self) -> list[Sud]:
        """Geplante und gärende Sude (für Sensoren)."""
        return [s for s in self.sude.values() if s.status in (STATUS_REZEPT, STATUS_GEBRAUT)]


# --------------------------------------------------------------------------
# Hilfsfunktionen
# --------------------------------------------------------------------------

def _parse_dt(value) -> datetime | None:
    """Zeitstempel im Qt-ISO-Format lesen (z. B. 2026-10-15T10:31:00)."""
    if not value:
        return None
    text = str(value).strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        # Brauhelfer arbeitet mit Ortszeit; Zeitzone entfernen.
        dt = dt.astimezone(_tz()).replace(tzinfo=None)
    return dt


def _format_dt(dt: datetime) -> str:
    """Wie QDateTime::toString(Qt::ISODate) für Ortszeit."""
    return dt.replace(microsecond=0, tzinfo=None).isoformat()


def _connect(path: str | os.PathLike, readonly: bool) -> sqlite3.Connection:
    path = Path(path)
    if not path.is_file():
        raise BrauhelferError(f"Datenbank nicht gefunden: {path}")
    if readonly:
        uri = f"{path.resolve().as_uri()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=BUSY_TIMEOUT_S)
    else:
        conn = sqlite3.connect(str(path), timeout=BUSY_TIMEOUT_S, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


def check_schema(conn: sqlite3.Connection) -> int:
    """Prüft, ob alle benötigten Tabellen und Spalten vorhanden sind.

    Gibt die Datenbankversion zurück.
    """
    for table, needed in REQUIRED_COLUMNS.items():
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if not cols:
            raise SchemaError(f"Tabelle {table} fehlt – ist das eine Brauhelfer-Datenbank?")
        missing = needed - cols
        if missing:
            raise SchemaError(f"Tabelle {table}: Spalten fehlen: {', '.join(sorted(missing))}")
    row = conn.execute("SELECT db_Version FROM Global").fetchone()
    if row is None:
        raise SchemaError("Keine Datenbankversion in Tabelle Global")
    return int(row[0])


_ZUSATZ_ZEITPUNKT_KOCHEN = 1
_ZUSATZ_ZEITPUNKT_MAISCHEN = 2


@dataclass
class _WzExtrakt:
    maischen: float = 0.0
    kochen: float = 0.0
    gaerung_aktuell: float = 0.0
    unvergaerbar: float = 0.0


def _wz_extrakt(conn: sqlite3.Connection, sud_id: int) -> _WzExtrakt:
    """Extrakt aus weiteren Zutaten, wie ModelSud::updateSwWeitereZutaten."""
    out = _WzExtrakt()
    rows = conn.execute(
        "SELECT * FROM WeitereZutatenGaben WHERE SudID = ?",
        (sud_id,),
    )
    for r in rows:
        if r["Typ"] == _ZUSATZ_TYP_HOPFEN:
            continue
        ausbeute = r["Ausbeute"] or 0.0
        if ausbeute <= 0.0:
            continue
        menge = r["Menge"] or 0.0
        if r["Einheit"] != _EINHEIT_STK:
            menge /= 1000
        extrakt = menge * ausbeute
        if extrakt <= 0.0:
            continue
        zp = r["Zeitpunkt"]
        if zp == _ZUSATZ_ZEITPUNKT_GAERUNG:
            if r["Zugabestatus"] != _ZUSATZ_STATUS_NICHT_ZUGEGEBEN:
                out.gaerung_aktuell += extrakt
        elif zp == _ZUSATZ_ZEITPUNKT_KOCHEN:
            out.kochen += extrakt
        elif zp == _ZUSATZ_ZEITPUNKT_MAISCHEN:
            out.maischen += extrakt
        if "Unvergaerbar" in r.keys() and r["Unvergaerbar"]:
            out.unvergaerbar += extrakt
    return out


def _sw_gaerung_zugaben(conn: sqlite3.Connection, sud_id: int) -> float:
    """Extrakt aus bereits zugegebenen Gärungs-Zutaten (swWzGaerungCurrent)."""
    return _wz_extrakt(conn, sud_id).gaerung_aktuell


def _sw_ist(conn: sqlite3.Connection, sud_row: sqlite3.Row) -> float:
    return (sud_row["SWAnstellen"] or 0.0) + _sw_gaerung_zugaben(conn, sud_row["ID"])


# --------------------------------------------------------------------------
# Öffentliche Funktionen
# --------------------------------------------------------------------------

def validate(path: str) -> int:
    """Datei öffnen und Schema prüfen. Gibt die DB-Version zurück."""
    try:
        conn = _connect(path, readonly=True)
        try:
            return check_schema(conn)
        finally:
            conn.close()
    except sqlite3.DatabaseError as err:
        raise BrauhelferError(f"Datei ist keine lesbare SQLite-Datenbank: {err}") from err


def read_snapshot(path: str) -> Snapshot:
    """Liest geplante (Merkliste) und gebraute Sude inkl. letztem Messwert."""
    mtime = Path(path).stat().st_mtime
    try:
        conn = _connect(path, readonly=True)
    except sqlite3.DatabaseError as err:
        raise BrauhelferError(str(err)) from err
    try:
        version = check_schema(conn)
        snap = Snapshot(db_version=version, mtime=mtime)
        rows = conn.execute(
            "SELECT * FROM Sud WHERE Status IN (?, ?) OR (Status = ? AND MerklistenID > 0) "
            "ORDER BY Status DESC, Braudatum, Sudname",
            (STATUS_GEBRAUT, STATUS_ABGEFUELLT, STATUS_REZEPT),
        ).fetchall()
        for r in rows:
            sud = Sud(
                id=r["ID"],
                name=r["Sudname"],
                nummer=r["Sudnummer"] or 0,
                status=r["Status"],
                kategorie=r["Kategorie"],
                braudatum=_parse_dt(r["Braudatum"]) if r["Status"] != STATUS_REZEPT else None,
                merkliste=(r["MerklistenID"] or 0) > 0,
                menge=r["Menge"] or 0.0,
                sw_rezept=r["SW"] or 0.0,
                sw_anstellen=r["SWAnstellen"] or 0.0,
                sw_ist=_sw_ist(conn, r),
                co2=r["CO2"] or 0.0,
                ibu=r["IBU"] or 0.0,
                vergaerungsgrad_rezept=r["Vergaerungsgrad"] or 0.0,
                farbe_ebc=r["erg_Farbe"] or 0.0,
                alkohol_rezept=r["erg_Alkohol"] or 0.0,
                kommentar=r["Kommentar"],
                abfuelldatum=_parse_dt(r["Abfuelldatum"]) if r["Status"] >= STATUS_ABGEFUELLT else None,
                hefe=[
                    h["Name"] for h in conn.execute(
                        "SELECT Name FROM Hefegaben WHERE SudID = ? ORDER BY ID", (r["ID"],)
                    ) if h["Name"]
                ],
            )
            if sud.status == STATUS_REZEPT:
                sud.lager_fehlt = [
                    {"typ": p["typ"], "name": p["name"], "fehlt": p["fehlt"], "einheit": p["einheit"], "gefunden": p["gefunden"]}
                    for p in _bedarf(conn, sud.id)
                    if not p["spaeter"] and p["menge"] > 0 and (p["fehlt"] > 0 or not p["gefunden"])
                ]
            if sud.status in (STATUS_GEBRAUT, STATUS_ABGEFUELLT):
                mw = conn.execute(
                    "SELECT Zeitstempel, Restextrakt, Alc, Temp, Bemerkung FROM Hauptgaerverlauf "
                    "WHERE SudID = ?",
                    (sud.id,),
                ).fetchall()
                sud.anzahl_messwerte = len(mw)
                sud.verlauf = sorted(
                    (
                        Messwert(
                            zeitstempel=_parse_dt(m["Zeitstempel"]),
                            restextrakt=m["Restextrakt"] or 0.0,
                            alc=m["Alc"] or 0.0,
                            temp=m["Temp"] or 0.0,
                            bemerkung=m["Bemerkung"],
                        )
                        for m in mw
                    ),
                    key=lambda m: m.zeitstempel or datetime.min,
                )
                if sud.verlauf:
                    # Wie getLastRow(): späteste Zeit gewinnt (nicht die höchste ID)
                    sud.letzter_messwert = sud.verlauf[-1]
                if r["SchnellgaerprobeAktiv"]:
                    # Letzter Wert der Schnellgärprobe (ohne den Anstellwert) = erreichbarer Endvergärungsgrad
                    sg = [
                        (_parse_dt(x["Zeitstempel"]) or datetime.min, x["Restextrakt"])
                        for x in conn.execute("SELECT Zeitstempel, Restextrakt FROM Schnellgaerverlauf WHERE SudID = ?", (sud.id,))
                        if x["Restextrakt"] is not None and x["Restextrakt"] < sud.sw_ist - 0.5
                    ]
                    if sg:
                        sud.sre_schnellgaer = max(sg)[1]
            snap.sude[sud.id] = sud
        return snap
    except sqlite3.DatabaseError as err:
        raise BrauhelferError(str(err)) from err
    finally:
        conn.close()


def backup(path: str, keep: int) -> Path | None:
    """Konsistente Sicherung über die SQLite-Backup-API.

    Sicherungen liegen in <Ordner>/backup/ und die ältesten werden gelöscht,
    sodass höchstens `keep` übrig bleiben. keep <= 0 schaltet Backups ab.
    """
    if keep <= 0:
        return None
    src_path = Path(path)
    backup_dir = src_path.parent / "backup"
    backup_dir.mkdir(exist_ok=True)
    target = backup_dir / f"{src_path.stem}_{jetzt():%Y%m%d_%H%M%S}{src_path.suffix}"
    src = _connect(src_path, readonly=True)
    try:
        dst = sqlite3.connect(str(target))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    # Die letzten `keep` Sicherungen behalten, dazu von älteren je eine pro Tag
    # für 30 Tage. So lässt sich auch ein Fehler von vor zwei Wochen noch zurückholen.
    files = sorted(backup_dir.glob(f"{src_path.stem}_*{src_path.suffix}"))
    behalten_tage: set[str] = set()
    grenze = (jetzt() - timedelta(days=30)).strftime("%Y%m%d")
    for old in reversed(files[:-keep]):
        tag = old.stem[len(src_path.stem) + 1:][:8]
        if tag >= grenze and tag not in behalten_tage:
            behalten_tage.add(tag)
            continue
        try:
            old.unlink()
        except OSError:
            pass
    return target


# --------------------------------------------------------------------------
# Schreiben
# --------------------------------------------------------------------------

def _write_tx(path: str, fn):
    """fn(conn) in einer Schreib-Transaktion ausführen."""
    conn = _connect(path, readonly=False)
    try:
        check_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        try:
            result = fn(conn)
            conn.execute("COMMIT")
            return result
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    except sqlite3.OperationalError as err:
        if "locked" in str(err).lower() or "busy" in str(err).lower():
            raise BrauhelferError(
                "Datenbank ist gesperrt (wird sie gerade im Brauhelfer gespeichert?)"
            ) from err
        raise BrauhelferError(str(err)) from err
    except sqlite3.DatabaseError as err:
        raise BrauhelferError(str(err)) from err
    finally:
        conn.close()


def _get_sud(conn: sqlite3.Connection, sud_id: int, *status: int) -> sqlite3.Row:
    sud = conn.execute("SELECT * FROM Sud WHERE ID = ?", (sud_id,)).fetchone()
    if sud is None:
        raise BrauhelferError(f"Sud mit ID {sud_id} existiert nicht")
    if status and sud["Status"] not in status:
        erlaubt = " oder ".join(f"'{STATUS_TEXT[s]}'" for s in status)
        raise BrauhelferError(
            f"Sud '{sud['Sudname']}' steht auf '{STATUS_TEXT.get(sud['Status'], sud['Status'])}', "
            f"erwartet {erlaubt}"
        )
    return sud


def _update_sud(conn: sqlite3.Connection, sud_id: int, values: dict) -> None:
    values = {**values, "Gespeichert": _format_dt(jetzt())}
    sets = ", ".join(f"{k} = ?" for k in values)
    conn.execute(f"UPDATE Sud SET {sets} WHERE ID = ?", (*values.values(), sud_id))


def _insert_messwert(
    conn: sqlite3.Connection, sud: sqlite3.Row, restextrakt: float, temp: float,
    bemerkung: str | None, zeitpunkt: datetime,
) -> Messwert:
    sud_id = sud["ID"]
    sw = _sw_ist(conn, sud)
    alc = alkohol(sw, restextrakt)
    conn.execute(
        "INSERT INTO Hauptgaerverlauf (SudID, Zeitstempel, Restextrakt, Alc, Temp, Bemerkung) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (sud_id, _format_dt(zeitpunkt), round(restextrakt, 2), alc, round(temp, 1), bemerkung),
    )
    rows = conn.execute(
        "SELECT Zeitstempel, Temp FROM Hauptgaerverlauf WHERE SudID = ?", (sud_id,)
    ).fetchall()
    latest = max((_parse_dt(r["Zeitstempel"]) or datetime.min) for r in rows)
    temp_max = max(max((r["Temp"] or 0.0) for r in rows), 0.0)
    updates: dict = {"TemperaturKarbonisierung": temp_max}
    if zeitpunkt >= latest:
        updates["SWJungbier"] = round(restextrakt, 2)
        updates["TemperaturJungbier"] = round(temp, 1)
        # erg_Alkohol wie ModelSud::update (SREIst; ohne Zucker zum Karbonisieren)
        if not sud["SchnellgaerprobeAktiv"]:
            updates["erg_Alkohol"] = alc
    _update_sud(conn, sud_id, updates)
    return Messwert(zeitstempel=zeitpunkt, restextrakt=round(restextrakt, 2), alc=alc, temp=round(temp, 1), bemerkung=bemerkung)


def add_messwert(
    path: str,
    sud_id: int,
    restextrakt: float,
    temp: float,
    bemerkung: str | None = None,
    zeitpunkt: datetime | None = None,
) -> Messwert:
    """Trägt einen Messwert in den Hauptgärverlauf ein.

    Macht dasselbe wie das Desktop-Programm beim Hinzufügen einer Zeile:
    - Alkohol aus Stammwürze (inkl. zugegebener Gärungs-Zutaten) berechnen
    - Ist es der jüngste Messwert, SWJungbier und TemperaturJungbier im Sud setzen
    - TemperaturKarbonisierung = höchste Temperatur im Gärverlauf
    """
    zeitpunkt = (zeitpunkt or jetzt()).replace(microsecond=0)

    def fn(conn):
        sud = _get_sud(conn, sud_id, STATUS_GEBRAUT)
        return _insert_messwert(conn, sud, restextrakt, temp, bemerkung, zeitpunkt)

    return _write_tx(path, fn)


# --------------------------------------------------------------------------
# Brautag (Tab „Braudaten“ im Brauhelfer)
# --------------------------------------------------------------------------

# Felder, die im Formular bearbeitet werden: DB-Spalte -> (Bezeichnung, Einheit)
BRAUDATEN_FELDER: dict[str, tuple[str, str]] = {
    "WuerzemengeKochbeginn": ("Würzemenge Kochbeginn", "l"),
    "SWKochbeginn": ("Stammwürze Kochbeginn", "°P"),
    "WuerzemengeVorHopfenseihen": ("Würzemenge vor Hopfenseihen", "l"),
    "WuerzemengeKochende": ("Würzemenge Kochende", "l"),
    "SWKochende": ("Stammwürze Kochende", "°P"),
    "VerduennungAnstellen": ("Verdünnung", "l"),
    "MengeHefestarter": ("Menge Hefestarter", "l"),
    "SWHefestarter": ("Stammwürze Hefestarter", "°P"),
    "Speisemenge": ("Speisemenge", "l"),
    "WuerzemengeAnstellen": ("Würzemenge Anstellen", "l"),
    "SWAnstellen": ("Stammwürze Anstellen", "°P"),
}


def _menge_soll_anstellen(conn: sqlite3.Connection, sud: sqlite3.Row) -> float:
    korrektur = 0.0
    if sud["Anlage"]:
        row = conn.execute(
            "SELECT KorrekturMenge FROM Ausruestung WHERE Name = ?", (sud["Anlage"],)
        ).fetchone()
        if row and row["KorrekturMenge"]:
            korrektur = row["KorrekturMenge"]
    return (sud["Menge"] or 0.0) + korrektur


def sudhausausbeute(sw: float, sw_dichte: float, menge: float, schuettung: float) -> float:
    if schuettung <= 0.0:
        return 0.0
    return sw * plato_to_dichte(sw_dichte) * menge / schuettung


def _ausbeuten(conn: sqlite3.Connection, sud: sqlite3.Row, v: dict) -> tuple[float, float]:
    """erg_Sudhausausbeute und erg_EffektiveAusbeute wie ModelSud::update."""
    wz = _wz_extrakt(conn, sud["ID"])
    schuet = sud["erg_S_Gesamt"] or 0.0
    sw_dichte = v["SWKochende"]
    sha = sudhausausbeute(sw_dichte - wz.maischen - wz.kochen, sw_dichte, v["WuerzemengeVorHopfenseihen"], schuet)
    soll = _menge_soll_anstellen(conn, sud)
    sw_starter = (v["SWHefestarter"] * v["MengeHefestarter"] / soll) if v["MengeHefestarter"] > 0 and soll > 0 else 0.0
    sw_dichte = v["SWAnstellen"]
    menge_total = v["WuerzemengeAnstellen"] + v["Speisemenge"]
    eff = sudhausausbeute(sw_dichte - wz.maischen - wz.kochen - sw_starter, sw_dichte, menge_total, schuet)
    return sha, eff


def get_braudaten(path: str, sud_id: int) -> dict:
    """Werte für das Brautag-Formular, inkl. Zielwerte aus dem Rezept."""
    conn = _connect(path, readonly=True)
    try:
        check_schema(conn)
        sud = _get_sud(conn, sud_id)
        wz = _wz_extrakt(conn, sud_id)
        return {
            "sud_id": sud_id,
            "name": sud["Sudname"],
            "status": sud["Status"],
            "braudatum": _format_dt(_parse_dt(sud["Braudatum"])) if _parse_dt(sud["Braudatum"]) else None,
            "bemerkung": sud["BemerkungBrauen"] or "",
            "werte": {k: sud[k] or 0.0 for k in BRAUDATEN_FELDER},
            "rezept": {
                "sw": sud["SW"] or 0.0,
                "menge": sud["Menge"] or 0.0,
                "menge_soll_anstellen": _menge_soll_anstellen(conn, sud),
                "kochdauer": sud["Kochdauer"] or 0,
                "sudhausausbeute": sud["Sudhausausbeute"] if "Sudhausausbeute" in sud.keys() else None,
                "vergaerungsgrad": sud["Vergaerungsgrad"] or 0.0,
            },
            "schuettung": sud["erg_S_Gesamt"] or 0.0,
            "wz_maischen_kochen": wz.maischen + wz.kochen,
        }
    finally:
        conn.close()


def save_braudaten(
    path: str,
    sud_id: int,
    werte: dict,
    braudatum: datetime | None = None,
    bemerkung: str | None = None,
    gebraut: bool = False,
) -> None:
    """Brautag-Werte speichern und optional den Sud auf „gebraut“ setzen.

    Folgewerte wie im Brauhelfer (ModelSud::setDataExt und update, Status Rezept):
    SWSchnellgaerprobe/SWJungbier aus SWAnstellen und Vergärungsgrad,
    JungbiermengeAbfuellen = WuerzemengeAnstellen, Sudhausausbeute und effektive Ausbeute.
    Beim „Sud gebraut“ wie TabBraudaten::on_btnSudGebraut_clicked: Braudatum, Status,
    erster Eintrag in Schnell- und Hauptgärverlauf mit der Anstellwürze.
    """
    unbekannt = set(werte) - set(BRAUDATEN_FELDER)
    if unbekannt:
        raise BrauhelferError(f"Unbekannte Felder: {', '.join(sorted(unbekannt))}")
    for k, val in werte.items():
        if val is None or not isinstance(val, (int, float)) or val < 0 or val > 1000:
            raise BrauhelferError(f"Ungültiger Wert für {BRAUDATEN_FELDER[k][0]}: {val}")

    def fn(conn):
        sud = _get_sud(conn, sud_id, STATUS_REZEPT, STATUS_GEBRAUT) if not gebraut else _get_sud(conn, sud_id, STATUS_REZEPT)
        v = {k: (sud[k] or 0.0) for k in BRAUDATEN_FELDER}
        v.update({k: float(x) for k, x in werte.items()})
        updates: dict = dict(werte)
        if bemerkung is not None:
            updates["BemerkungBrauen"] = bemerkung
        if braudatum is not None:
            updates["Braudatum"] = _format_dt(braudatum)

        if sud["Status"] == STATUS_REZEPT:
            wz = _wz_extrakt(conn, sud_id)
            vg_rezept = sud["Vergaerungsgrad"] or 0.0
            sre = (v["SWAnstellen"] - wz.unvergaerbar) * (100 - vg_rezept) / 100 + wz.unvergaerbar
            updates["SWSchnellgaerprobe"] = sre
            updates["SWJungbier"] = sre
            updates["JungbiermengeAbfuellen"] = v["WuerzemengeAnstellen"]
            sha, eff = _ausbeuten(conn, sud, v)
            updates["erg_Sudhausausbeute"] = sha
            updates["erg_EffektiveAusbeute"] = eff

        if gebraut:
            dt = braudatum or _parse_dt(sud["Braudatum"]) or jetzt()
            updates["Braudatum"] = _format_dt(dt)
            updates["Status"] = STATUS_GEBRAUT
            sw_ist = v["SWAnstellen"] + _wz_extrakt(conn, sud_id).gaerung_aktuell
            updates["erg_Alkohol"] = alkohol(sw_ist, updates.get("SWJungbier", sud["SWJungbier"] or 0.0))
            _update_sud(conn, sud_id, updates)
            for table in ("Schnellgaerverlauf", "Hauptgaerverlauf"):
                n = conn.execute(f"SELECT count(*) FROM {table} WHERE SudID = ?", (sud_id,)).fetchone()[0]
                if n == 0:
                    conn.execute(
                        f"INSERT INTO {table} (SudID, Zeitstempel, Restextrakt, Alc, Temp) VALUES (?, ?, ?, 0, 18)",
                        (sud_id, _format_dt(dt), round(sw_ist, 2)),
                    )
        else:
            _update_sud(conn, sud_id, updates)

    _write_tx(path, fn)


# --------------------------------------------------------------------------
# Gärung fertig (Abfüllen) und Verbraucht
# --------------------------------------------------------------------------

def co2(druck: float, temp: float) -> float:
    """BierCalc::co2 (g/l)."""
    import math  # noqa: PLC0415

    return (1.013 + druck) * math.exp(-10.73797 + (2617.25 / (temp + 273.15))) * 10


def abfuellen(
    path: str,
    sud_id: int,
    restextrakt: float | None = None,
    temp: float | None = None,
    bemerkung: str | None = None,
) -> None:
    """Gärung beenden: optional letzter Messwert, dann Status „abgefüllt“.

    Wie TabAbfuellen::on_btnSudAbgefuellt_clicked: Abfülldatum, ReifungStart,
    Status und erster Eintrag im Nachgärverlauf (Druck 0, Temperatur Jungbier).
    """
    now = jetzt()

    def fn(conn):
        sud = _get_sud(conn, sud_id, STATUS_GEBRAUT)
        if restextrakt is not None:
            t = temp if temp is not None else (sud["TemperaturJungbier"] or 18.0)
            # Der letzte Wert muss der jüngste sein, auch wenn ein Eintrag (falsche Uhr
            # am PC) in der Zukunft liegt – sonst würde SW Jungbier nicht übernommen.
            zeiten = [
                _parse_dt(r["Zeitstempel"]) for r in conn.execute(
                    "SELECT Zeitstempel FROM Hauptgaerverlauf WHERE SudID = ?", (sud_id,)
                )
            ]
            spaetester = max((z for z in zeiten if z), default=None)
            zeit = now if spaetester is None or spaetester < now else spaetester + timedelta(minutes=1)
            _insert_messwert(conn, sud, restextrakt, t, bemerkung, zeit)
            sud = _get_sud(conn, sud_id)
        abf = _parse_dt(sud["Abfuelldatum"]) or now
        reifung = _parse_dt(sud["ReifungStart"]) or now
        _update_sud(conn, sud_id, {
            "Abfuelldatum": _format_dt(abf),
            "ReifungStart": _format_dt(reifung),
            "Status": STATUS_ABGEFUELLT,
        })
        n = conn.execute("SELECT count(*) FROM Nachgaerverlauf WHERE SudID = ?", (sud_id,)).fetchone()[0]
        if n == 0:
            t = sud["TemperaturJungbier"] or 18.0
            conn.execute(
                "INSERT INTO Nachgaerverlauf (SudID, Zeitstempel, Druck, Temp, CO2) VALUES (?, ?, 0, ?, ?)",
                (sud_id, _format_dt(abf), t, co2(0.0, t)),
            )

    _write_tx(path, fn)


def verbraucht(path: str, sud_id: int) -> None:
    """Sud als ausgetrunken markieren (TabAbfuellen::on_btnSudVerbraucht_clicked)."""

    def fn(conn):
        _get_sud(conn, sud_id, STATUS_ABGEFUELLT)
        _update_sud(conn, sud_id, {"Status": STATUS_VERBRAUCHT})

    _write_tx(path, fn)


# --------------------------------------------------------------------------
# Sud-Details (Lebenslauf, Brautag-Assistent, Zutaten, Proben, Bewertungen)
# --------------------------------------------------------------------------

EINHEITEN = {0: "kg", 1: "g", 2: "mg", 3: "Stk", 4: "l", 5: "ml"}
RAST_TYP = {0: "Einmaischen", 1: "Aufheizen", 2: "Zubrühen", 3: "Zuschütten", 4: "Dekoktion"}
HOPFEN_ZEITPUNKT = {0: "Kochen", 1: "Vorderwürze", 2: "Kochbeginn", 3: "Kochen", 4: "Kochende", 5: "Ausschlagen"}
ZUSATZ_ZEITPUNKT = {0: "Gärung", 1: "Kochen", 2: "Maischen"}
ZUSATZ_STATUS = {0: "offen", 1: "zugegeben", 2: "entnommen"}

BEWERTUNG_FELDER = (
    "Farbe", "Schaum", "Geruch", "Geschmack", "Antrunk", "Haupttrunk", "Nachtrunk", "Gesamteindruck",
)


def _opt(row: sqlite3.Row, key: str, default=None):
    return row[key] if key in row.keys() else default


def _tage(von: datetime | None, bis: datetime | None) -> int | None:
    """Wie QDateTime::daysTo: Kalendertage (Mitternachten) zwischen zwei Zeitpunkten."""
    if von is None or bis is None:
        return None
    return (bis.date() - von.date()).days


def _rows(conn: sqlite3.Connection, sql: str, *args) -> list[sqlite3.Row]:
    return conn.execute(sql, args).fetchall()


def get_sud_details(path: str, sud_id: int) -> dict:
    """Alles zu einem Sud, was Brauhelfer-Seite und Assistent brauchen."""
    conn = _connect(path, readonly=True)
    try:
        check_schema(conn)
        sud = _get_sud(conn, sud_id)
        braudatum = _parse_dt(sud["Braudatum"]) if sud["Status"] >= STATUS_GEBRAUT else None
        sw_ist = _sw_ist(conn, sud)

        zutaten = []
        for z in _rows(conn, "SELECT * FROM WeitereZutatenGaben WHERE SudID = ? ORDER BY ID", sud_id):
            zp = z["Zeitpunkt"]
            einheit = EINHEITEN.get(z["Einheit"], "")
            menge = z["erg_Menge"] or 0.0  # g bzw. ml bzw. Stk (Gesamtmenge)
            item = {
                "id": z["ID"],
                "name": z["Name"],
                "typ": z["Typ"],
                "hopfen": z["Typ"] == _ZUSATZ_TYP_HOPFEN,
                "zeitpunkt": zp,
                "zeitpunkt_text": ZUSATZ_ZEITPUNKT.get(zp, str(zp)),
                "menge": menge,
                "einheit": {"kg": "g", "mg": "g", "l": "ml"}.get(einheit, einheit),
                "status": z["Zugabestatus"] or 0,
                "status_text": ZUSATZ_STATUS.get(z["Zugabestatus"] or 0, ""),
                "mit_entnahme": (z["Entnahmeindex"] or 0) == 0,
                "bemerkung": z["Bemerkung"],
            }
            if zp == _ZUSATZ_ZEITPUNKT_GAERUNG:
                item["zugabe_nach_tagen"] = z["ZugabeNach"] or 0
                item["dauer_tage"] = round((z["Zugabedauer"] or 0) / 1440, 1)
                if braudatum:
                    zug = braudatum + timedelta(days=item["zugabe_nach_tagen"])
                    item["zugabe_datum"] = _format_dt(zug)
                    if item["dauer_tage"] > 0:
                        item["entnahme_datum"] = _format_dt(zug + timedelta(minutes=z["Zugabedauer"] or 0))
            elif zp == _ZUSATZ_ZEITPUNKT_KOCHEN:
                item["kochdauer_min"] = z["Zugabedauer"] or 0
            zutaten.append(item)

        hefe = [
            {
                "id": h["ID"], "name": h["Name"], "menge": h["Menge"] or 0,
                "zugegeben": bool(h["Zugegeben"]), "zugabe_nach_tagen": h["ZugabeNach"] or 0,
            }
            for h in _rows(conn, "SELECT * FROM Hefegaben WHERE SudID = ? ORDER BY ID", sud_id)
        ]

        def verlauf(table: str, cols: tuple[str, ...]) -> list[dict]:
            out = []
            for r in _rows(conn, f"SELECT * FROM {table} WHERE SudID = ?", sud_id):
                d = {"zeit": _format_dt(_parse_dt(r["Zeitstempel"])) if _parse_dt(r["Zeitstempel"]) else None}
                for c in cols:
                    d[c.lower()] = r[c]
                out.append(d)
            return sorted(out, key=lambda x: x["zeit"] or "")

        reifung = _parse_dt(sud["ReifungStart"]) or _parse_dt(sud["Abfuelldatum"])
        bewertungen = []
        for b in _rows(conn, "SELECT * FROM Bewertungen WHERE SudID = ? ORDER BY Datum", sud_id):
            datum = _parse_dt(b["Datum"])
            d = {
                "id": b["ID"],
                "datum": _format_dt(datum) if datum else None,
                "woche": (_tage(reifung, datum) // 7 + 1) if reifung and datum else 0,
                "sterne": b["Sterne"] or 0,
                "bemerkung": b["Bemerkung"] or "",
            }
            for f in BEWERTUNG_FELDER:
                d[f.lower()] = b[f] or 0
                d[f.lower() + "_bemerkung"] = b[f + "Bemerkung"] or ""
            bewertungen.append(d)

        return {
            "id": sud_id,
            "name": sud["Sudname"],
            "status": sud["Status"],
            "kategorie": sud["Kategorie"],
            "erstellt": _format_dt(_parse_dt(sud["Erstellt"])) if _parse_dt(_opt(sud, "Erstellt")) else None,
            "braudatum": _format_dt(braudatum) if braudatum else None,
            "abfuelldatum": _format_dt(_parse_dt(sud["Abfuelldatum"])) if sud["Status"] >= STATUS_ABGEFUELLT and _parse_dt(sud["Abfuelldatum"]) else None,
            "reifung_start": _format_dt(reifung) if reifung and sud["Status"] >= STATUS_ABGEFUELLT else None,
            "reifezeit_wochen": _opt(sud, "Reifezeit", 0) or 0,
            "menge": sud["Menge"] or 0.0,
            "sw": sud["SW"] or 0.0,
            "sw_ist": sw_ist,
            "sw_jungbier": sud["SWJungbier"] or 0.0,
            "kochdauer": sud["Kochdauer"] or 0,
            "nachisomerisierung": _opt(sud, "Nachisomerisierungszeit", 0) or 0,
            "hauptguss": _opt(sud, "erg_WHauptguss", 0.0) or 0.0,
            "nachguss": _opt(sud, "erg_WNachguss", 0.0) or 0.0,
            "schuettung": sud["erg_S_Gesamt"] or 0.0,
            "co2_soll": sud["CO2"] or 0.0,
            "spunden": bool(_opt(sud, "Spunden", 0)),
            "schnellgaerprobe_aktiv": bool(sud["SchnellgaerprobeAktiv"]),
            "sw_schnellgaerprobe": sud["SWSchnellgaerprobe"] or 0.0,
            "vergaerungsgrad": sud["Vergaerungsgrad"] or 0.0,
            "bemerkung_brauen": sud["BemerkungBrauen"] or "",
            "malz": [
                {"name": m["Name"], "menge_kg": m["erg_Menge"] or 0.0, "prozent": m["Prozent"] or 0.0}
                for m in _rows(conn, "SELECT * FROM Malzschuettung WHERE SudID = ? ORDER BY ID", sud_id)
            ],
            "maischplan": [
                {
                    "id": m["ID"], "typ": m["Typ"], "typ_text": RAST_TYP.get(m["Typ"], ""), "name": m["Name"],
                    "temp_wasser": m["TempWasser"] or 0.0, "temp_rast": m["TempRast"] or 0.0,
                    "dauer": m["DauerRast"] or 0, "temp_extra1": m["TempExtra1"] or 0.0,
                    "dauer_extra1": m["DauerExtra1"] or 0, "temp_extra2": m["TempExtra2"] or 0.0,
                    "dauer_extra2": m["DauerExtra2"] or 0,
                }
                for m in _rows(conn, "SELECT * FROM Maischplan WHERE SudID = ? ORDER BY ID", sud_id)
            ],
            "hopfen": [
                {
                    "id": h["ID"], "name": h["Name"], "menge_g": h["erg_Menge"] or 0.0, "alpha": h["Alpha"] or 0.0,
                    "zeit": h["Zeit"] or 0, "zeitpunkt": h["Vorderwuerze"] or 0,
                    "zeitpunkt_text": HOPFEN_ZEITPUNKT.get(h["Vorderwuerze"] or 0, ""),
                }
                for h in _rows(conn, "SELECT * FROM Hopfengaben WHERE SudID = ? ORDER BY ID", sud_id)
            ],
            "zutaten": zutaten,
            "hefe": hefe,
            "hauptgaerverlauf": verlauf("Hauptgaerverlauf", ("Restextrakt", "Alc", "Temp", "Bemerkung")),
            # Der Eintrag zum Brautag (Anstellwürze, vom „Sud gebraut“ angelegt) ist keine Probe
            "schnellgaerverlauf": [
                m for m in verlauf("Schnellgaerverlauf", ("Restextrakt", "Alc", "Temp", "Bemerkung"))
                if not (
                    braudatum and m["zeit"] == _format_dt(braudatum)
                    and abs((m["restextrakt"] or 0) - sw_ist) < 0.05
                )
            ],
            "nachgaerverlauf": verlauf("Nachgaerverlauf", ("Druck", "Temp", "CO2", "Bemerkung")),
            "bewertungen": bewertungen,
        }
    finally:
        conn.close()


def zutat_zugeben(path: str, zutat_id: int, datum: datetime | None = None) -> None:
    """Weitere Zutat (auch Hopfenstopfen) als zugegeben markieren.

    Wie TabGaerverlauf1: ZugabeNach = Tage seit Brautag bis heute, Status „zugegeben“.
    """
    def fn(conn):
        z = conn.execute("SELECT * FROM WeitereZutatenGaben WHERE ID = ?", (zutat_id,)).fetchone()
        if z is None:
            raise BrauhelferError("Zutat nicht gefunden")
        sud = _get_sud(conn, z["SudID"], STATUS_GEBRAUT)
        if (z["Zugabestatus"] or 0) != _ZUSATZ_STATUS_NICHT_ZUGEGEBEN:
            raise BrauhelferError(f"„{z['Name']}“ ist bereits zugegeben")
        brau = _parse_dt(sud["Braudatum"])
        nach = _tage(brau, datum or jetzt())
        conn.execute(
            "UPDATE WeitereZutatenGaben SET Zugabestatus = 1, ZugabeNach = ? WHERE ID = ?",
            (nach if nach is not None else z["ZugabeNach"], zutat_id),
        )
        _update_sud(conn, sud["ID"], {})

    _write_tx(path, fn)


def zutat_entnehmen(path: str, zutat_id: int, datum: datetime | None = None) -> None:
    """Zutat entnehmen (z. B. Hopfensack raus): Zugabedauer = Tage seit Zugabe in Minuten."""
    def fn(conn):
        z = conn.execute("SELECT * FROM WeitereZutatenGaben WHERE ID = ?", (zutat_id,)).fetchone()
        if z is None:
            raise BrauhelferError("Zutat nicht gefunden")
        sud = _get_sud(conn, z["SudID"], STATUS_GEBRAUT)
        if (z["Zugabestatus"] or 0) != 1:
            raise BrauhelferError(f"„{z['Name']}“ ist nicht im Status zugegeben")
        brau = _parse_dt(sud["Braudatum"])
        zug = brau + timedelta(days=z["ZugabeNach"] or 0) if brau else None
        tage = _tage(zug, datum or jetzt())
        conn.execute(
            "UPDATE WeitereZutatenGaben SET Zugabestatus = 2, Zugabedauer = ? WHERE ID = ?",
            ((tage or 0) * 1440 if tage is not None else z["Zugabedauer"], zutat_id),
        )
        _update_sud(conn, sud["ID"], {})

    _write_tx(path, fn)


def hefe_zugeben(path: str, hefe_id: int, datum: datetime | None = None) -> None:
    def fn(conn):
        h = conn.execute("SELECT * FROM Hefegaben WHERE ID = ?", (hefe_id,)).fetchone()
        if h is None:
            raise BrauhelferError("Hefegabe nicht gefunden")
        sud = _get_sud(conn, h["SudID"], STATUS_REZEPT, STATUS_GEBRAUT)
        brau = _parse_dt(sud["Braudatum"]) or jetzt()
        nach = _tage(brau, datum or jetzt()) or 0
        conn.execute("UPDATE Hefegaben SET Zugegeben = 1, ZugabeNach = ? WHERE ID = ?", (max(nach, 0), hefe_id))

    _write_tx(path, fn)


def add_schnellgaer(path: str, sud_id: int, restextrakt: float, temp: float, bemerkung: str | None = None) -> None:
    """Schnellgärprobe eintragen (ModelSchnellgaerverlauf::setDataExt)."""
    zeit = jetzt()

    def fn(conn):
        sud = _get_sud(conn, sud_id, STATUS_GEBRAUT)
        alc = alkohol(_sw_ist(conn, sud), restextrakt)
        conn.execute(
            "INSERT INTO Schnellgaerverlauf (SudID, Zeitstempel, Restextrakt, Alc, Temp, Bemerkung) VALUES (?, ?, ?, ?, ?, ?)",
            (sud_id, _format_dt(zeit), round(restextrakt, 2), alc, round(temp, 1), bemerkung),
        )
        zeiten = [_parse_dt(r[0]) for r in conn.execute("SELECT Zeitstempel FROM Schnellgaerverlauf WHERE SudID = ?", (sud_id,))]
        if zeit >= max((z for z in zeiten if z), default=zeit):
            _update_sud(conn, sud_id, {"SWSchnellgaerprobe": round(restextrakt, 2), "SchnellgaerprobeAktiv": 1})

    _write_tx(path, fn)


def add_nachgaer(path: str, sud_id: int, druck: float, temp: float, bemerkung: str | None = None) -> None:
    """Nachgärung: Druck (bar) und Temperatur, CO₂ wie ModelNachgaerverlauf."""
    zeit = jetzt()

    def fn(conn):
        _get_sud(conn, sud_id, STATUS_ABGEFUELLT)
        conn.execute(
            "INSERT INTO Nachgaerverlauf (SudID, Zeitstempel, Druck, Temp, CO2, Bemerkung) VALUES (?, ?, ?, ?, ?, ?)",
            (sud_id, _format_dt(zeit), round(druck, 2), round(temp, 1), co2(druck, temp), bemerkung),
        )

    _write_tx(path, fn)


def add_bewertung(path: str, sud_id: int, werte: dict) -> int:
    """Verkostung speichern (Tabelle Bewertungen, Bitmasken wie DlgBewertungen)."""
    zeit = jetzt()

    def fn(conn):
        sud = _get_sud(conn, sud_id, STATUS_ABGEFUELLT, STATUS_VERBRAUCHT)
        reifung = _parse_dt(sud["ReifungStart"]) or _parse_dt(sud["Abfuelldatum"])
        woche = (_tage(reifung, zeit) // 7 + 1) if reifung else 0
        cols = {"SudID": sud_id, "Datum": _format_dt(zeit), "Woche": woche,
                "Sterne": max(0, min(5, int(werte.get("sterne", 0)))), "Bemerkung": str(werte.get("bemerkung", ""))}
        for f in BEWERTUNG_FELDER:
            cols[f] = int(werte.get(f.lower(), 0)) & 0xFFFF
            cols[f + "Bemerkung"] = str(werte.get(f.lower() + "_bemerkung", ""))
        names = ", ".join(cols)
        marks = ", ".join("?" for _ in cols)
        cur = conn.execute(f"INSERT INTO Bewertungen ({names}) VALUES ({marks})", tuple(cols.values()))
        return cur.lastrowid

    return _write_tx(path, fn)


# --------------------------------------------------------------------------
# Lager (Modul Lagerverwaltung im Brauhelfer)
# --------------------------------------------------------------------------
# Einheiten wie im Brauhelfer: Malz in kg, Hopfen in g, Hefe in Stück,
# weitere Zutaten normiert in g/ml/Stk (ModelWeitereZutaten::ColMengeNormiert).

LAGER_TABELLE = {"malz": "Malz", "hopfen": "Hopfen", "hefe": "Hefe", "zusatz": "WeitereZutaten"}
LAGER_EINHEIT = {"malz": "kg", "hopfen": "g", "hefe": "Stk"}
_NORM = {0: 1000.0, 1: 1.0, 2: 0.001, 3: 1.0, 4: 1000.0, 5: 1.0}  # Einheit -> Faktor auf g/ml/Stk
_NORM_EINHEIT = {0: "g", 1: "g", 2: "g", 3: "Stk", 4: "ml", 5: "ml"}


def _lager_zeile(conn: sqlite3.Connection, typ: str, name: str) -> sqlite3.Row | None:
    return conn.execute(f"SELECT * FROM {LAGER_TABELLE[typ]} WHERE Name = ?", (name,)).fetchone()


def _vorhanden(row: sqlite3.Row | None, typ: str) -> float | None:
    if row is None:
        return None
    if typ == "zusatz":
        return (row["Menge"] or 0.0) * _NORM.get(row["Einheit"] or 0, 1.0)
    return float(row["Menge"] or 0)


def _posten(conn: sqlite3.Connection, typ: str, name: str, menge: float, spaeter: bool = False,
            einheit: str | None = None) -> dict:
    row = _lager_zeile(conn, typ, name)
    vorhanden = _vorhanden(row, typ)
    if einheit is None:
        einheit = LAGER_EINHEIT.get(typ) or (_NORM_EINHEIT.get(row["Einheit"], "g") if row is not None else "g")
    return {
        "typ": typ, "name": name, "menge": round(menge, 3), "einheit": einheit,
        "vorhanden": round(vorhanden, 3) if vorhanden is not None else None,
        "gefunden": row is not None, "spaeter": spaeter,
        "fehlt": max(0.0, round(menge - (vorhanden or 0.0), 3)) if not spaeter else 0.0,
    }


def lager_bedarf(path: str, sud_id: int) -> list[dict]:
    """Was beim Brauen abgezogen wird – wie DlgRohstoffeAbziehen mit „alle Brauzutaten“.

    Hopfen und Zutaten zur Gärung mit Zugabe nach Tag 0 und Hefe mit späterer
    Zugabe werden mit Menge 0 und `spaeter` aufgeführt: sie werden erst beim
    Abhaken der Zugabe abgezogen.
    """
    conn = _connect(path, readonly=True)
    try:
        check_schema(conn)
        _get_sud(conn, sud_id)
        return _bedarf(conn, sud_id)
    finally:
        conn.close()


def _bedarf(conn: sqlite3.Connection, sud_id: int) -> list[dict]:
    if True:
        out: list[dict] = []
        summe: dict[tuple[str, str], float] = {}
        spaeter: set[tuple[str, str]] = set()

        for m in _rows(conn, "SELECT Name, erg_Menge FROM Malzschuettung WHERE SudID = ? ORDER BY ID", sud_id):
            summe[("malz", m["Name"])] = summe.get(("malz", m["Name"]), 0.0) + (m["erg_Menge"] or 0.0)
        for h in _rows(conn, "SELECT Name, erg_Menge FROM Hopfengaben WHERE SudID = ? ORDER BY ID", sud_id):
            summe[("hopfen", h["Name"])] = summe.get(("hopfen", h["Name"]), 0.0) + (h["erg_Menge"] or 0.0)
        for z in _rows(conn, "SELECT * FROM WeitereZutatenGaben WHERE SudID = ? ORDER BY ID", sud_id):
            typ = "hopfen" if z["Typ"] == _ZUSATZ_TYP_HOPFEN else "zusatz"
            key = (typ, z["Name"])
            if z["Zeitpunkt"] != _ZUSATZ_ZEITPUNKT_GAERUNG or (z["ZugabeNach"] or 0) == 0:
                summe[key] = summe.get(key, 0.0) + (z["erg_Menge"] or 0.0)
            else:
                spaeter.add(key)
        for h in _rows(conn, "SELECT Name, Menge, ZugabeNach FROM Hefegaben WHERE SudID = ? ORDER BY ID", sud_id):
            key = ("hefe", h["Name"])
            if (h["ZugabeNach"] or 0) == 0:
                summe[key] = summe.get(key, 0.0) + (h["Menge"] or 0)
            else:
                spaeter.add(key)

        for (typ, name), menge in summe.items():
            out.append(_posten(conn, typ, name, menge))
        for typ, name in spaeter:
            if (typ, name) not in summe:
                out.append(_posten(conn, typ, name, 0.0, spaeter=True))
        reihenfolge = {"malz": 0, "hopfen": 1, "hefe": 2, "zusatz": 3}
        out.sort(key=lambda p: (reihenfolge[p["typ"]], p["spaeter"]))
        return out


def lager_bedarf_zugabe(path: str, art: str, item_id: int) -> list[dict]:
    """Abzug für eine einzelne Zugabe in der Gärung (Zutat/Hopfen oder Hefe)."""
    conn = _connect(path, readonly=True)
    try:
        check_schema(conn)
        if art == "hefe":
            h = conn.execute("SELECT * FROM Hefegaben WHERE ID = ?", (item_id,)).fetchone()
            if h is None:
                raise BrauhelferError("Hefegabe nicht gefunden")
            return [_posten(conn, "hefe", h["Name"], h["Menge"] or 0)]
        z = conn.execute("SELECT * FROM WeitereZutatenGaben WHERE ID = ?", (item_id,)).fetchone()
        if z is None:
            raise BrauhelferError("Zutat nicht gefunden")
        typ = "hopfen" if z["Typ"] == _ZUSATZ_TYP_HOPFEN else "zusatz"
        return [_posten(conn, typ, z["Name"], z["erg_Menge"] or 0.0)]
    finally:
        conn.close()


def lager_abziehen(path: str, posten: list[dict], zurueck: bool = False) -> list[dict]:
    """Bestände reduzieren (oder bei `zurueck` wieder gutschreiben).

    Wie Brauhelfer::rohstoffAbziehen: Name muss exakt passen, Bestand nie unter 0,
    weitere Zutaten in der Lager-Einheit umgerechnet, Stückzahlen aufgerundet.
    Gibt die gebuchten Posten mit neuem Bestand zurück.
    """
    import math  # noqa: PLC0415

    def fn(conn):
        gebucht = []
        for p in posten:
            typ, name, menge = p["typ"], p["name"], float(p["menge"])
            if typ not in LAGER_TABELLE or menge <= 0:
                continue
            row = _lager_zeile(conn, typ, name)
            if row is None:
                continue
            delta = -menge if zurueck else menge
            if typ == "zusatz":
                einheit = row["Einheit"] or 0
                if einheit == _EINHEIT_STK:
                    delta = math.copysign(math.ceil(abs(delta)), delta)
                else:
                    delta = delta / _NORM.get(einheit, 1.0)
            elif typ == "hefe":
                delta = math.copysign(math.ceil(abs(delta)), delta)
            neu = max(0.0, (row["Menge"] or 0.0) - delta)
            if typ == "hefe":
                neu = int(neu)
            conn.execute(f"UPDATE {LAGER_TABELLE[typ]} SET Menge = ? WHERE ID = ?", (neu, row["ID"]))
            gebucht.append({"typ": typ, "name": name, "menge": menge, "neu": _vorhanden(
                conn.execute(f"SELECT * FROM {LAGER_TABELLE[typ]} WHERE ID = ?", (row["ID"],)).fetchone(), typ)})
        return gebucht

    return _write_tx(path, fn)
