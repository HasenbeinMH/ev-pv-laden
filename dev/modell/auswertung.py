# -*- coding: utf-8 -*-
"""
Erste Auswertung: eigenes PV-Prognosemodell aus HA-Historie + Open-Meteo-Archivprognosen.

Eingaben (dev/data/modell, nicht im Repo):
  pv_stunden.csv     gemessene PV je Stunde (daten_zusammenfuehren.py)
  om_basis.json      Open-Meteo Historical Forecast: GHI/DNI/DHI, Temperatur, Wolken, Schnee
  om_gti_<flaeche>   Einstrahlung auf die geneigte Flaeche (tilt/azimuth je Flaeche)

Zeitbezug: HA-Statistik "start=t" = Stunde [t, t+1h). Open-Meteo-Strahlung zum Zeitpunkt T
= Mittel ueber [T-1h, T]. Also gehoert Messung t zu Open-Meteo t+1h.

Modelle (Training 2024–2025, Test 2026 – das Modell sieht die Testdaten nie):
  M0 Standard:  Summe GTI je Flaeche x 3,33 kWp x Wirkungsgrad (ein Faktor, gelernt)
  M1 Kennfeld:  M0 x Korrekturfaktor je Sonnenstand (Azimut x Hoehe), Sommer/Winter getrennt
  M2 ML:        Gradient Boosting auf Einstrahlung, Sonnenstand, Wetter, Jahreszeit

    python dev/modell/auswertung.py
"""
import json
import os

import matplotlib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HIER = os.path.dirname(os.path.abspath(__file__))
DATEN = os.path.join(os.path.dirname(HIER), "data", "modell")
AUSGABE = os.path.join(DATEN, "bericht")
# Standort lokal in dev/data/modell/standort.json ({"lat": .., "lon": ..}) – nicht im Repo
LAT, LON = (lambda d: (d["lat"], d["lon"]))(json.load(open(os.path.join(DATEN, "standort.json"))))
KWP = {"sued": 3.33, "nord": 3.33, "ost": 3.33}
AZ_BIN, EL_BIN = 15, 5
SOMMER = [4, 5, 6, 7, 8, 9]          # Laub am Baum (grob)


# ── Sonnenstand (NOAA, vektorisiert) ─────────────────────────────────────────────
def sonnenstand(zeit_utc: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray]:
    """Elevation und Azimut (0 = Nord, 90 = Ost) in Grad fuer UTC-Zeitpunkte."""
    jd = zeit_utc.to_julian_date().to_numpy()
    jc = (jd - 2451545.0) / 36525
    l0 = (280.46646 + jc * (36000.76983 + jc * 0.0003032)) % 360
    m = np.radians(357.52911 + jc * (35999.05029 - 0.0001537 * jc))
    e = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)
    c = (np.sin(m) * (1.914602 - jc * (0.004817 + 0.000014 * jc))
         + np.sin(2 * m) * (0.019993 - 0.000101 * jc) + np.sin(3 * m) * 0.000289)
    lam = np.radians(l0 + c - 0.00569 - 0.00478 * np.sin(np.radians(125.04 - 1934.136 * jc)))
    eps = np.radians(23 + (26 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60) / 60
                     + 0.00256 * np.cos(np.radians(125.04 - 1934.136 * jc)))
    dekl = np.arcsin(np.sin(eps) * np.sin(lam))
    y = np.tan(eps / 2) ** 2
    l0r = np.radians(l0)
    zeitgl = 4 * np.degrees(y * np.sin(2 * l0r) - 2 * e * np.sin(m) + 4 * e * y * np.sin(m) * np.cos(2 * l0r)
                            - 0.5 * y * y * np.sin(4 * l0r) - 1.25 * e * e * np.sin(2 * m))
    minuten = zeit_utc.hour.to_numpy() * 60 + zeit_utc.minute.to_numpy()
    stundenwinkel = np.radians((minuten + zeitgl + 4 * LON) / 4 - 180)
    lat = np.radians(LAT)
    cos_z = np.sin(lat) * np.sin(dekl) + np.cos(lat) * np.cos(dekl) * np.cos(stundenwinkel)
    zenit = np.arccos(np.clip(cos_z, -1, 1))
    el = 90 - np.degrees(zenit)
    az = np.degrees(np.arctan2(np.sin(stundenwinkel),
                               np.cos(stundenwinkel) * np.sin(lat) - np.tan(dekl) * np.cos(lat))) + 180
    return el, az % 360


