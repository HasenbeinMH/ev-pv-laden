# -*- coding: utf-8 -*-
"""
Welches Wettermodell liefert die beste PV-Prognose fuer diese Anlage?

Je Wettermodell (Prognose vom Vortag, geladen mit wettermodelle_laden.py) wird das Kennfeld
des Add-ons (pvmodell.trainieren) mit 2024–2025 trainiert und auf 2026 getestet – Tage,
die das Modell nie gesehen hat. Alle Modelle werden auf denselben Testtagen verglichen.
Zusaetzlich Mittelwerte mehrerer Modelle (Ensemble).

    python dev/modell/wettermodelle.py
"""
import csv
import io
import json
import os
import statistics as st
import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HIER)))
import pvmodell as pm  # noqa: E402

DATEN = os.path.join(os.path.dirname(HIER), "data", "modell")
TZ = ZoneInfo("Europe/Berlin")
LAT, LON = (lambda d: (d["lat"], d["lon"]))(json.load(open(os.path.join(DATEN, "standort.json"))))
FL = [pm.Flaeche("sued", 6, 179, 3.33), pm.Flaeche("nord", 14, 359, 3.33), pm.Flaeche("ost", 34, 86, 3.33)]
EINZELN = ["best_match", "ecmwf_ifs025", "icon_seamless", "ukmo_seamless", "metno_seamless",
           "meteofrance_seamless", "gfs_seamless", "knmi_seamless"]
ENSEMBLES = {
    "Mittel ECMWF+ICON": ["ecmwf_ifs025", "icon_seamless"],
    "Mittel ECMWF+ICON+UKMO": ["ecmwf_ifs025", "icon_seamless", "ukmo_seamless"],
    "Mittel ECMWF+ICON+Meteo-France": ["ecmwf_ifs025", "icon_seamless", "meteofrance_seamless"],
}
GRENZE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def gti(datei_name):
    aus = {}
    for f in FL:
        d = json.load(open(os.path.join(DATEN, datei_name.format(f.name))))["hourly"]
        werte = d[[k for k in d if k != "time"][0]]
        for t, v in zip(d["time"], werte):
            if v is None:
                continue
            tb = datetime.fromisoformat(t).replace(tzinfo=timezone.utc) - timedelta(hours=1)
            aus.setdefault(tb, {})[f.name] = v
    return {t: g for t, g in aus.items() if len(g) == len(FL)}


def mittel(quellen):
    gemeinsam = set.intersection(*(set(q) for q in quellen))
    return {t: {f.name: st.mean(q[t][f.name] for q in quellen) for f in FL} for t in gemeinsam}


mess = {}
for z in csv.DictReader(open(os.path.join(DATEN, "pv_stunden.csv"))):
    mess[datetime.fromisoformat(z["zeit_utc"].replace("Z", "+00:00"))] = float(z["pv_kwh"])
arch = gti("arch_gti_{}.json")
prog = {m: gti(os.path.join("modelle", m + "_{}.json")) for m in EINZELN}
for name, teile in ENSEMBLES.items():
    prog[name] = mittel([prog[m] for m in teile])

# Testtage: 2026, Messung vollstaendig, alle Modelle mit allen 24 Stunden
stunden_je_tag = {}
for t in mess:
    d = t.astimezone(TZ).date()
    stunden_je_tag[d] = stunden_je_tag.get(d, 0) + 1
tage = []
for d, n in sorted(stunden_je_tag.items()):
    if n < 23 or d.year != 2026:
        continue
    beginn = datetime(d.year, d.month, d.day, tzinfo=TZ).astimezone(timezone.utc)
    st_liste = [beginn + timedelta(hours=h) for h in range(24)]
    if all(all(t in p for t in st_liste) for p in prog.values()):
        tage.append((d, st_liste))

ergebnis = []
for name, p in prog.items():
    with redirect_stdout(io.StringIO()):
        modell = pm.trainieren({t: v for t, v in mess.items() if t < GRENZE}, p, arch, FL, LAT, LON, TZ)
    fehler, rel, winter = [], [], []
    for d, st_liste in tage:
        vorh = sum(k for _, k in modell.prognose([(t, p[t]) for t in st_liste], FL, LAT, LON, TZ))
        ist = sum(mess.get(t, 0.0) for t in st_liste)
        fehler.append(abs(vorh - ist))
        if ist > 3:
            rel.append(abs(vorh - ist) / ist)
        if d.month not in pm.SOMMER:
            winter.append(abs(vorh - ist))
    ergebnis.append((st.mean(fehler), name, st.mean(rel) * 100, st.mean(winter), modell.kennzahlen.get("tage")))

print(f"Testtage 2026: {len(tage)} ({tage[0][0]} bis {tage[-1][0]}), Training 2024–2025, Prognose vom Vortag\n")
print(f"{'Wettermodell':32s} {'Fehler/Tag':>10s} {'Tage>3kWh':>10s} {'Okt–Mär':>8s}")
for mae, name, r, w, _ in sorted(ergebnis):
    print(f"{name:32s} {mae:8.2f} kWh {r:8.1f} % {w:6.2f} kWh")


# ── Gegenprobe wie im Add-on: Training mit dem juengsten Lauf (lauf0) ────────────────────
lauf0 = {m: gti(os.path.join("modelle", m + "_lauf0_{}.json")) for m in ("best_match", "ecmwf_ifs025", "icon_seamless")}
lauf0["Mittel ECMWF+ICON"] = mittel([lauf0["ecmwf_ifs025"], lauf0["icon_seamless"]])
vortag = {"best_match": prog["best_match"], "ecmwf_ifs025": prog["ecmwf_ifs025"],
          "icon_seamless": prog["icon_seamless"], "Mittel ECMWF+ICON": prog["Mittel ECMWF+ICON"]}
tage0 = [(d, sl) for d, sl in tage if all(all(t in p for t in sl) for p in lauf0.values())]
print(f"\nTraining mit juengstem Lauf (wie im Add-on), {len(tage0)} Testtage 2026")
print(f"{'Wettermodell':32s} {'Test: Lauf am Tag':>18s} {'Test: Vortag':>13s}")
for name in lauf0:
    with redirect_stdout(io.StringIO()):
        modell = pm.trainieren({t: v for t, v in mess.items() if t < GRENZE}, lauf0[name], arch, FL, LAT, LON, TZ)
    zeile = []
    for quelle in (lauf0[name], vortag[name]):
        f = []
        for d, sl in tage0:
            vorh = sum(k for _, k in modell.prognose([(t, quelle[t]) for t in sl], FL, LAT, LON, TZ))
            f.append(abs(vorh - sum(mess.get(t, 0.0) for t in sl)))
        zeile.append(st.mean(f))
    print(f"{name:32s} {zeile[0]:14.2f} kWh {zeile[1]:9.2f} kWh")
