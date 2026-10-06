"""Reine Rechenlogik ohne Home-Assistant-Abhaengigkeit (testbar).

Format wie energy/solar_forecast: {Zeitstempel ISO: Wh}, der Zeitstempel ist das ENDE der
Stunde, deren Energie der Wert angibt.
"""
from __future__ import annotations

from datetime import datetime, timedelta


def einlesen(wh_hours: dict | None) -> dict[datetime, float]:
    """{"2026-10-06T11:00:00+02:00": 812} -> {datetime (aware): 812.0}, sortiert."""
    werte: dict[datetime, float] = {}
    for zeit, wh in (wh_hours or {}).items():
        try:
            werte[datetime.fromisoformat(zeit)] = float(wh or 0)
        except (TypeError, ValueError):
            continue
    return dict(sorted(werte.items()))


def summe_wh(werte: dict[datetime, float], von: datetime, bis: datetime) -> float:
    """Wh im Zeitraum; eine Stunde, die den Rand schneidet, zaehlt anteilig."""
    wh = 0.0
    for ende, wert in werte.items():
        beginn = ende - timedelta(hours=1)
        ueberlapp = (min(ende, bis) - max(beginn, von)).total_seconds()
        if ueberlapp > 0:
            wh += wert * min(ueberlapp, 3600) / 3600
    return wh


def kennzahlen(werte: dict[datetime, float], jetzt: datetime) -> dict[str, float | None]:
    """kWh fuer die Sensoren der Integration (jetzt: zeitzonenbewusst, Ortszeit von HA)."""
    if not werte:
        return {k: None for k in ("heute", "rest_heute", "morgen", "aktuelle_stunde",
                                  "naechste_stunde", "naechste_3h")}
    mitternacht = jetzt.replace(hour=0, minute=0, second=0, microsecond=0)
    morgen = mitternacht + timedelta(days=1)
    stunde = jetzt.replace(minute=0, second=0, microsecond=0)

    def kwh(von, bis):
        return round(summe_wh(werte, von, bis) / 1000, 3)

    return {
        "heute": kwh(mitternacht, morgen),
        "rest_heute": kwh(jetzt, morgen),
        "morgen": kwh(morgen, morgen + timedelta(days=1)),
        "aktuelle_stunde": kwh(stunde, stunde + timedelta(hours=1)),
        "naechste_stunde": kwh(stunde + timedelta(hours=1), stunde + timedelta(hours=2)),
        "naechste_3h": kwh(jetzt, jetzt + timedelta(hours=3)),
    }