# ── Daten ────────────────────────────────────────────────────────────────────────
def laden() -> pd.DataFrame:
    pv = pd.read_csv(os.path.join(DATEN, "pv_stunden.csv"), parse_dates=["zeit_utc"])
    pv["zeit_utc"] = pv["zeit_utc"].dt.tz_convert("UTC")
    pv = pv.set_index("zeit_utc")

    def om(name):
        d = json.load(open(os.path.join(DATEN, f"om_{name}.json")))
        h = pd.DataFrame(d["hourly"])
        h["time"] = pd.to_datetime(h["time"]).dt.tz_localize("UTC")
        # Open-Meteo T = Mittel ueber [T-1h, T] -> auf Stundenbeginn der Messung schieben
        h["zeit_utc"] = h.pop("time") - pd.Timedelta(hours=1)
        return h.set_index("zeit_utc")

    basis = om("basis")
    for f in KWP:
        basis[f"gti_{f}"] = om(f"gti_{f}")["global_tilted_irradiance"]
    df = pv.join(basis, how="inner")
    mitte = df.index + pd.Timedelta(minutes=30)
    df["sonne_el"], df["sonne_az"] = sonnenstand(mitte)
    df["phys_kwh"] = sum(df[f"gti_{f}"] / 1000 * KWP[f] for f in KWP)
    lokal = df.index.tz_convert("Europe/Berlin")
    df["datum"] = lokal.date
    df["monat"] = lokal.month
    df["doy"] = lokal.dayofyear
    return df


def qualitaet(df: pd.DataFrame) -> pd.DataFrame:
    """Tage mit unvollstaendiger Messung verwerfen (Luecken in der Statistik)."""
    stunden = df.groupby("datum").size()
    voll = stunden[stunden >= 23].index
    raus = df[~df["datum"].isin(voll)]["datum"].nunique()
    print(f"Qualitaet: {raus} Tage mit < 23 Stunden verworfen")
    return df[df["datum"].isin(voll)].copy()


# ── Modelle ──────────────────────────────────────────────────────────────────────
def fit_m0(train):
    tag = train[train["sonne_el"] > 0]
    return (tag["pv_kwh"] * tag["phys_kwh"]).sum() / (tag["phys_kwh"] ** 2).sum()


