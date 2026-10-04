# -*- coding: utf-8 -*-
"""
Verschmutzung mit nachtraeglich gemessener Einstrahlung (Open-Meteo Archiv statt Prognose):
    Messung ~ Einstrahlung x Kennfeld(Sonnenstand, Halbjahr) x Sauberkeit(Woche)
Kennfeld und Sauberkeit werden abwechselnd geschaetzt (wie eine Zerlegung in zwei Faktoren).
Sauberkeit ist so normiert, dass die saubersten Wochen (90-%-Quantil) = 1 sind.

    python dev/modell/verschmutzung2.py
"""
import json
import os

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import auswertung as a  # noqa: E402


def archiv(name):
    d = json.load(open(os.path.join(a.DATEN, f"arch_{name}.json")))
    h = pd.DataFrame(d["hourly"])
    h["zeit_utc"] = pd.to_datetime(h.pop("time")).dt.tz_localize("UTC") - pd.Timedelta(hours=1)
    return h.set_index("zeit_utc")


pv = pd.read_csv(os.path.join(a.DATEN, "pv_stunden.csv"), parse_dates=["zeit_utc"]).set_index("zeit_utc")
basis = archiv("basis")
for f in a.KWP:
    basis[f"gti_{f}"] = archiv(f"gti_{f}")["global_tilted_irradiance"]
df = pv.join(basis, how="inner")
df["sonne_el"], df["sonne_az"] = a.sonnenstand(df.index + pd.Timedelta(minutes=30))
df["phys"] = sum(df[f"gti_{f}"] / 1000 * a.KWP[f] for f in a.KWP)
lokal = df.index.tz_convert("Europe/Berlin")
df["datum"], df["monat"] = lokal.date, lokal.month
df = a.qualitaet(df)
df["woche"] = lokal[df.index.isin(df.index)].to_period("W").start_time if False else \
    df.index.tz_convert("Europe/Berlin").tz_localize(None).to_period("W").start_time
d = df[(df["sonne_el"] > 3) & (df["phys"] > 0.15)].copy()
d["halb"] = np.where(d["monat"].isin(a.SOMMER), "s", "w")
d["az_b"] = (d["sonne_az"] // a.AZ_BIN) * a.AZ_BIN
d["el_b"] = (d["sonne_el"] // a.EL_BIN) * a.EL_BIN
d["bin"] = d["halb"] + "_" + d["az_b"].astype(int).astype(str) + "_" + d["el_b"].astype(int).astype(str)

s = pd.Series(1.0, index=d["woche"].unique())
for _ in range(12):
    d["s"] = d["woche"].map(s)
    k = d.groupby("bin").apply(lambda g: g["pv_kwh"].sum() / (g["phys"] * g["s"]).sum(), include_groups=False)
    d["k"] = d["bin"].map(k)
    s = d.groupby("woche").apply(lambda g: g["pv_kwh"].sum() / (g["phys"] * g["k"]).sum(), include_groups=False)
    s = s / s.quantile(0.9)
# Wochen mit wenig Sonne sind unsicher
energie = d.groupby("woche")["phys"].sum()
s = s[energie > energie.quantile(0.15)]
d["s"] = d["woche"].map(s)

verlust = 1 - (d["pv_kwh"].sum() / (d["pv_kwh"] / d["s"]).sum())
print(f"Sauberkeit: Median {s.median():.2f}, 10-%-Quantil {s.quantile(.1):.2f}")
print(f"Ertragsverlust durch Verschmutzung (gegenueber sauberster Zeit): {verlust * 100:.0f} %")

regen = basis["precipitation"].groupby(basis.index.tz_convert("Europe/Berlin").date).sum()
regen.index = pd.to_datetime(regen.index)
starkregen = regen[regen >= 10]

fig, (ax, ax2) = plt.subplots(2, 1, figsize=(13, 6), sharex=True, height_ratios=[3, 1])
ax.plot(s.index, s.values, color="#16a34a", marker="o", ms=3, lw=1.5, label="Sauberkeit je Woche")
ax.axhline(1, color="#111827", lw=.8)
ax.axvline(pd.Timestamp("2025-05-23"), color="#f59e0b", ls="--", lw=1.2)
ax.text(pd.Timestamp("2025-05-23"), 1.12, "Reinigung Mai 2025", color="#b45309", fontsize=9, ha="center")
ax.set_ylim(0.4, 1.2)
ax.set_ylabel("Sauberkeit (1 = sauberste Wochen)")
ax.set_title("Verschmutzung je Woche (gemessene Einstrahlung, Verschattung herausgerechnet)")
ax.legend(loc="lower left")
ax2.bar(regen.index, regen.values, width=1, color="#3b82f6")
ax2.set_ylabel("Regen (mm/Tag)")
fig.savefig(os.path.join(a.AUSGABE, "6_sauberkeit.png"), dpi=120, bbox_inches="tight")
s.to_csv(os.path.join(a.AUSGABE, "sauberkeit_woche.csv"))
print("Grafik:", os.path.join(a.AUSGABE, "6_sauberkeit.png"))
