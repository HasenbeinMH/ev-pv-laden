# -*- coding: utf-8 -*-
"""
Morgentau-Korrektur der eigenen PV-Prognose.

Nach klaren, feuchten, windstillen Naechten liegt Tau auf den Modulen; im Winterhalbjahr
(Okt–Maerz) verdunstet er langsam und die ersten Sonnenstunden bringen deutlich weniger.
Das Kennfeld kennt diesen Effekt nur als Mittelwert. Auswertung 2024–2026
(dev/modell/tau.py): nach Tau-Naechten im Winterhalbjahr am Morgen ~0,7–0,8 der Prognose.

Merkmale der Nacht aus der Open-Meteo-Prognose (9 h vor Sonnenaufgang):
  Spreizung = Temperatur - Taupunkt (Minimum der letzten 3 h vor Sonnenaufgang)
  Wolken, Wind = Mittel der Nacht; Regen = Summe der Nacht
Klassen wie in der Auswertung; bei "Tau wahrscheinlich" und "Tau moeglich" werden die ersten
MORGEN_STUNDEN Sonnenstunden mit TAU_FAKTOR multipliziert (nur Winterhalbjahr).
"""
from datetime import date, datetime, timedelta, timezone

import pvmodell as pm

TAU_FAKTOR = 0.7            # Startwert (07.10.2026), am 18.10. mit echten Herbstmorgen nachjustieren
MORGEN_STUNDEN = 4          # so viele Sonnenstunden ab Sonnenaufgang gelten als "Morgen"
NACHT_STUNDEN = 9
WETTER_GROESSEN = "temperature_2m,dew_point_2m,cloud_cover,wind_speed_10m,precipitation"

WAHRSCHEINLICH, MOEGLICH, TROCKEN, NASS = "Tau wahrscheinlich", "Tau möglich", "trocken", "nass (Regen)"
MIT_TAU = {WAHRSCHEINLICH, MOEGLICH}


def wetter_eintragen(antwort: dict) -> dict[datetime, dict]:
    """Open-Meteo-Antwort (hourly, UTC) -> {Zeitpunkt UTC: {groesse: wert}} (nicht verschoben)."""
    h = (antwort or {}).get("hourly") or {}
    aus = {}
    for i, t in enumerate(h.get("time", [])):
        aus[datetime.fromisoformat(t).replace(tzinfo=timezone.utc)] = {
            k: v[i] for k, v in h.items() if k != "time"}
    return aus


def nacht(wetter: dict[datetime, dict], sonnenaufgang: datetime) -> dict | None:
    """Merkmale der Nacht vor sonnenaufgang (UTC-Stundenbeginn der ersten Sonnenstunde)."""
    werte = [wetter.get(sonnenaufgang - timedelta(hours=h)) for h in range(1, NACHT_STUNDEN + 1)]
    werte = [w for w in werte if w and None not in (w.get("temperature_2m"), w.get("dew_point_2m"),
                                                    w.get("cloud_cover"), w.get("wind_speed_10m"))]
    if len(werte) < 6:
        return None
    letzte = werte[:3]      # die 3 Stunden vor Sonnenaufgang
    return {
        "spreizung": round(min(w["temperature_2m"] - w["dew_point_2m"] for w in letzte), 1),
        "wolken": round(sum(w["cloud_cover"] for w in werte) / len(werte)),
        "wind": round(sum(w["wind_speed_10m"] for w in werte) / len(werte), 1),
        "regen": round(sum(w.get("precipitation") or 0 for w in werte), 1),
    }


def klasse(n: dict | None) -> str | None:
    if n is None:
        return None
    if n["regen"] > 0.2:
        return NASS
    if n["spreizung"] <= 1.5 and n["wolken"] < 50 and n["wind"] < 12:
        return WAHRSCHEINLICH
    if n["spreizung"] <= 3.0 and n["wolken"] < 70:
        return MOEGLICH
    return TROCKEN


def korrigieren(werte: list[tuple[datetime, float]], wetter: dict[datetime, dict],
                lat: float, lon: float, tz, faktor: float = TAU_FAKTOR
                ) -> tuple[list[tuple[datetime, float]], dict[date, dict]]:
    """werte: (Stundenbeginn UTC, kWh) aus dem Kennfeld. Gibt korrigierte Werte und je Tag
    {klasse, faktor, nacht, morgen_ohne_kwh, morgen_mit_kwh, morgen_bis} zurueck."""
    je_tag: dict[date, list[datetime]] = {}
    for t, _ in werte:
        lokal = t.astimezone(tz)
        if pm.bin_von(t, lat, lon, lokal.month)[0] is not None:
            je_tag.setdefault(lokal.date(), []).append(t)
    kwh = dict(werte)
    tage: dict[date, dict] = {}
    for tag, sonne in je_tag.items():
        sonne.sort()
        n = nacht(wetter, sonne[0])
        k = klasse(n)
        winter = tag.month not in pm.SOMMER
        f = faktor if (winter and k in MIT_TAU) else 1.0
        morgen = sonne[:MORGEN_STUNDEN]
        ohne = sum(kwh[t] for t in morgen)
        for t in morgen:
            kwh[t] *= f
        tage[tag] = {"klasse": k, "faktor": f, "nacht": n, "morgen_ohne_kwh": round(ohne, 2),
                     "morgen_mit_kwh": round(ohne * f, 2),
                     "morgen_bis": (morgen[-1] + timedelta(hours=1)).astimezone(tz).strftime("%H:%M")}
    return sorted(kwh.items()), tage


def text(tag: date, info: dict) -> str:
    """Eine Zeile fuer Protokoll/Ereignisse."""
    n = info.get("nacht")
    merkmale = (f" (Abstand Temperatur–Taupunkt {n['spreizung']:.1f} K, Wolken {n['wolken']} %, "
                f"Wind {n['wind']:.0f} km/h)".replace(".", ",") if n else "")
    zeile = f"Morgentau {tag:%d.%m.}: {info.get('klasse') or 'unbekannt'}{merkmale}"
    if info["faktor"] != 1.0:
        zeile += (f" – Morgen bis {info['morgen_bis']} ×{info['faktor']:.1f}: "
                  f"{info['morgen_ohne_kwh']:.2f} → {info['morgen_mit_kwh']:.2f} kWh").replace(".", ",")
    return zeile
