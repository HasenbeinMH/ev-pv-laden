# -*- coding: utf-8 -*-
"""
Verschmutzung sichtbar machen: Verhaeltnis Messung / Kennfeld-Prognose (M1) ueber die Zeit.
Das Kennfeld wird dafuer auf ALLEN Daten gelernt (hier geht es um den Verlauf, nicht um
einen fairen Test). Wetterfehler mitteln sich ueber 14 Tage weitgehend heraus; was bleibt,
ist ein langsam fallender Wert (Schmutz) mit Spruengen nach oben (Reinigung, Starkregen).

    python dev/modell/verschmutzung.py
"""
import os

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import auswertung as a  # noqa: E402

df = a.qualitaet(a.laden())
wg = a.fit_m0(df)
g = a.kennfeld(df, wg)
df["m1"] = a.wende_kennfeld(df, g, wg)
tage = df.groupby("datum").agg(mess=("pv_kwh", "sum"), prog=("m1", "sum"),
                              regen_mm=("snow_depth", "size"))
tage.index = pd.to_datetime(tage.index)
# nur Tage mit nennenswerter Prognose (bei Dunkelheit ist das Verhaeltnis Rauschen)
t = tage[tage["prog"] > 4].copy()
t["quote"] = t["mess"] / t["prog"]
t["gleitend"] = t["quote"].rolling("14D", min_periods=5).median()

# Spruenge suchen: Median der 10 Tage danach gegen die 10 Tage davor
werte = t["quote"]
spruenge = []
for i in range(10, len(werte) - 10):
    vor, nach = werte.iloc[i - 10:i].median(), werte.iloc[i:i + 10].median()
    if nach / vor > 1.18:
        spruenge.append((werte.index[i].date(), round(vor, 2), round(nach, 2), round((nach / vor - 1) * 100)))
# benachbarte Treffer zusammenfassen (groesster Sprung je 3 Wochen)
zusammen = []
for s in spruenge:
    if zusammen and (pd.Timestamp(s[0]) - pd.Timestamp(zusammen[-1][0])).days < 21:
        if s[3] > zusammen[-1][3]:
            zusammen[-1] = s
    else:
        zusammen.append(s)
print("Spruenge nach oben (> 18 %, Median 10 Tage vorher/nachher):")
for s in zusammen:
    print(f"  {s[0]}: {s[1]} -> {s[2]}  (+{s[3]} %)")

fig, ax = plt.subplots(figsize=(13, 4.5))
ax.scatter(t.index, t["quote"], s=6, color="#9ca3af", alpha=.6, label="Tag: Messung / Prognose")
ax.plot(t.index, t["gleitend"], color="#16a34a", lw=2, label="gleitender Median 14 Tage")
for s in zusammen:
    ax.axvline(pd.Timestamp(s[0]), color="#f59e0b", ls="--", lw=1)
    ax.text(pd.Timestamp(s[0]), 1.55, f"+{s[3]} %", color="#b45309", fontsize=8, ha="center")
ax.axhline(1, color="#111827", lw=.8)
ax.set_ylim(0.2, 1.65)
ax.set_ylabel("Messung / Kennfeld-Prognose")
ax.set_title("Verschmutzung über die Zeit (Sprünge nach oben = Reinigung oder Starkregen)")
ax.legend(loc="lower left")
ziel = os.path.join(a.AUSGABE, "5_verschmutzung.png")
fig.savefig(ziel, dpi=120, bbox_inches="tight")
print("Grafik:", ziel)
