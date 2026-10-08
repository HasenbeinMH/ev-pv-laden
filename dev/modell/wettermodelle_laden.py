# -*- coding: utf-8 -*-
"""
Laedt fuer mehrere Wettermodelle die Einstrahlungsprognose VOM VORTAG (previous_day1) je
Dachflaeche von Open-Meteo (previous-runs-api) nach dev/data/modell/modelle/.

    python dev/modell/wettermodelle_laden.py

Danach: python dev/modell/wettermodelle.py (Training 2024–2025, Test 2026).
"""
import json
import os
import subprocess
import sys
import urllib.parse

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HIER)))
import pvmodell as pm  # noqa: E402

DATEN = os.path.join(os.path.dirname(HIER), "data", "modell")
ZIEL = os.path.join(DATEN, "modelle")
STANDORT = json.load(open(os.path.join(DATEN, "standort.json")))   # lokal, nicht im Repo
FL = [pm.Flaeche("sued", 6, 179, 3.33), pm.Flaeche("nord", 14, 359, 3.33), pm.Flaeche("ost", 34, 86, 3.33)]
MODELLE = ["best_match", "ecmwf_ifs025", "icon_seamless", "ukmo_seamless", "metno_seamless",
           "meteofrance_seamless", "gfs_seamless", "knmi_seamless"]
START, ENDE = "2024-01-01", "2026-10-07"


def laden(modell: str, f: pm.Flaeche, variable: str = "global_tilted_irradiance_previous_day1",
          kennung: str = "") -> None:
    """variable ..._previous_day1 = Prognose vom Vortag; ohne Endung = juengster Lauf (wie Training)."""
    datei = os.path.join(ZIEL, f"{modell}{kennung}_{f.name}.json")
    if os.path.exists(datei):
        return
    q = urllib.parse.urlencode({
        "latitude": round(STANDORT["lat"], 2), "longitude": round(STANDORT["lon"], 2), "timezone": "UTC",
        "hourly": variable, "tilt": f.neigung, "azimuth": f.om_azimut,
        "models": modell, "start_date": START, "end_date": ENDE})
    out = subprocess.run(["curl", "-sS", "--max-time", "300",
                          "https://previous-runs-api.open-meteo.com/v1/forecast?" + q],
                         capture_output=True, text=True).stdout
    d = json.loads(out)
    if d.get("error"):
        print(f"{modell} {f.name}: {d.get('reason')}")
        return
    with open(datei, "w") as fh:
        json.dump(d, fh)
    werte = [v for v in d["hourly"][[k for k in d["hourly"] if k != "time"][0]] if v is not None]
    print(f"{modell:22s} {f.name:5s} {len(werte)} Stunden mit Wert")


if __name__ == "__main__":
    os.makedirs(ZIEL, exist_ok=True)
    for m in MODELLE:
        for f in FL:
            laden(m, f)
    # juengster Lauf je Stunde (Trainingsdaten wie im Add-on)
    for m in ("best_match", "ecmwf_ifs025", "icon_seamless"):
        for f in FL:
            laden(m, f, "global_tilted_irradiance", "_lauf0")
