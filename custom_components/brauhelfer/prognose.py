"""Gär-Prognose: Wann ist der Sud voraussichtlich durchgegoren?

Die Hauptgärung folgt grob einer S-Kurve (logistisch) von der Stammwürze zum
Endwert. Aus den Messwerten der letzten Tage werden Steilheit und Wendepunkt
geschätzt und daraus der Zeitpunkt berechnet, an dem der Restextrakt weniger als
FERTIG_ABSTAND über dem Endwert liegt.

Endwert: Schnellgärprobe, falls vorhanden, sonst der Rezept-Vergärungsgrad.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

FERTIG_ABSTAND = 0.3      # °P über dem Endwert gilt als durchgegoren
FENSTER = timedelta(hours=72)
MIN_PUNKTE = 4
MIN_SPANNE = timedelta(hours=8)
MAX_VORAUS = timedelta(days=21)


def berechnen(
    verlauf: list[tuple[datetime, float]], sw: float, endwert: float, jetzt: datetime
) -> dict[str, Any] | None:
    """Prognose oder None, wenn (noch) keine sinnvolle Aussage möglich ist.

    Rückgabe: {"fertig_am": datetime, "erreicht": bool, "endwert": float}
    """
    if sw <= 0 or endwert <= 0 or endwert >= sw or not verlauf:
        return None
    verlauf = sorted((t, v) for t, v in verlauf if t is not None and v is not None)
    if not verlauf:
        return None
    letzter_t, letzter = verlauf[-1]
    if letzter - endwert <= FERTIG_ABSTAND:
        return {"fertig_am": letzter_t, "erreicht": True, "endwert": endwert}
    # Noch in der Anlaufphase: weniger als 20 % des Wegs geschafft
    if (sw - letzter) < 0.2 * (sw - endwert):
        return None

    # Logistische Kurve mit bekanntem Start (Stammwürze) und Endwert:
    #   Abstand d(t) = D / (1 + e^(k·(t - tm)))   mit D = SW - Endwert
    # linearisiert: ln(D/d - 1) = k·t - k·tm  -> lineare Regression
    gesamt = sw - endwert
    pkt = [
        (t, v - endwert) for t, v in verlauf
        if t >= letzter_t - FENSTER and 0.05 < v - endwert < 0.97 * gesamt
    ]
    if len(pkt) < MIN_PUNKTE or pkt[-1][0] - pkt[0][0] < MIN_SPANNE:
        return None
    t0 = pkt[0][0]
    xs = [(t - t0).total_seconds() / 3600 for t, _ in pkt]
    ys = [math.log(gesamt / d - 1) for _, d in pkt]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None
    k = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    if k <= 1e-3:
        return None  # kein Fortschritt mehr erkennbar (steht oder steigt)
    tm = mx - my / k
    stunden = tm + math.log(gesamt / FERTIG_ABSTAND - 1) / k
    fertig = t0 + timedelta(hours=stunden)
    if fertig < letzter_t:
        fertig = letzter_t
    if fertig - jetzt > MAX_VORAUS:
        return None
    return {"fertig_am": fertig, "erreicht": False, "endwert": endwert}


def fuer_sud(sud: Any, jetzt: datetime) -> dict[str, Any] | None:
    """Prognose für einen db.Sud in Gärung."""
    endwert = sud.sre_schnellgaer if sud.sre_schnellgaer else sud.sre_erwartet
    punkte = [(m.zeitstempel, m.restextrakt) for m in sud.verlauf]
    return berechnen(punkte, sud.sw_ist, endwert, jetzt)