def kennfeld(train, wg):
    """Faktor Messung/Standard je (Halbjahr, Azimut-Bin, Hoehen-Bin), nur Stunden mit
    nennenswerter Direktstrahlung; duenn besetzte Felder -> 1."""
    t = train[(train["sonne_el"] > 2) & (train["phys_kwh"] > 0.2)].copy()
    t["halb"] = np.where(t["monat"].isin(SOMMER), "sommer", "winter")
    t["az_b"] = (t["sonne_az"] // AZ_BIN) * AZ_BIN
    t["el_b"] = (t["sonne_el"] // EL_BIN) * EL_BIN
    g = t.groupby(["halb", "az_b", "el_b"]).agg(mess=("pv_kwh", "sum"), std=("phys_kwh", "sum"),
                                              n=("pv_kwh", "size"))
    g["faktor"] = (g["mess"] / (g["std"] * wg)).clip(0.05, 1.6)
    g.loc[g["n"] < 15, "faktor"] = np.nan
    return g


def wende_kennfeld(df, g, wg):
    halb = np.where(df["monat"].isin(SOMMER), "sommer", "winter")
    az_b = (df["sonne_az"] // AZ_BIN) * AZ_BIN
    el_b = (df["sonne_el"] // EL_BIN) * EL_BIN
    idx = pd.MultiIndex.from_arrays([halb, az_b, el_b])
    f = g["faktor"].reindex(idx).to_numpy()
    f = np.where(np.isnan(f), 1.0, f)
    return np.where(df["sonne_el"] > 0, df["phys_kwh"] * wg * f, 0.0)


MERKMALE = ["gti_sued", "gti_nord", "gti_ost", "shortwave_radiation", "direct_radiation",
            "diffuse_radiation", "direct_normal_irradiance", "temperature_2m", "cloud_cover",
            "snow_depth", "wind_speed_10m", "sonne_el", "sonne_az", "doy_sin", "doy_cos"]


def ml(train, test):
    for d in (train, test):
        d["doy_sin"] = np.sin(2 * np.pi * d["doy"] / 365.25)
        d["doy_cos"] = np.cos(2 * np.pi * d["doy"] / 365.25)
    m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, max_leaf_nodes=31,
                                      min_samples_leaf=40, random_state=1)
    m.fit(train[MERKMALE], train["pv_kwh"])
    return np.clip(m.predict(test[MERKMALE]), 0, None)


def kennzahlen(name, test, spalte):
    h = test["pv_kwh"] - test[spalte]
    tage = test.groupby("datum")[["pv_kwh", spalte]].sum()
    td = tage[spalte] - tage["pv_kwh"]
    gute = tage[tage["pv_kwh"] > 3]
    return {
        "Modell": name,
        "RMSE Stunde (kWh)": round(float(np.sqrt((h ** 2).mean())), 3),
        "MAE Tag (kWh)": round(float(td.abs().mean()), 2),
        "MAPE Tag >3 kWh (%)": round(float(((gute[spalte] - gute["pv_kwh"]).abs() / gute["pv_kwh"]).mean() * 100), 1),
        "Bias Summe (%)": round(float((tage[spalte].sum() / tage["pv_kwh"].sum() - 1) * 100), 1),
    }


# ── Bericht ──────────────────────────────────────────────────────────────────────
def grafiken(df, test, g):
    os.makedirs(AUSGABE, exist_ok=True)
    # 1) Kennfeld (Verschattungskarte) je Halbjahr
    fig, achsen = plt.subplots(1, 2, figsize=(13, 4.5), sharey=True)
    for ax, halb in zip(achsen, ("sommer", "winter")):
        k = g.loc[halb]["faktor"].unstack("el_b")
        bild = ax.pcolormesh(k.index, k.columns, k.T.to_numpy(), cmap="RdYlGn", vmin=0.3, vmax=1.3,
                             shading="nearest")
        ax.set_title(f"Korrekturfaktor {'Apr–Sep' if halb == 'sommer' else 'Okt–Mär'}")
        ax.set_xlabel("Sonnenazimut (90 = Ost, 180 = Süd, 270 = West)")
        ax.set_xticks(range(60, 301, 30))
    achsen[0].set_ylabel("Sonnenhöhe (°)")
    fig.colorbar(bild, ax=achsen, label="Messung / Standardmodell")
    fig.savefig(os.path.join(AUSGABE, "1_verschattungskarte.png"), dpi=120, bbox_inches="tight")
    plt.close(fig)

    # 2) Tagessummen Test: Modell gegen Messung
    tage = test.groupby("datum")[["pv_kwh", "m0", "m1", "m2"]].sum()
    fig, ax = plt.subplots(figsize=(6.5, 6))
    for sp, farbe, name in (("m0", "#9ca3af", "M0 Standard"), ("m1", "#f59e0b", "M1 Kennfeld"),
                            ("m2", "#16a34a", "M2 ML")):
        ax.scatter(tage["pv_kwh"], tage[sp], s=10, alpha=.6, color=farbe, label=name)
    gr = max(tage.max()) * 1.05
    ax.plot([0, gr], [0, gr], color="#111827", lw=1)
    ax.set_xlabel("gemessen (kWh/Tag)")
    ax.set_ylabel("Prognose (kWh/Tag)")
    ax.set_title("Testjahr 2026: Tagessummen")
    ax.legend()
    fig.savefig(os.path.join(AUSGABE, "2_tagessummen_test.png"), dpi=120, bbox_inches="tight")
    plt.close(fig)

    # 3) Beispieltage
    beispiele = [d for d in (pd.Timestamp("2026-10-03").date(), pd.Timestamp("2026-06-21").date(),
                             pd.Timestamp("2026-03-15").date()) if d in set(test["datum"])]
    fig, achsen = plt.subplots(1, len(beispiele), figsize=(5 * len(beispiele), 3.8), sharey=True)
    for ax, d in zip(np.atleast_1d(achsen), beispiele):
        t = test[test["datum"] == d]
        x = t.index.tz_convert("Europe/Berlin").hour
        ax.bar(x, t["pv_kwh"], color="#fcd34d", label="gemessen")
        ax.plot(x, t["m0"], color="#6b7280", lw=1.5, label="M0 Standard")
        ax.plot(x, t["m1"], color="#f59e0b", lw=2, label="M1 Kennfeld")
        ax.plot(x, t["m2"], color="#16a34a", lw=2, label="M2 ML")
        ax.set_title(str(d))
        ax.set_xlabel("Uhrzeit")
    np.atleast_1d(achsen)[0].set_ylabel("kWh je Stunde")
    np.atleast_1d(achsen)[0].legend(fontsize=8)
    fig.savefig(os.path.join(AUSGABE, "3_beispieltage.png"), dpi=120, bbox_inches="tight")
    plt.close(fig)

    # 4) Monatsabweichung Test
    mon = test.groupby("monat")[["pv_kwh", "m0", "m1", "m2"]].sum()
    fig, ax = plt.subplots(figsize=(8, 3.8))
    breite = 0.27
    for i, (sp, farbe, name) in enumerate((("m0", "#9ca3af", "M0"), ("m1", "#f59e0b", "M1"),
                                            ("m2", "#16a34a", "M2"))):
        ax.bar(mon.index + (i - 1) * breite, (mon[sp] / mon["pv_kwh"] - 1) * 100, breite,
               color=farbe, label=name)
    ax.axhline(0, color="#111827", lw=1)
    ax.set_xlabel("Monat 2026")
    ax.set_ylabel("Abweichung Summe (%)")
    ax.legend()
    fig.savefig(os.path.join(AUSGABE, "4_monatsabweichung.png"), dpi=120, bbox_inches="tight")
    plt.close(fig)


def main():
    df = qualitaet(laden())
    train = df[df.index < "2026-01-01"].copy()
    test = df[(df.index >= "2026-01-01") & (df.index < "2026-10-04")].copy()
    print(f"Training {train['datum'].nunique()} Tage, Test {test['datum'].nunique()} Tage")

    wg = fit_m0(train)
    print(f"M0: Wirkungsgrad-Faktor (Messung / Einstrahlung x kWp) = {wg:.3f}")
    g = kennfeld(train, wg)
    for d in (train, test):
        d["m0"] = np.where(d["sonne_el"] > 0, d["phys_kwh"] * wg, 0)
        d["m1"] = wende_kennfeld(d, g, wg)
    test["m2"] = ml(train, test)

    tab = pd.DataFrame([kennzahlen("M0 Standard", test, "m0"), kennzahlen("M1 Kennfeld", test, "m1"),
                        kennzahlen("M2 ML", test, "m2")])
    print(tab.to_string(index=False))

    # Flaechenvergleich wie Layout 03.10.2026: Anteil der Ost-Flaeche am Standardmodell
    t = test[test["datum"] == pd.Timestamp("2026-10-03").date()]
    if len(t):
        print("03.10.2026:", {k: round(float(t[k].sum()), 2) for k in ("pv_kwh", "m0", "m1", "m2")})
    grafiken(df, test, g)
    os.makedirs(AUSGABE, exist_ok=True)
    tab.to_csv(os.path.join(AUSGABE, "kennzahlen.csv"), index=False)
    print("Grafiken:", AUSGABE)


if __name__ == "__main__":
    main()
