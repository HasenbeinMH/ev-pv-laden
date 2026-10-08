# -*- coding: utf-8 -*-
"""
Eigenes PV-Prognosemodell, auf die Anlage zugeschnitten (reine Logik, ohne numpy).

Prognose (Kennfeld M1 – im Test 2026 das genaueste Verfahren):
    PV(Stunde) = Einstrahlung je Flaeche x kWp  x  K(Sonnenstand, Halbjahr)  x  Reinigungszuschlag
  Einstrahlung  Open-Meteo-Prognose, Strahlung auf die geneigte Flaeche (GTI), Stundenmittel
  K             gelernter Faktor je Sonnenstand (Azimut x Hoehe) und Halbjahr (Laub):
                Verschattung, Wirkungsgrad, mittlere Verschmutzung und systematische Fehler
                der Wetterprognose – alles, was an dieser Anlage anders ist als im Lehrbuch
  Zuschlag      nur nach dem Knopf "gereinigt": Sauberkeit jetzt / Sauberkeit im Mittel

Sauberkeit (Information und Reinigungshinweis, nicht Teil der normalen Prognose):
    Messung ~ GTI_Archiv x K_archiv(Bin) x S(Woche)      (Faktorzerlegung)
  mit nachtraeglich gemessener Einstrahlung (Open-Meteo-Archiv) – so faellt der Wetterfehler
  heraus. S = 1 entspricht den saubersten Wochen der Historie.
  Warum nicht in jede Prognose? Getestet (dev/modell/): Die laufende Schaetzung schwankt um
  einige Prozent und machte die Tagesprognose schlechter (2,77 -> 3,04 kWh Fehler/Tag).

Herleitung und Pruefung: dev/modell/ (auswertung.py, verschmutzung2.py, pruefen_pvmodell.py).
"""
import math
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone

AZ_BIN, EL_BIN = 15, 5
SOMMER = {4, 5, 6, 7, 8, 9}           # Monate mit Laub (grob)
MIN_STUNDEN_JE_BIN = 15
FAKTOR_MIN, FAKTOR_MAX = 0.05, 1.6
EL_MIN_PROGNOSE, PHYS_MIN_PROGNOSE = 2.0, 0.2
EL_MIN_SAUBER, PHYS_MIN_SAUBER = 3.0, 0.15
SAUBERKEIT_FENSTER_TAGE = 14
SAUBERKEIT_MIN_KWH = 20.0              # so viel Einstrahlung im Fenster, sonst keine Aussage
WINTER_OHNE_SCHMUTZ = {11, 12, 1, 2}   # Schnee/tiefe Sonne: Schaetzung unzuverlaessig
ZUSCHLAG_TAGE = 90                     # so lange wirkt "gereinigt" auf die Prognose
ZUSCHLAG_MIN, ZUSCHLAG_MAX = 0.8, 1.35


# ── Sonnenstand (NOAA) ─────────────────────────────────────────────────────────────
def sonnenstand(t: datetime, lat: float, lon: float) -> tuple[float, float]:
    """Hoehe und Azimut (0 = Nord, 90 = Ost) in Grad. t zeitzonenbewusst."""
    t = t.astimezone(timezone.utc)
    jd = t.timestamp() / 86400 + 2440587.5
    jc = (jd - 2451545.0) / 36525
    l0 = (280.46646 + jc * (36000.76983 + jc * 0.0003032)) % 360
    m = math.radians(357.52911 + jc * (35999.05029 - 0.0001537 * jc))
    e = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)
    c = (math.sin(m) * (1.914602 - jc * (0.004817 + 0.000014 * jc))
         + math.sin(2 * m) * (0.019993 - 0.000101 * jc) + math.sin(3 * m) * 0.000289)
    omega = math.radians(125.04 - 1934.136 * jc)
    lam = math.radians(l0 + c - 0.00569 - 0.00478 * math.sin(omega))
    eps = math.radians(23 + (26 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60) / 60
                       + 0.00256 * math.cos(omega))
    dekl = math.asin(math.sin(eps) * math.sin(lam))
    y = math.tan(eps / 2) ** 2
    l0r = math.radians(l0)
    zeitgl = 4 * math.degrees(y * math.sin(2 * l0r) - 2 * e * math.sin(m)
                              + 4 * e * y * math.sin(m) * math.cos(2 * l0r)
                              - 0.5 * y * y * math.sin(4 * l0r) - 1.25 * e * e * math.sin(2 * m))
    minuten = t.hour * 60 + t.minute + t.second / 60
    hw = math.radians((minuten + zeitgl + 4 * lon) / 4 - 180)
    br = math.radians(lat)
    cos_z = math.sin(br) * math.sin(dekl) + math.cos(br) * math.cos(dekl) * math.cos(hw)
    zenit = math.acos(max(-1.0, min(1.0, cos_z)))
    az = math.degrees(math.atan2(math.sin(hw), math.cos(hw) * math.sin(br) - math.tan(dekl) * math.cos(br))) + 180
    return 90 - math.degrees(zenit), az % 360


