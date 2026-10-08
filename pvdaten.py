# -*- coding: utf-8 -*-
"""
Daten fuer das PV-Modell: Open-Meteo (Einstrahlung) und HA-Langzeitstatistik (Messung).

Open-Meteo (kostenlos, ohne Schluessel, nur nicht-kommerziell):
  PROGNOSE       api.open-meteo.com/v1/forecast              – aktuelle Prognose
  LAEUFE         previous-runs-api.open-meteo.com/...         – fruehere Laeufe (Training, je Modell)
  ALTE_PROGNOSE  historical-forecast-api.open-meteo.com/...   – archivierte Prognosen (bis 0.15.x)
  ARCHIV         archive-api.open-meteo.com/v1/archive        – nachtraeglich gemessene Werte
Wettermodell (Option wettermodell): Standard Mittel aus ECMWF und ICON (WETTERMODELLE).
Je Dachflaeche eine Abfrage (tilt/azimuth). Strahlung zum Zeitpunkt T = Mittel ueber
[T-1h, T] -> wird hier auf den Stundenbeginn T-1h gelegt (wie die HA-Statistik).

HA: recorder/statistics_during_period (geprueft gegen recorder/websocket_api.py), stuendlich.
PV-Erzeugung: Energiezaehler ("change") oder SolarEdge-Hybrid:
    PV = DC-Leistung ("mean", W) + Akku geladen ("change") - Akku entladen ("change")
"""
import logging
from datetime import date, datetime, timedelta, timezone

import aiohttp

import morgentau
import pvmodell as pm

log = logging.getLogger("pvdaten")

PROGNOSE = "https://api.open-meteo.com/v1/forecast"
ALTE_PROGNOSE = "https://historical-forecast-api.open-meteo.com/v1/forecast"
ARCHIV = "https://archive-api.open-meteo.com/v1/archive"
# Fruehere Laeufe je Wettermodell (ab ~02/2024 fuer ECMWF) – Training: juengster Lauf je Stunde
LAEUFE = "https://previous-runs-api.open-meteo.com/v1/forecast"
# Option wettermodell -> Open-Meteo-Modelle; mehrere werden je Stunde und Flaeche gemittelt
WETTERMODELLE = {
    "ecmwf_icon": ("ecmwf_ifs025", "icon_seamless"),
    "best_match": ("best_match",),
    "ecmwf": ("ecmwf_ifs025",),
    "icon": ("icon_seamless",),
}
WETTERMODELL_TEXT = {"ecmwf_icon": "ECMWF + ICON", "best_match": "best_match",
                     "ecmwf": "ECMWF", "icon": "ICON (DWD)"}
HA_ABSCHNITT_TAGE = 60          # Statistik in Abschnitten abfragen (Antwortgroesse)
HA_TIMEOUT_S = 60


def flaechen_aus_konfig(liste: list[dict]) -> list[pm.Flaeche]:
    return [pm.Flaeche(str(f["name"]), float(f["neigung"]), float(f["azimut"]), float(f["kwp"]))
            for f in liste]


# ── Open-Meteo ─────────────────────────────────────────────────────────────────────
def gti_eintragen(antwort: dict, flaeche: str, ziel: dict) -> None:
    """Open-Meteo-Antwort (hourly.time/global_tilted_irradiance, UTC) in
    ziel[Stundenbeginn UTC][flaeche] = W/m2 eintragen."""
    h = antwort.get("hourly") or {}
    for t, v in zip(h.get("time", []), h.get("global_tilted_irradiance", [])):
        if v is None:
            continue
        beginn = datetime.fromisoformat(t).replace(tzinfo=timezone.utc) - timedelta(hours=1)
        ziel.setdefault(beginn, {})[flaeche] = float(v)


async def gti_holen(sitzung: aiohttp.ClientSession, url: str, lat: float, lon: float,
                    flaechen: list[pm.Flaeche], zeitraum: dict,
                    modelle: tuple[str, ...] = ()) -> dict[datetime, dict]:
    """zeitraum: {"start_date": ..., "end_date": ...} oder {"past_days": 1, "forecast_days": 3}.
    modelle: Open-Meteo-Wettermodelle; mehrere werden je Stunde und Flaeche gemittelt
    (nur Stunden, die alle Modelle liefern). Leer = Voreinstellung des Dienstes."""
    je_modell = []
    for modell in (modelle or (None,)):
        ziel: dict[datetime, dict] = {}
        for f in flaechen:
            params = {"latitude": round(lat, 2), "longitude": round(lon, 2), "timezone": "UTC",
                      "hourly": "global_tilted_irradiance", "tilt": f.neigung, "azimuth": f.om_azimut,
                      **zeitraum, **({"models": modell} if modell else {})}
            async with sitzung.get(url, params=params, timeout=aiohttp.ClientTimeout(total=120)) as r:
                daten = await r.json(content_type=None)
                if r.status != 200 or daten.get("error"):
                    raise RuntimeError(f"Open-Meteo {r.status}: {daten.get('reason', daten)}")
            gti_eintragen(daten, f.name, ziel)
        # nur Stunden, fuer die alle Flaechen einen Wert haben
        je_modell.append({t: g for t, g in ziel.items() if len(g) == len(flaechen)})
    if len(je_modell) == 1:
        return je_modell[0]
    gemeinsam = set.intersection(*(set(m) for m in je_modell))
    return {t: {f.name: sum(m[t][f.name] for m in je_modell) / len(je_modell) for f in flaechen}
            for t in sorted(gemeinsam)}


