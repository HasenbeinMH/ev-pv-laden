# -*- coding: utf-8 -*-
"""
Untersuchung: Erklaert Tau (Nachtwetter) den Fehler der Morgenstunden?

Wetter der Nacht aus der archivierten Open-Meteo-Prognose (dev/data/modell/om_tau.json, das
haette man zur Prognosezeit gekannt). Kennfeld wie im Add-on, Training bis 31.12.2025,
Test 2026.

    python dev/modell/tau.py
"""
import csv
import json
import os
import statistics as st
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HIER)))
import pvmodell as pm  # noqa: E402

DATEN = os.path.join(os.path.dirname(HIER), "data", "modell")
TZ = ZoneInfo("Europe/Berlin")
LAT, LON = (lambda d: (d["lat"], d["lon"]))(json.load(open(os.path.join(DATEN, "standort.json"))))
FL = [pm.Flaeche("sued", 6, 179, 3.33), pm.Flaeche("nord", 14, 359, 3.33), pm.Flaeche("ost", 34, 86, 3.33)]
MORGEN_STUNDEN = 4          # so viele Sonnenstunden ab Sonnenaufgang zaehlen als "Morgen"


def gti(prefix):
    aus = {}
    for f in FL:
        d = json.load(open(os.path.join(DATEN, f"{prefix}_gti_{f.name}.json")))["hourly"]
        for t, v in zip(d["time"], d["global_tilted_irradiance"]):
            tb = datetime.fromisoformat(t).replace(tzinfo=timezone.utc) - timedelta(hours=1)
            aus.setdefault(tb, {})[f.name] = v
    return aus


def wetter(datei):
    """Zeitpunktwerte (nicht verschoben): {UTC: {groesse: wert}}."""
    h = json.load(open(os.path.join(DATEN, datei)))["hourly"]
    aus = {}
    for i, t in enumerate(h["time"]):
        aus[datetime.fromisoformat(t).replace(tzinfo=timezone.utc)] = {k: h[k][i] for k in h if k != "time"}
    return aus


mess = {}
for z in csv.DictReader(open(os.path.join(DATEN, "pv_stunden.csv"))):
    mess[datetime.fromisoformat(z["zeit_utc"].replace("Z", "+00:00"))] = float(z["pv_kwh"])
prog, arch = gti("om"), gti("arch")
nacht_wetter = wetter("om_tau.json")
grenze = datetime(2026, 1, 1, tzinfo=timezone.utc)
modell = pm.trainieren({t: v for t, v in mess.items() if t < grenze}, prog, arch, FL, LAT, LON, TZ)


def nacht(sonnenaufgang):
    """Merkmale der Nacht vor dem Sonnenaufgang (UTC-Stundenbeginn der ersten Sonnenstunde)."""
    werte = [nacht_wetter.get(sonnenaufgang - timedelta(hours=h)) for h in range(1, 10)]
    werte = [w for w in werte if w and None not in (w["temperature_2m"], w["dew_point_2m"])]
    if len(werte) < 6:
        return None
    letzte = werte[:3]   # die 3 Stunden vor Sonnenaufgang
    return {
        "spreizung": min(w["temperature_2m"] - w["dew_point_2m"] for w in letzte),
        "wolken": st.mean(w["cloud_cover"] for w in werte),
        "wind": st.mean(w["wind_speed_10m"] for w in werte),
        "regen": sum(w["precipitation"] or 0 for w in werte),
        "temp": min(w["temperature_2m"] for w in werte),
    }


def tau_klasse(n):
    if n is None:
        return None
    if n["regen"] > 0.2:
        return "nass (Regen)"
    if n["spreizung"] <= 1.5 and n["wolken"] < 50 and n["wind"] < 12:
        return "Tau wahrscheinlich"
    if n["spreizung"] <= 3.0 and n["wolken"] < 70:
        return "Tau moeglich"
    return "trocken"


# Tage aufbauen: Morgenstunden mit Prognose (Kennfeld) und Messung
stunden_je_tag = {}
for t in mess:
    stunden_je_tag.setdefault(t.astimezone(TZ).date(), []).append(t)
tage = []
for tag, ts in sorted(stunden_je_tag.items()):
    if len(ts) < 23:
        continue
    beginn = datetime(tag.year, tag.month, tag.day, tzinfo=TZ).astimezone(timezone.utc)
    st_liste = [(beginn + timedelta(hours=h), prog.get(beginn + timedelta(hours=h))) for h in range(24)]
    if any(g is None or None in g.values() for _, g in st_liste):
        continue
    p = dict(modell.prognose(st_liste, FL, LAT, LON, TZ))
    sonnen = [t for t, _ in st_liste if pm.bin_von(t, LAT, LON, tag.month)[0] is not None]
    if not sonnen:
        continue
    morgen = sonnen[:MORGEN_STUNDEN]
    tage.append({
        "tag": tag, "test": beginn >= grenze, "nacht": nacht(sonnen[0]),
        "morgen": [(i, p[t], mess.get(t, 0.0)) for i, t in enumerate(morgen)],
        "p_tag": sum(p.values()), "m_tag": sum(mess.get(t, 0.0) for t in p),
    })
