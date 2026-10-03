# -*- coding: utf-8 -*-
"""
Anlagenmodell zum Testen der Strategie ohne echte Wallbox (wie PLCSIM).

Eingang ist nur der Verlauf "PV minus Hauslast" (W, positiv = Ueberschuss). Den kann man
synthetisch erzeugen oder aus aufgezeichneten Messwerten zurueckrechnen:
    PV - Last = -Netz - Akku + Auto     (interne Vorzeichen: Netz Bezug +, Akku Entladung +)

Modell:
  SolarEdge-Akku: laedt aus dem Rest-Ueberschuss (bis max_laden_w, nicht ueber 100 %),
                  entlaedt automatisch bei Defizit (bis max_entladen_w, nicht unter min_soc).
  Netz:           nimmt den Rest auf.
  go-e + Auto:    folgt P_erlaubt in Stromstufen (6..max A), einphasig bis zur
                  Umschaltschwelle, sonst dreiphasig; Stufenwechsel hoechstens alle
                  stufen_s Sekunden (Traegheit der go-e-Regelung und des Fahrzeugs).
"""
import csv
import math
from dataclasses import dataclass, field

from bilanz import aufteilen
from strategie import Eingang, Strategie

U = 230.0


@dataclass
class Akku:
    kapazitaet_kwh: float = 7.1
    soc: float = 50.0
    max_laden_w: float = 5000.0
    max_entladen_w: float = 5000.0
    min_soc: float = 5.0


@dataclass
class Wallbox:
    min_a: int = 6
    max_a: int = 24
    max_a_1ph: int = 16
    umschalt_w: float = 4200.0     # spl3 der go-e
    stufen_s: float = 5.0
    p_ist: float = 0.0
    _t_stufe: float = -1e9

    def nachfuehren(self, t: float, freigabe: bool, p_soll: float) -> float:
        if not freigabe or p_soll <= 0:
            self.p_ist = 0.0
            return 0.0
        if t - self._t_stufe < self.stufen_s:
            return self.p_ist
        self._t_stufe = t
        if p_soll <= self.umschalt_w:
            strom = min(max(math.floor(p_soll / U), self.min_a), self.max_a_1ph)
            self.p_ist = strom * U
        else:
            strom = min(max(math.floor(p_soll / (3 * U)), self.min_a), self.max_a)
            self.p_ist = strom * 3 * U
        return self.p_ist


@dataclass
class Ergebnis:
    verlauf: list = field(default_factory=list)
    kwh_auto: float = 0.0
    kwh: dict = field(default_factory=lambda: {"pv": 0.0, "akku": 0.0, "netz": 0.0})
    kwh_akku_geladen: float = 0.0
    starts: int = 0
    p_erlaubt_max: float = 0.0

    @property
    def anteil_pv(self) -> float:
        return self.kwh["pv"] / self.kwh_auto if self.kwh_auto else 0.0


def simulieren(ueberschuss_w: list[float], strategie: Strategie, akku: Akku | None = None,
               wallbox: Wallbox | None = None, dt: float = 1.0, steckt: bool = True,
               ungueltig: set[int] | None = None, verlauf: bool = False) -> Ergebnis:
    """ueberschuss_w[i] = PV - Hauslast im Schritt i. ungueltig = Schritte, in denen die
    Messwerte als veraltet gelten (Watchdog-Test)."""
    akku = akku or Akku()
    wb = wallbox or Wallbox()
    erg = Ergebnis()
    p_auto, netz, akku_w, war_frei = 0.0, 0.0, 0.0, False
    for i, s in enumerate(ueberschuss_w):
        t = i * dt
        kaputt = ungueltig is not None and i in ungueltig
        a = strategie.schritt(Eingang(t, p_auto, None if kaputt else netz,
                                      None if kaputt else akku_w, akku.soc, steckt))
        if a.freigabe and not war_frei:
            erg.starts += 1
        war_frei = a.freigabe
        erg.p_erlaubt_max = max(erg.p_erlaubt_max, a.p_erlaubt)

        p_auto = wb.nachfuehren(t, a.freigabe, a.p_erlaubt)
        rest = s - p_auto
        if rest >= 0:
            frei_kwh = (100.0 - akku.soc) / 100 * akku.kapazitaet_kwh
            laden = min(rest, akku.max_laden_w, frei_kwh * 1000 * 3600 / dt)
            akku_w, netz = -laden, -(rest - laden)
        else:
            vorrat_kwh = max(akku.soc - akku.min_soc, 0) / 100 * akku.kapazitaet_kwh
            entladen = min(-rest, akku.max_entladen_w, vorrat_kwh * 1000 * 3600 / dt)
            akku_w, netz = entladen, -rest - entladen
        akku.soc -= akku_w * dt / 3600 / 1000 / akku.kapazitaet_kwh * 100
        akku.soc = min(max(akku.soc, 0.0), 100.0)

        teile = aufteilen(p_auto, netz, akku_w)
        for q in teile:
            erg.kwh[q] += teile[q] * dt / 3600 / 1000
        erg.kwh_auto += p_auto * dt / 3600 / 1000
        erg.kwh_akku_geladen += max(-akku_w, 0) * dt / 3600 / 1000
        if verlauf:
            erg.verlauf.append({"t": t, "ueberschuss": s, "p_roh": a.p_roh, "p_glatt": a.p_glatt,
                                "p_erlaubt": a.p_erlaubt, "p_auto": p_auto, "netz": netz,
                                "akku": akku_w, "soc": akku.soc, "zustand": a.zustand})
    return erg


