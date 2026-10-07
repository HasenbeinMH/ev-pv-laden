# -*- coding: utf-8 -*-
"""
PV-Prognose aus Home Assistant (WebSocket "energy/solar_forecast", geprueft gegen
homeassistant/components/energy/websocket_api.py).

HA liefert nur Prognosen, die im Energie-Dashboard der PV-Quelle zugeordnet sind
("config_entry_solar_forecast"). Antwort je Config-Entry:
    {entry_id: {"wh_hours": {"2026-10-04T10:00:00+02:00": 812, ...}}}
Bei Forecast.Solar ist der Wert die Energie der Stunde, die zum Zeitstempel endet.
Mehrere Dachflaechen werden summiert.

Nutzung heute nur zur Anzeige; in M7 (Zielzeit) plant die Strategie damit.
"""
import logging
from datetime import datetime, timedelta

log = logging.getLogger("prognose")

ABFRAGE_S = 900    # Forecast.Solar aktualisiert ohnehin nur etwa stuendlich


def zusammenfassen(antwort: dict) -> dict[datetime, float]:
    """Summiert wh_hours ueber alle Eintraege: {Zeitpunkt (aware): Wh}."""
    summe: dict[datetime, float] = {}
    for eintrag in (antwort or {}).values():
        for zeit, wh in ((eintrag or {}).get("wh_hours") or {}).items():
            try:
                t = datetime.fromisoformat(zeit)
            except (TypeError, ValueError):
                continue
            summe[t] = summe.get(t, 0.0) + float(wh or 0)
    return dict(sorted(summe.items()))


class Prognose:
    def __init__(self):
        self.werte: dict[datetime, float] = {}
        self.stand: datetime | None = None
        self.fehler: str | None = None
        self.eintraege = 0

    def setzen(self, antwort: dict, jetzt: datetime, nur_eigene: bool = False) -> None:
        """nur_eigene: im Energie-Dashboard ist nur unsere Integration zugeordnet (herausgerechnet)
        – gewollt, kein Fehler; es gibt dann nur keinen Vergleich."""
        self.eintraege = len(antwort or {})
        self.werte = zusammenfassen(antwort)
        self.stand = jetzt
        if self.eintraege:
            self.fehler = None
        elif nur_eigene:
            self.fehler = "nur die eigene Prognose im Energie-Dashboard zugeordnet – kein Vergleich"
        else:
            self.fehler = ("keine Prognose im Energie-Dashboard zugeordnet "
                           "(Energie -> Solarmodule -> Prognose der Solarproduktion)")

    def _summe(self, von: datetime, bis: datetime) -> float:
        """Wh im Zeitraum. Stunde (Ende t) anteilig, wenn sie den Rand schneidet."""
        wh = 0.0
        for t, w in self.werte.items():
            beginn = t - timedelta(hours=1)
            ueberlapp = (min(t, bis) - max(beginn, von)).total_seconds()
            if ueberlapp > 0:
                wh += w * ueberlapp / 3600
        return wh

    def uebersicht(self, jetzt: datetime) -> dict:
        """jetzt: zeitzonenbewusst (lokale Zeit von HA)."""
        mitternacht = jetzt.replace(hour=0, minute=0, second=0, microsecond=0)
        morgen = mitternacht + timedelta(days=1)
        stunden = [{"zeit": t.isoformat(), "wh": round(w)}
                   for t, w in self.werte.items() if mitternacht < t <= morgen + timedelta(days=1)]
        return {
            "verfuegbar": bool(self.werte),
            "fehler": self.fehler,
            "stand": self.stand.isoformat(timespec="seconds") if self.stand else None,
            "heute_kwh": round(self._summe(mitternacht, morgen) / 1000, 2),
            "heute_rest_kwh": round(self._summe(jetzt, morgen) / 1000, 2),
            "morgen_kwh": round(self._summe(morgen, morgen + timedelta(days=1)) / 1000, 2),
            "stunden": stunden,
        }