for d in tage:
    d["klasse"] = tau_klasse(d["nacht"])
    d["p_morgen"] = sum(p for _, p, _ in d["morgen"])
    d["m_morgen"] = sum(m for _, _, m in d["morgen"])

# 1) Verhaeltnis Messung/Prognose am Morgen je Klasse (nur Morgen mit nennenswerter Sonne)
KLASSEN = ["Tau wahrscheinlich", "Tau moeglich", "trocken", "nass (Regen)"]
print(f"Morgen = erste {MORGEN_STUNDEN} Sonnenstunden; nur Tage mit Prognose Morgen > 1 kWh\n")
for teil, name in ((False, "Training 2024-2025"), (True, "Test 2026")):
    print(name)
    print(f"  {'Klasse':20} {'Tage':>5} {'Ist/Prognose (Summe)':>21} {'Median je Tag':>14}")
    for k in KLASSEN:
        auswahl = [d for d in tage if d["test"] == teil and d["klasse"] == k and d["p_morgen"] > 1]
        if not auswahl:
            continue
        summe = sum(d["m_morgen"] for d in auswahl) / sum(d["p_morgen"] for d in auswahl)
        median = st.median(d["m_morgen"] / d["p_morgen"] for d in auswahl)
        print(f"  {k:20} {len(auswahl):5} {summe:21.2f} {median:14.2f}")
    print()

# Nach Jahreszeit (Tau ist vor allem Herbst/Fruehling)
print("Tau wahrscheinlich vs. trocken je Halbjahr (alle Jahre, Ist/Prognose Morgen):")
for halb, monate in (("Apr-Sep", pm.SOMMER), ("Okt-Mar", set(range(1, 13)) - pm.SOMMER)):
    zeile = []
    for k in ("Tau wahrscheinlich", "trocken"):
        a = [d for d in tage if d["klasse"] == k and d["p_morgen"] > 1 and d["tag"].month in monate]
        if a:
            zeile.append(f"{k}: {sum(d['m_morgen'] for d in a) / sum(d['p_morgen'] for d in a):.2f} ({len(a)} T.)")
    print(f"  {halb}: " + " | ".join(zeile))
print()

# 2) Korrektur lernen: Faktor je (Klasse, Halbjahr, Stunde nach Sonnenaufgang), aus Training
def schluessel(d, i):
    return (d["klasse"], "s" if d["tag"].month in pm.SOMMER else "w", i)


za, ne = {}, {}
for d in tage:
    if d["test"] or d["klasse"] is None:
        continue
    for i, p, m in d["morgen"]:
        if p > 0.05:
            za[schluessel(d, i)] = za.get(schluessel(d, i), 0) + m
            ne[schluessel(d, i)] = ne.get(schluessel(d, i), 0) + p
faktor = {k: min(max(za[k] / ne[k], 0.3), 1.6) for k in za if ne[k] > 5}
print("Gelernte Faktoren (Training), Stunde 0..3 nach Sonnenaufgang:")
for k in KLASSEN:
    for halb in ("s", "w"):
        f = [faktor.get((k, halb, i)) for i in range(MORGEN_STUNDEN)]
        print(f"  {k:20} {halb}: " + "  ".join("  -  " if x is None else f"{x:.2f}" for x in f))
print()

# 3) Wirkung im Test 2026
fm_o = fm_k = ft_o = ft_k = 0.0
gute_o, gute_k, n = [], [], 0
for d in tage:
    if not d["test"]:
        continue
    korr = sum(p * faktor.get(schluessel(d, i), 1.0) - p for i, p, _ in d["morgen"])
    fm_o += abs(d["p_morgen"] - d["m_morgen"])
    fm_k += abs(d["p_morgen"] + korr - d["m_morgen"])
    ft_o += abs(d["p_tag"] - d["m_tag"])
    ft_k += abs(d["p_tag"] + korr - d["m_tag"])
    if d["m_tag"] > 3:
        gute_o.append(abs(d["p_tag"] - d["m_tag"]) / d["m_tag"])
        gute_k.append(abs(d["p_tag"] + korr - d["m_tag"]) / d["m_tag"])
    n += 1
print(f"Test 2026 ({n} Tage)            ohne Tau   mit Tau")
print(f"  Fehler Morgen  (kWh/Tag)     {fm_o / n:8.3f}  {fm_k / n:8.3f}")
print(f"  Fehler Tag     (kWh/Tag)     {ft_o / n:8.3f}  {ft_k / n:8.3f}")
print(f"  Fehler Tag > 3 kWh (%)       {st.mean(gute_o) * 100:8.1f}  {st.mean(gute_k) * 100:8.1f}")