@dataclass(frozen=True)
class Flaeche:
    name: str
    neigung: float        # Grad
    azimut: float         # 0 = Nord, 90 = Ost, 180 = Sued, 270 = West (wie Forecast.Solar)
    kwp: float

    @property
    def om_azimut(self) -> float:
        """Open-Meteo: 0 = Sued, -90 = Ost, 90 = West, +-180 = Nord."""
        a = (self.azimut - 180) % 360
        return a - 360 if a > 180 else a


def phys_kwh(gti: dict[str, float], flaechen: list[Flaeche]) -> float:
    """Einstrahlung je Flaeche (W/m2, Stundenmittel) -> kWh der Stunde bei Faktor 1."""
    return sum((gti.get(f.name) or 0.0) / 1000 * f.kwp for f in flaechen)


def bin_von(t_beginn: datetime, lat: float, lon: float, monat: int) -> tuple[str | None, float]:
    """Kennfeld-Feld fuer die Stunde ab t_beginn (Sonnenstand in der Stundenmitte)."""
    el, az = sonnenstand(t_beginn + timedelta(minutes=30), lat, lon)
    if el <= 0:
        return None, el
    halb = "s" if monat in SOMMER else "w"
    return f"{halb}_{int(az // AZ_BIN) * AZ_BIN}_{int(el // EL_BIN) * EL_BIN}", el


# ── Modell ─────────────────────────────────────────────────────────────────────────
@dataclass
class Modell:
    k_prognose: dict = field(default_factory=dict)
    k_archiv: dict = field(default_factory=dict)
    k_standard: float = 0.8              # fuer Felder ohne genug Daten
    sauberkeit: float | None = None      # letzte Schaetzung (1 = sauberste Wochen)
    sauberkeit_stand: str | None = None  # Datum dieser Schaetzung
    sauberkeit_mittel: float = 1.0       # Mittel der Historie (steckt im Kennfeld)
    gereinigt_am: str | None = None
    trainiert_am: str | None = None
    kennzahlen: dict = field(default_factory=dict)
    sauberkeit_wochen: dict = field(default_factory=dict)   # Woche -> Wert (Verlauf)
    wettermodell: str = "best_match"     # mit diesem Wettermodell trainiert (Option wettermodell)

    def als_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def aus_dict(cls, d: dict | None) -> "Modell":
        m = cls()
        for k, v in (d or {}).items():
            if hasattr(m, k):
                setattr(m, k, v)
        return m

    @property
    def trainiert(self) -> bool:
        return bool(self.k_prognose)

    def zuschlag(self, heute: date) -> float:
        """Nach einer Reinigung ist die Anlage sauberer als im Mittel, das im Kennfeld steckt."""
        if not self.gereinigt_am or self.sauberkeit is None:
            return 1.0
        if (heute - date.fromisoformat(self.gereinigt_am)).days > ZUSCHLAG_TAGE:
            return 1.0
        return min(max(self.sauberkeit / self.sauberkeit_mittel, ZUSCHLAG_MIN), ZUSCHLAG_MAX)

    def verlust_prozent(self) -> float | None:
        """Ertragsverlust durch Schmutz gegenueber den saubersten Wochen."""
        return None if self.sauberkeit is None else round((1 - self.sauberkeit) * 100, 1)

    def prognose(self, stunden: list[tuple[datetime, dict]], flaechen: list[Flaeche],
                 lat: float, lon: float, tz) -> list[tuple[datetime, float]]:
        """stunden: (Stundenbeginn UTC, {flaeche: GTI}) -> (Stundenbeginn, kWh)."""
        aus = []
        for t, gti in stunden:
            lokal = t.astimezone(tz)
            schluessel, _ = bin_von(t, lat, lon, lokal.month)
            if schluessel is None:
                aus.append((t, 0.0))
                continue
            k = self.k_prognose.get(schluessel, self.k_standard)
            aus.append((t, max(phys_kwh(gti, flaechen) * k * self.zuschlag(lokal.date()), 0.0)))
        return aus


