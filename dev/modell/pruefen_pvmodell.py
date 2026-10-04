# -*- coding: utf-8 -*-
"""
Prueft pvmodell.py (Add-on-Code, reines Python) gegen die Daten der Auswertung:
Training bis 31.12.2025, Test 2026 (nur vollstaendige Tage). Die laufende Sauberkeit wird
nur aus den VORHERIGEN 14 Tagen geschaetzt (wie im Betrieb).

    python dev/modell/pruefen_pvmodell.py
"""
import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HIER)))
import pvmodell as pm  # noqa: E402

DATEN = os.path.join(os.path.dirname(HIER), "data", "modell")
TZ = ZoneInfo("Europe/Berlin")
# Standort lokal in dev/data/modell/standort.json – nicht im Repo
LAT, LON = (lambda d: (d["lat"], d["lon"]))(json.load(open(os.path.join(DATEN, "standort.json"))))
FL = [pm.Flaeche("sued", 8, 180, 3.33), pm.Flaeche("nord", 12, 0, 3.33), pm.Flaeche("ost", 25, 90, 3.33)]


def gti(prefix):
    aus = {}
    for f in FL:
        d = json.load(open(os.path.join(DATEN, f"{prefix}_gti_{f.name}.json")))["hourly"]
        for t, v in zip(d["time"], d["global_tilted_irradiance"]):
            tb = datetime.fromisoformat(t).replace(tzinfo=timezone.utc) - timedelta(hours=1)
            aus.setdefault(tb, {})[f.name] = v
    return aus


mess = {}
for z in csv.DictReader(open(os.path.join(DATEN, "pv_stunden.csv"))):
    mess[datetime.fromisoformat(z["zeit_utc"].replace("Z", "+00:00"))] = float(z["pv_kwh"])
prog, arch = gti("om"), gti("arch")
grenze = datetime(2026, 1, 1, tzinfo=timezone.utc)
modell = pm.trainieren({t: v for t, v in mess.items() if t < grenze}, prog, arch, FL, LAT, LON, TZ)
print("Training:", modell.kennzahlen, "k_standard", modell.k_standard,
      "Sauberkeit Mittel", modell.sauberkeit_mittel, "zuletzt", modell.sauberkeit, modell.sauberkeit_stand)

stunden_je_tag = {}
for t in mess:
    d = t.astimezone(TZ).date()
    stunden_je_tag[d] = stunden_je_tag.get(d, 0) + 1
tage = sorted(d for d, n in stunden_je_tag.items() if n >= 23 and d.year == 2026 and d < datetime(2026, 10, 4).date())
fehler, s_verlauf = [], []
for tag in tage:
    beginn = datetime(tag.year, tag.month, tag.day, tzinfo=TZ).astimezone(timezone.utc)
    fenster = {t: v for t, v in mess.items() if beginn - timedelta(days=14) <= t < beginn}
    neu, _ = pm.sauberkeit_schaetzen(modell, fenster, arch, FL, LAT, LON, TZ)
    if neu is not None:
        s_verlauf.append(neu)
    st = [(beginn + timedelta(hours=h), prog.get(beginn + timedelta(hours=h), {})) for h in range(24)]
    p = sum(k for _, k in modell.prognose(st, FL, LAT, LON, TZ))
    m = sum(mess.get(beginn + timedelta(hours=h), 0.0) for h in range(24))
    fehler.append((m, p))
mae = sum(abs(p - m) for m, p in fehler) / len(fehler)
gute = [(m, p) for m, p in fehler if m > 3]
mape = sum(abs(p - m) / m for m, p in gute) / len(gute) * 100
bias = (sum(p for _, p in fehler) / sum(m for m, _ in fehler) - 1) * 100
print(f"Test 2026: {len(fehler)} Tage, MAE Tag {mae:.2f} kWh, MAPE (>3 kWh) {mape:.1f} %, Bias {bias:+.1f} %")
print(f"Sauberkeit 2026 laufend geschaetzt: {min(s_verlauf):.2f} … {max(s_verlauf):.2f}, zuletzt {s_verlauf[-1]:.2f}")
print("Erwartung (Auswertung M1): MAE 2,76–2,77 kWh, MAPE 18,7–18,8 %")