class LiveSimulator:
    """Nur Entwicklung (EVPV_SIMULATION=1): speist das Anlagenmodell statt Home Assistant
    in das Prozessabbild ein – mit Sonne, Wolken, Akku und einem Auto, das P_erlaubt der
    Regelung folgt (als gaebe es schon einen Treiber). Vorzeichen wie SolarEdge roh."""

    def __init__(self, konfig, abbild, regelung):
        self.k, self.pa, self.reg = konfig, abbild, regelung
        self.akku = Akku(soc=88.0)
        self.wb = Wallbox(max_a=konfig.max_strom_a)
        self.eto = 1234.0
        self.t0 = None

    def ueberschuss(self, t: float) -> float:
        # 5,5 kW Sonne mit Wolkenluecken (alle ~3 min fuer ~1 min), 600 W Hauslast
        wolke = 0.25 if (t % 200) > 140 else 1.0
        return 5500.0 * wolke - 600.0

    def schritt(self, mono: float) -> None:
        import time as _t
        self.t0 = mono if self.t0 is None else self.t0
        t = mono - self.t0
        a = self.reg.aus
        p_auto = self.wb.nachfuehren(t, bool(a and a.freigabe), a.p_erlaubt if a else 0.0)
        rest = self.ueberschuss(t) - p_auto
        if rest >= 0:
            laden = min(rest, self.akku.max_laden_w) if self.akku.soc < 100 else 0.0
            akku_w, netz = -laden, -(rest - laden)
        else:
            entl = min(-rest, self.akku.max_entladen_w) if self.akku.soc > self.akku.min_soc else 0.0
            akku_w, netz = entl, -rest - entl
        self.akku.soc = min(max(self.akku.soc - akku_w / 3600 / 1000 / self.akku.kapazitaet_kwh * 100,
                                0.0), 100.0)
        self.eto += p_auto / 3600 / 1000
        g, k = self.k.goe_praefix, self.k

        def z(s, e=None):
            return {"s": str(s), "a": {"unit_of_measurement": e} if e else {}}
        w = {k.sensor_netz: z(round(-netz if k.sensor_netz_invertieren else netz, 1), "W"),
             k.sensor_akku_leistung: z(round(-akku_w if k.sensor_akku_leistung_invertieren else akku_w), "W"),
             k.sensor_akku_soc: z(round(self.akku.soc, 1), "%"),
             f"sensor.{g}_rbt": z(int(_t.time() * 1000)),
             f"sensor.{g}_nrg_11": z(round(p_auto), "W"),
             f"sensor.{g}_eto": z(round(self.eto, 3), "kWh"),
             f"binary_sensor.{g}_car_0": z("on"),
             f"number.{g}_ama": z(k.max_strom_a, "A")}
        if k.sensor_pv:
            w[k.sensor_pv] = z(round(self.ueberschuss(t) + 600), "W")
        for eid, zustand in w.items():
            if eid:
                self.pa.aktualisieren(eid, zustand, mono)


def ueberschuss_aus_csv(pfad: str) -> tuple[list[float], float | None]:
    """CSV aus dev/export_ha.py (1-s-Raster, interne Vorzeichen): Spalten netz_w, akku_w,
    auto_w, akku_soc. Gibt (PV - Last je Sekunde, Start-SoC) zurueck."""
    werte, soc0 = [], None
    with open(pfad, encoding="utf-8", newline="") as fh:
        for z in csv.DictReader(fh):
            netz = float(z["netz_w"])
            akku = float(z.get("akku_w") or 0)
            auto = float(z.get("auto_w") or 0)
            werte.append(-netz - akku + auto)
            if soc0 is None and z.get("akku_soc"):
                soc0 = float(z["akku_soc"])
    return werte, soc0