# ── Training ───────────────────────────────────────────────────────────────────────
def _woche(t: datetime, tz) -> str:
    lokal = t.astimezone(tz)
    return (lokal - timedelta(days=lokal.weekday())).date().isoformat()


def _ausfalltage(zeilen) -> set:
    """Tage mit fast keiner Erzeugung trotz Sonne (Wechselrichter/HA aus, Schnee)."""
    m, p = {}, {}
    for z in zeilen:
        m[z["tag"]] = m.get(z["tag"], 0.0) + z["m"]
        p[z["tag"]] = p.get(z["tag"], 0.0) + z["pa"]
    return {d for d in m if p[d] > 5 and m[d] < 0.1 * p[d]}


def trainieren(mess: dict[datetime, float], prog: dict[datetime, dict], archiv: dict[datetime, dict],
               flaechen: list[Flaeche], lat: float, lon: float, tz, iterationen: int = 12) -> Modell:
    """mess: Stundenbeginn UTC -> gemessene PV (kWh). prog/archiv: Stundenbeginn UTC ->
    {flaeche: GTI} (Open-Meteo-Prognose bzw. -Archiv)."""
    alle = []
    for t, kwh in mess.items():
        if t not in archiv or t not in prog:
            continue
        lokal = t.astimezone(tz)
        schluessel, el = bin_von(t, lat, lon, lokal.month)
        if schluessel is None:
            continue
        alle.append({"bin": schluessel, "el": el, "woche": _woche(t, tz), "tag": lokal.date(),
                     "m": kwh, "pa": phys_kwh(archiv[t], flaechen), "pp": phys_kwh(prog[t], flaechen)})
    ausfall = _ausfalltage(alle)
    alle = [z for z in alle if z["tag"] not in ausfall]

    # 1) Prognose-Kennfeld (M1): Messung / Prognose-Einstrahlung je Feld
    zaehler, nenner, anzahl = {}, {}, {}
    for z in alle:
        if z["el"] <= EL_MIN_PROGNOSE or z["pp"] <= PHYS_MIN_PROGNOSE:
            continue
        b = z["bin"]
        zaehler[b] = zaehler.get(b, 0.0) + z["m"]
        nenner[b] = nenner.get(b, 0.0) + z["pp"]
        anzahl[b] = anzahl.get(b, 0) + 1
    if sum(anzahl.values()) < 500:
        raise ValueError(f"zu wenig Trainingsdaten ({sum(anzahl.values())} Sonnenstunden)")
    k_prog = {b: _begrenzen(zaehler[b] / nenner[b]) for b in zaehler if anzahl[b] >= MIN_STUNDEN_JE_BIN}
    k_standard = _begrenzen(sum(zaehler.values()) / sum(nenner.values()))

    # 2) Sauberkeit je Woche: Faktorzerlegung auf gemessener Einstrahlung
    zeilen = [z for z in alle if z["el"] >= EL_MIN_SAUBER and z["pa"] >= PHYS_MIN_SAUBER]
    s = {z["woche"]: 1.0 for z in zeilen}
    k_arch: dict[str, float] = {}
    for _ in range(iterationen):
        za, ne = {}, {}
        for z in zeilen:
            za[z["bin"]] = za.get(z["bin"], 0.0) + z["m"]
            ne[z["bin"]] = ne.get(z["bin"], 0.0) + z["pa"] * s[z["woche"]]
        k_arch = {b: za[b] / ne[b] for b in za if ne[b] > 0}
        za, ne = {}, {}
        for z in zeilen:
            za[z["woche"]] = za.get(z["woche"], 0.0) + z["m"]
            ne[z["woche"]] = ne.get(z["woche"], 0.0) + z["pa"] * k_arch[z["bin"]]
        s = {w: za[w] / ne[w] for w in za if ne[w] > 0}
        q90 = _quantil(list(s.values()), 0.9)
        s = {w: v / q90 for w, v in s.items()}
    anzahl_a, sonne = {}, {}
    for z in zeilen:
        anzahl_a[z["bin"]] = anzahl_a.get(z["bin"], 0) + 1
        sonne[z["woche"]] = sonne.get(z["woche"], 0.0) + z["pa"]
    k_arch = {b: _begrenzen(v) for b, v in k_arch.items() if anzahl_a[b] >= MIN_STUNDEN_JE_BIN}
    grenze = _quantil(list(sonne.values()), 0.15)
    verlaesslich = {w: round(v, 3) for w, v in sorted(s.items())
                    if sonne[w] > grenze and int(w[5:7]) not in WINTER_OHNE_SCHMUTZ}
    mittel = sum(verlaesslich.values()) / len(verlaesslich) if verlaesslich else 1.0
    letzte = max(verlaesslich) if verlaesslich else None

    return Modell(
        k_prognose=k_prog, k_archiv=k_arch, k_standard=k_standard,
        sauberkeit=verlaesslich.get(letzte) if letzte else None, sauberkeit_stand=letzte,
        sauberkeit_mittel=round(mittel, 3), sauberkeit_wochen=verlaesslich,
        kennzahlen={"sonnenstunden": sum(anzahl.values()), "ausfalltage": len(ausfall),
                    "felder": len(k_prog), "wochen": len(verlaesslich),
                    "verlust_schmutz_prozent": round((1 - mittel) * 100, 1)},
    )


