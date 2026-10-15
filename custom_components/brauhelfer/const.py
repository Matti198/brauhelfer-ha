"""Konstanten für die Kleiner-Brauhelfer-Integration."""

from datetime import timedelta

DOMAIN = "brauhelfer"

CONF_PATH = "path"
CONF_GRAVITY_ENTITY = "gravity_entity"
CONF_TEMPERATURE_ENTITY = "temperature_entity"
CONF_INTERVAL = "interval"
CONF_BACKUPS = "backups"
CONF_MAX_AGE = "max_age"

DEFAULT_PATH = "/share/brauhelfer/kb_daten.sqlite"
DEFAULT_INTERVAL = 240  # Minuten zwischen zwei automatischen Einträgen
DEFAULT_BACKUPS = 20  # Anzahl Sicherungen, die behalten werden
DEFAULT_MAX_AGE = 120  # Minuten: ältere Pill-Werte werden nicht eingetragen

SCAN_INTERVAL = timedelta(seconds=60)  # Datei auf Änderungen prüfen
CHECK_INTERVAL = timedelta(minutes=5)  # prüfen, ob eine Aufzeichnung fällig ist

BEMERKUNG_AUTO = "RAPT Pill (Home Assistant)"
BEMERKUNG_MANUELL = "Home Assistant"

NO_SUD = "Kein Sud"

SERVICE_MESSWERT = "messwert_eintragen"
ATTR_SUD_ID = "sud_id"
ATTR_RESTEXTRAKT = "restextrakt"
ATTR_DICHTE = "dichte"
ATTR_TEMPERATUR = "temperatur"
ATTR_BEMERKUNG = "bemerkung"
ATTR_ENTRY_ID = "config_entry_id"

# Plausibilitätsgrenzen für Pill-Werte
SG_MIN, SG_MAX = 0.980, 1.150
PLATO_MIN, PLATO_MAX = -5.0, 35.0
TEMP_MIN, TEMP_MAX = -5.0, 45.0