async def wetter_holen(sitzung: aiohttp.ClientSession, lat: float, lon: float, zeitraum: dict) -> dict:
    """Wetter der Naechte fuer die Morgentau-Korrektur (Open-Meteo-Prognose, UTC)."""
    params = {"latitude": round(lat, 2), "longitude": round(lon, 2), "timezone": "UTC",
              "hourly": morgentau.WETTER_GROESSEN, **zeitraum}
    async with sitzung.get(PROGNOSE, params=params, timeout=aiohttp.ClientTimeout(total=60)) as r:
        daten = await r.json(content_type=None)
        if r.status != 200 or daten.get("error"):
            raise RuntimeError(f"Open-Meteo {r.status}: {daten.get('reason', daten)}")
    return morgentau.wetter_eintragen(daten)


# ── HA-Statistik ───────────────────────────────────────────────────────────────────
def statistik_ids(k) -> dict[str, str]:
    if k.sensor_pv_energie:
        return {"energie": k.sensor_pv_energie}
    return {"dc": k.sensor_pv_dc_leistung, "geladen": k.sensor_akku_geladen,
            "entladen": k.sensor_akku_entladen}


def pv_aus_statistik(ergebnis: dict, ids: dict[str, str]) -> dict[datetime, float]:
    """Antwort von recorder/statistics_during_period -> {Stundenbeginn UTC: PV kWh}."""
    def reihe(sid, art):
        return {datetime.fromtimestamp(z["start"] / 1000, timezone.utc): z.get(art)
                for z in ergebnis.get(sid, []) if z.get(art) is not None}

    if "energie" in ids:
        return {t: max(float(v), 0.0) for t, v in reihe(ids["energie"], "change").items()}
    dc = reihe(ids["dc"], "mean")
    geladen = reihe(ids["geladen"], "change") if ids.get("geladen") else {}
    entladen = reihe(ids["entladen"], "change") if ids.get("entladen") else {}
    # Fehlende Akku-Stunde = keine Aenderung (Statistik schreibt dann oft keine Zeile)
    return {t: max(w / 1000 + geladen.get(t, 0.0) - entladen.get(t, 0.0), 0.0) for t, w in dc.items()}


async def pv_messung(ha, k, start: datetime, ende: datetime) -> dict[datetime, float]:
    ids = statistik_ids(k)
    ergebnis: dict[str, list] = {}
    abschnitt = start
    while abschnitt < ende:
        bis = min(abschnitt + timedelta(days=HA_ABSCHNITT_TAGE), ende)
        teil = await ha.anfrage({
            "type": "recorder/statistics_during_period",
            "start_time": abschnitt.isoformat(), "end_time": bis.isoformat(),
            "statistic_ids": [s for s in ids.values() if s], "period": "hour",
            "types": ["mean", "change"], "units": {"power": "W", "energy": "kWh"},
        }, timeout=HA_TIMEOUT_S) or {}
        for sid, zeilen in teil.items():
            ergebnis.setdefault(sid, []).extend(zeilen)
        abschnitt = bis
    return pv_aus_statistik(ergebnis, ids)


async def verbrauch_holen(ha, k, ende: datetime, tage_haus: int = 28, tage_akku: int = 14
                          ) -> tuple[dict[datetime, float], float | None]:
    """Fuer die 7-Tage-Vorschau: Hausverbrauch je Stunde (W, ohne Auto) der letzten Wochen und
    mittlere Entladung des Hausakkus je Tag (kWh) – beides aus der HA-Langzeitstatistik."""
    auto = f"sensor.goe_{k.goe_seriennummer}_nrg_11"
    ids = [s for s in (k.sensor_haus, auto if k.sensor_haus_enthaelt_auto else "", k.sensor_akku_entladen) if s]
    if not ids:
        return {}, None
    stunden = await ha.anfrage({
        "type": "recorder/statistics_during_period",
        "start_time": (ende - timedelta(days=tage_haus)).isoformat(), "end_time": ende.isoformat(),
        "statistic_ids": ids, "period": "hour", "types": ["mean", "change"],
        "units": {"power": "W", "energy": "kWh"},
    }, timeout=HA_TIMEOUT_S) or {}

    def reihe(sid, art):
        return {datetime.fromtimestamp(z["start"] / 1000, timezone.utc): z.get(art)
                for z in stunden.get(sid, []) if z.get(art) is not None}

    haus = reihe(k.sensor_haus, "mean") if k.sensor_haus else {}
    if k.sensor_haus_enthaelt_auto:
        a = reihe(auto, "mean")
        haus = {t: w - (a.get(t) or 0.0) for t, w in haus.items()}
    akku = None
    if k.sensor_akku_entladen:
        grenze = ende - timedelta(days=tage_akku)
        werte = [v for t, v in reihe(k.sensor_akku_entladen, "change").items() if t >= grenze]
        if werte:
            akku = round(max(sum(werte), 0.0) / tage_akku, 2)
    return haus, akku


def datum(t: datetime) -> str:
    return t.astimezone(timezone.utc).date().isoformat()


def gestern() -> date:
    return datetime.now(timezone.utc).date() - timedelta(days=1)
