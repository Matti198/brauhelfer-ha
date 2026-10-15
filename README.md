# Kleiner Brauhelfer für Home Assistant

[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz) [![Prüfen](https://github.com/Matti198/brauhelfer-ha/actions/workflows/validate.yml/badge.svg)](https://github.com/Matti198/brauhelfer-ha/actions/workflows/validate.yml)

Eigene Integration für die Datenbank des [kleinen Brauhelfers 2](https://github.com/kleiner-brauhelfer/kleiner-brauhelfer-2). Die Datenbank liegt auf dem HA-Server, der Brauhelfer am PC greift per Samba darauf zu, und in der HA-Seitenleiste gibt es eine eigene Seite **Brauhelfer** – auch in der iOS-App.

**Was sie kann**

- Reiter **Geplant → Gärung → Gebraut** mit allen Suden, jeder mit Glas in seiner Bierfarbe
- **Brautag-Assistent**: Schritt für Schritt aus Maischplan, Hopfengaben und Zutaten, mit Timern, Erinnerungen und Ansagen über Sonos oder Music Assistant (z. B. „Jetzt zugeben: 9 g Magnum“)
- **Gärverlauf per RAPT Pill**: Pill pro Sud wählen, „Aufzeichnung starten“. Eingetragen wird der Median der letzten Minuten (Ausreißer fliegen raus), auf Wunsch mit Spindel-Abgleich
- **Gär-Prognose**: „voraussichtlich fertig am Sa., 17. Okt.“ aus dem bisherigen Verlauf (Endwert aus Schnellgärprobe oder Rezept)
- **Zutaten & Hopfenstopfen** als zugegeben/entnommen markieren, **Schnellgärprobe**, **Nachgärung** (Druck → CO₂)
- **Gärschrank-Regelung**: Kühlung und Heizung über Steckdosen, Temperaturprofil nach Vergärungsgrad (z. B. Diacetylrast ab 70 %)
- **Fässer**: Leergewicht, Wiegen (Waage-Sensor oder von Hand), NFC-Tags pro Glasgröße – Scan mit dem iPhone zieht ein Glas ab
- **Verkostung** mit denselben Kategorien wie im Brauhelfer
- **Lager**: Rohstoffe nach dem Brauen und beim Zugeben abziehen wie im Brauhelfer, fehlende Rohstoffe auf die Einkaufsliste
- **Lebenslauf** pro Sud: alles vom Rezept bis zum letzten Glas auf einer Zeitleiste
- **Meldungen aufs iPhone**: Gärung steht, Ziel erreicht, Temperatur daneben, Pill offline/Akku, Hopfenstopfen fällig, Fass fast leer, Brautag-Timer. Bei „Gärung steht“ und „Ziel erreicht“ direkt aus der Meldung „Gärung fertig“ oder „Noch 2 Tage warten“ wählen (Mitteilung gedrückt halten)

Alles, was in die Datenbank geschrieben wird, rechnet HA wie das Desktop-Programm (aus dessen Quellcode übernommen). Vor jedem Schreiben wird eine Sicherung angelegt. Getestet mit Datenbankversion 2009 (kleiner-brauhelfer 2.6).

---

## 1. Datenbank auf den HA-Server legen (Samba)

1. Add-on **Samba share** installieren, Benutzer/Passwort setzen, starten.
2. Am PC `\\homeassistant.local\share` öffnen, Ordner `brauhelfer` anlegen.
3. **Brauhelfer am PC schließen**, `kb_daten.sqlite` nach `share\brauhelfer\` kopieren.
4. Freigabe als Netzlaufwerk verbinden (z. B. `B:`), im Brauhelfer unter Einstellungen → Datenbank `B:\brauhelfer\kb_daten.sqlite` wählen.
5. Die alte Datei (z. B. in der Dropbox) umbenennen, damit nicht zwei Stände entstehen.

## 2. Integration installieren

**Mit HACS (empfohlen)**
1. HACS → Menü oben rechts (⋮) → **Benutzerdefinierte Repositories**.
2. Repository `https://github.com/Matti198/brauhelfer-ha`, Typ **Integration**, hinzufügen.
3. „Kleiner Brauhelfer“ in HACS suchen → **Herunterladen** → HA neu starten.
4. **Einstellungen → Geräte & Dienste → Integration hinzufügen → „Kleiner Brauhelfer“**, Pfad `/share/brauhelfer/kb_daten.sqlite`.

Neue Versionen erscheinen danach in HA unter **Einstellungen → Updates**. Installieren, neu starten, fertig.

**Von Hand**: `custom_components/brauhelfer` nach `/config/custom_components/brauhelfer` kopieren – bei einem Update den alten Ordner vorher löschen – und HA neu starten.

Unter **Konfigurieren**: Intervall der Pill-Aufzeichnung (Standard 4 h), Höchstalter der Pill-Werte, Anzahl Sicherungen.

## 3. Einrichten auf der Brauhelfer-Seite

**Zahnrad oben rechts → Einstellungen**
- *Push aufs Handy*: dein iPhone (`mobile_app_…`) auswählen. „Testmeldung“ prüft es.
- *Ansagen am Brautag*: Lautsprecher wählen (Sonos, Music Assistant, …), dazu Stimme und Lautstärke. Voraussetzung ist eine Sprachausgabe in HA (Einstellungen → Sprachassistenten, z. B. Piper oder Home Assistant Cloud). Bei Sonos und Music Assistant wird laufende Musik für die Ansage nur leiser. Taucht ein Lautsprecher doppelt auf (einmal Sonos, einmal Music Assistant), nur einen wählen.
- *Worüber melden* und *Schwellen* nach Geschmack.
- *Gärschränke*: Temperatursensor, Steckdose Kühlung, Steckdose Heizung, Schaltabstand, Kompressorpause.

**Pill**: Integration „RAPT Bluetooth“ muss laufen. Die Pill erscheint dann bei jedem Sud in Gärung zur Auswahl. Unter *Einstellungen → Pill* stellst du die Glättung ein (Standard 30 min; braucht den Recorder, der in HA standardmäßig läuft). Zum Abgleich beim Sud „Aufzeichnung → Abgleichen“: Spindelwert eintragen, HA merkt sich die Abweichung pro Pill. Während der Gärung kein Refraktometer verwenden – der Alkohol verfälscht die Anzeige.

**NFC-Tags**: Beim Fass „NFC-Tag“ → Glasgröße eintragen → „Scannen“ → innerhalb von 3 Minuten den Tag mit der HA-App scannen. Oder einen bereits in HA angelegten Tag aus der Liste wählen. Jeder weitere Scan zieht ein Glas ab.

## Ablauf eines Suds

1. **Geplant**: Rezept im Brauhelfer auf die Merkliste setzen → „Brautag starten“.
2. **Brautag**: Schritte abarbeiten, Timer starten, Messwerte eintragen, Hefe als angestellt markieren, „Sud gebraut“.
3. **Gärung**: Pill wählen → „Aufzeichnung starten“. Optional Gärschrank zuordnen. Hopfenstopfen/Zutaten abhaken, Schnellgärprobe eintragen.
4. **Gärung fertig**: letzter Wert (°P oder SG) oder ohne → der Sud wird abgefüllt gesetzt, Aufzeichnung und Regelung enden.
5. **Gebraut**: Fässer anlegen, Gläser per NFC, Wiegen, Nachgärung, Verkostung.
6. **Leer**: Sud wird auf „verbraucht“ gesetzt.

## Entitäten

| Entität | Bedeutung |
|---|---|
| `sensor.kleiner_brauhelfer_sud_<name>` | je geplantem/gärendem Sud, Details als Attribute |
| `sensor.kleiner_brauhelfer_aktuelle_sude` | Anzahl, Listen als Attribute |
| `sensor.kleiner_brauhelfer_fass_<name>` | Restmenge in Litern (für Dashboards, Automationen) |
| `sensor.kleiner_brauhelfer_garschrank_<name>` | Zustand der Regelung, Soll/Ist als Attribute |
| `sensor.kleiner_brauhelfer_aufzeichnung_*` | Werte des Suds mit laufender Aufzeichnung |
| `sensor.kleiner_brauhelfer_letzter_garverlauf_eintrag` | letzter Eintrag, Fehler als Attribut |
| `button.kleiner_brauhelfer_laufende_aufzeichnungen_jetzt_eintragen` | sofort eintragen |

Ereignis `brauhelfer_glas` (bei jedem abgezogenen Glas) – z. B. für eine Automation „Prost“-Ansage.

Dienst `brauhelfer.messwert_eintragen` (Restextrakt oder Dichte, Temperatur; ohne `sud_id` der Sud mit laufender Aufzeichnung).

## Was man wissen sollte

- **Sicherheit Gärschrank**: Fällt der Temperatursensor aus oder wird die Regelung beendet, gehen beide Steckdosen aus. Kühlung und Heizung sind nie gleichzeitig an.
- **Gleichzeitig am PC arbeiten**: Der Brauhelfer schreibt beim Speichern nur geänderte Felder. Einträge von HA bleiben erhalten, erscheinen am PC aber erst nach Speichern/Neuöffnen.
- **Lager** (Einstellungen → „Lager führen“): Nach „Sud gebraut“ öffnet sich ein Dialog mit den Rezeptmengen und dem Lagerbestand; Mengen sind änderbar, „Abziehen“ bucht sie im Brauhelfer ab. Hopfenstopfen, Gärungszutaten und später zugegebene Hefe werden erst beim „Zugegeben“ abgezogen. Geplante Sude zeigen fehlende Rohstoffe, „Auf die Einkaufsliste“ setzt sie auf eine HA-Einkaufsliste. Zugeordnet wird über den **exakten Namen** wie im Brauhelfer, der Bestand geht nie unter 0. Im Brauhelfer am PC dann **nicht zusätzlich** abziehen.
- **Sicherungen**: `share/brauhelfer/backup/` – die letzten N plus 30 Tage lang eine pro Tag.
- **Daten außerhalb der Datenbank** (Fässer, Tags, Gärschränke, Einstellungen, Brautag-Sitzung) liegen in HA unter `.storage/brauhelfer.*` und sind im HA-Backup enthalten.

## Entwicklung und Releases

- Tests: `pip install -r requirements_test.txt && pytest tests`
- Neue Version: `version` in `custom_components/brauhelfer/manifest.json` erhöhen, committen, Tag `vX.Y.Z` pushen. Die GitHub-Action legt das Release an, HACS zeigt das Update.

## Lizenz

Copyright (C) 2026 Matti198

Dieses Programm ist freie Software unter der [GNU General Public License Version 3](LICENSE). Es wird ohne jede Gewährleistung bereitgestellt.

Die Berechnungen (Alkohol, Vergärungsgrad, Dichte, Sudhausausbeute, Rohstoffabzug …) sind aus dem Quellcode des [kleinen Brauhelfers 2](https://github.com/kleiner-brauhelfer/kleiner-brauhelfer-2) übernommen, der ebenfalls unter GPL-3.0 steht. `tests/kb_daten.sqlite` ist unverändert die Beispieldatenbank aus diesem Projekt. Dank an die Entwickler des kleinen Brauhelfers.

Dies ist ein privates, inoffizielles Projekt und gehört nicht zum kleinen Brauhelfer.