def sauberkeit_schaetzen(modell: Modell, mess: dict[datetime, float], archiv: dict[datetime, dict],
                         flaechen: list[Flaeche], lat: float, lon: float, tz) -> tuple[float | None, float]:
    """Sauberkeit aus einem Zeitfenster (gemessene Einstrahlung). Gibt (Wert oder None,
    Einstrahlung im Fenster in kWh) – None bei zu wenig Sonne oder im Winter."""
    m_sum = p_sum = 0.0
    for t, kwh in mess.items():
        if t not in archiv:
            continue
        lokal = t.astimezone(tz)
        if lokal.month in WINTER_OHNE_SCHMUTZ:
            continue
        schluessel, el = bin_von(t, lat, lon, lokal.month)
        if schluessel is None or el < EL_MIN_SAUBER or schluessel not in modell.k_archiv:
            continue
        pa = phys_kwh(archiv[t], flaechen)
        if pa < PHYS_MIN_SAUBER:
            continue
        m_sum += kwh
        p_sum += pa * modell.k_archiv[schluessel]
    if p_sum < SAUBERKEIT_MIN_KWH:
        return None, p_sum
    return round(min(max(m_sum / p_sum, 0.2), 1.3), 3), p_sum


def _begrenzen(x: float) -> float:
    return round(min(max(x, FAKTOR_MIN), FAKTOR_MAX), 4)


def _quantil(werte: list[float], q: float) -> float:
    w = sorted(werte)
    if not w:
        return 1.0
    pos = (len(w) - 1) * q
    u = int(pos)
    o = min(u + 1, len(w) - 1)
    return w[u] + (w[o] - w[u]) * (pos - u)
