# -*- coding: utf-8 -*-
"""
Strategie: wie viel Leistung darf das Auto bekommen? (P_erlaubt)

Reine Logik wie ein FB: Eingaenge -> Ausgaenge, Zustand in der Instanz. Kennt keine
Wallbox – das Stellglied (Treiber "ids" oder "A") setzt P_erlaubt spaeter um.

Interne Konvention: Netz Bezug +, Akku Entladung +.

1. Verfuegbare Leistung (roh):
       P = P_auto - Netz                       Einspeisung erhoeht, Bezug senkt
           - max(Akku - Unterstuetzung, 0)     Entladung ist immer Defizit
           + Akku-Ladung, wenn SoC >= Schwelle  (Ueberschuss vom Akku zum Auto umleiten)
   Unterstuetzung = "Akku darf Auto mit max. X W unterstuetzen oberhalb SoC Y" (Standard 0).
2. Glaettung PT1 (Zeitkonstante tau).
3. Start/Stopp mit Hysterese, Verzoegerungen, Mindestladedauer und Mindestpause.
4. Modi: Aus, Nur PV, Min + PV, Sofort; Zielzeit plant zielzeit.py und ruft die Strategie
   mit dem wirksamen Modus (Nur PV bzw. Sofort) auf.
5. Sicherheit: Messwert ungueltig/veraltet -> kein Ueberschuss, Stopp ohne Verzoegerung
   (Min + PV: Mindestleistung). Grenzen: P_erlaubt nie ueber P_max.
"""
from dataclasses import asdict, dataclass, fields

from zielzeit import UHRZEIT

# Modi
AUS, NUR_PV, MIN_PV, SOFORT, ZIELZEIT = "aus", "nur_pv", "min_pv", "sofort", "zielzeit"
MODI = {AUS: "Aus", NUR_PV: "Nur PV", MIN_PV: "Min + PV", SOFORT: "Sofort", ZIELZEIT: "Zielzeit"}

TREIBER = {"ids": "ids (go-e regelt)", "a": "A (Add-on stellt Strom, dreiphasig)"}
# Schalter "Nachtladen" (Nur PV und Min + PV, wenn keine PV da ist): voll = an, pause = aus
OHNE_PV = {"voll": "voll aus dem Netz", "pause": "Pause bis PV da ist"}
WIEDERANLAUF = {"melden": "nur melden", "fup": "fup kurz umschalten",
                "fup_dann_a": "fup umschalten, dann Treiber A"}

SPANNUNG_V = 230.0


@dataclass
class Parameter:
    """Zur Laufzeit einstellbar (Oberflaeche, spaeter HA-Entitaeten)."""
    modus: str = NUR_PV
    akku_soc_schwelle: float = 90.0     # %: darunter laedt der Hausakku zuerst
    akku_unterstuetzung_w: float = 0.0  # W: so viel darf der Akku das Auto stuetzen ...
    akku_unterstuetzung_soc: float = 100.0  # ... oberhalb dieses SoC
    tau_s: float = 30.0                 # Glaettung
    start_w: float = 1400.0             # Start, wenn Ueberschuss >= start_w ...
    start_verz_s: float = 60.0          # ... so lange anliegt
    stopp_w: float = 1100.0             # Stopp, wenn Ueberschuss < stopp_w ...
    stopp_verz_s: float = 180.0         # ... so lange anliegt
    min_ladedauer_s: float = 600.0
    min_pause_s: float = 300.0
    treiber: str = "ids"                # Stellglied: "ids" (go-e regelt) oder "a" (Add-on stellt amp)
    wiederanlauf: str = "fup_dann_a"    # Massnahme, wenn die Ladung nach einer Pause nicht anlaeuft
    wiederanlauf_s: float = 300.0       # ... nach so langer Freigabe ohne Ladung
    ziel_soc: float = 80.0              # Zielzeit: Ziel-SoC des Autos (%) ...
    abfahrt: str = "07:00"              # ... zur naechsten Abfahrt um diese Uhrzeit
    puffer_min: float = 30.0            # ... mit so viel Reserve vor der Abfahrt
    ohne_pv: str = "pause"              # Nachtladen: ohne PV voll aus dem Netz ("voll") oder Pause
    ohne_pv_unter_w: float = 50.0       # "keine PV": PV unter ... W ...
    ohne_pv_unter_s: float = 900.0      # ... so lange
    ohne_pv_ueber_w: float = 300.0      # "PV wieder da": PV ueber ... W ...
    ohne_pv_ueber_s: float = 300.0      # ... so lange

    def pruefen(self) -> list[str]:
        f = []
        if self.modus not in MODI:
            f.append(f"Modus '{self.modus}' unbekannt")
        if not 0 <= self.akku_soc_schwelle <= 100:
            f.append("Akku-SoC-Schwelle muss zwischen 0 und 100 % liegen")
        if not 0 <= self.akku_unterstuetzung_soc <= 100:
            f.append("SoC für Akku-Unterstützung muss zwischen 0 und 100 % liegen")
        if not 0 <= self.akku_unterstuetzung_w <= 20000:
            f.append("Akku-Unterstützung muss zwischen 0 und 20000 W liegen")
        if not 0 <= self.tau_s <= 600:
            f.append("Zeitkonstante muss zwischen 0 und 600 s liegen")
        if not 0 < self.stopp_w <= self.start_w:
            f.append("Stopp-Schwelle muss größer 0 und höchstens die Start-Schwelle sein")
        if self.treiber not in TREIBER:
            f.append(f"Treiber '{self.treiber}' unbekannt")
        if self.wiederanlauf not in WIEDERANLAUF:
            f.append(f"Wiederanlauf-Maßnahme '{self.wiederanlauf}' unbekannt")
        if not 60 <= self.wiederanlauf_s <= 3600:
            f.append("Wiederanlauf-Wartezeit muss zwischen 60 und 3600 s liegen")
        if self.ohne_pv not in OHNE_PV:
            f.append(f"Verhalten ohne PV '{self.ohne_pv}' unbekannt")
        if not 0 <= self.ohne_pv_unter_w < self.ohne_pv_ueber_w <= 5000:
            f.append("Schwellen ohne PV: 0 ≤ 'keine PV' < 'PV wieder da' ≤ 5000 W")
        for name in ("ohne_pv_unter_s", "ohne_pv_ueber_s"):
            if not 0 <= getattr(self, name) <= 7200:
                f.append(f"{name} muss zwischen 0 und 7200 s liegen")
        if not 10 <= self.ziel_soc <= 100:
            f.append("Ladestand muss zwischen 10 und 100 % liegen")
        if not UHRZEIT.match(str(self.abfahrt)):
            f.append(f"Abfahrt '{self.abfahrt}' ungültig (HH:MM)")
        if not 0 <= self.puffer_min <= 600:
            f.append("Puffer muss zwischen 0 und 600 min liegen")
        for name in ("start_verz_s", "stopp_verz_s", "min_ladedauer_s", "min_pause_s"):
            if not 0 <= getattr(self, name) <= 7200:
                f.append(f"{name} muss zwischen 0 und 7200 s liegen")
        return f

    def als_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def aus_dict(cls, d: dict | None) -> "Parameter":
        p = cls()
        for feld in fields(cls):
            if d and feld.name in d:
                wert = d[feld.name]
                setattr(p, feld.name, str(wert) if feld.type in ("str", str) else float(wert))
        if p.ohne_pv == "mindest":          # 0.11.0 kannte noch "Mindestleistung weiter"
            p.ohne_pv = "pause"
        return p


@dataclass
class Eingang:
    t: float                     # time.monotonic()
    p_auto: float | None         # W, None = Wallbox-Wert ungueltig
    netz_w: float | None         # Bezug +
    akku_w: float | None         # Entladung +; 0.0 wenn kein Akku konfiguriert
    akku_soc: float | None       # %; None wenn ungueltig (bei Akku noetig)
    steckt: bool | None
    akku_vorhanden: bool = True


@dataclass
class Ausgang:
    freigabe: bool               # soll geladen werden?
    p_erlaubt: float             # W, 0 wenn keine Freigabe
    p_roh: float | None          # verfuegbare Leistung vor der Glaettung
    p_glatt: float | None
    zustand: str                 # bereit / startet / laedt / stoppt / pause
    grund: str                   # Klartext fuer "warum (nicht)"


# Ohne Freigabe meldet der Treiber "ids" so viel Netzbezug zusaetzlich zur Ladeleistung,
# dass die go-e sicher keinen Ueberschuss sieht
DEFIZIT_OHNE_FREIGABE_W = 1000.0


def pgrid_virtuell(p_auto: float | None, a: Ausgang) -> float | None:
    """Virtueller Netzwert fuer den Treiber "ids" (wie HSEM): P_auto - P_erlaubt.
    Negativ = Ueberschuss verfuegbar, die go-e erhoeht; positiv = sie reduziert/stoppt."""
    if p_auto is None:
        return None
    if not a.freigabe:
        return max(p_auto, 0.0) + DEFIZIT_OHNE_FREIGABE_W
    return p_auto - a.p_erlaubt


class Strategie:
    def __init__(self, param: Parameter, p_min_w: float, p_max_w: float):
        """p_min_w: kleinste Ladeleistung (Mindeststrom einphasig), p_max_w: hoechste
        (max_strom_a dreiphasig) – beide aus der Konfiguration, nicht einstellbar."""
        self.param = param
        self.p_min = p_min_w
        self.p_max = p_max_w
        self.laedt = False
        self._glatt: float | None = None
        self._t_letzt: float | None = None
        self._seit_bedingung: float | None = None   # Start- bzw. Stoppbedingung erfuellt seit
        self._laden_seit: float | None = None
        self._pause_seit: float | None = None

    # -- Bausteine ----------------------------------------------------------------------
    def verfuegbar(self, e: Eingang) -> float | None:
        p = self.param
        if e.p_auto is None or e.netz_w is None:
            return None
        if e.akku_vorhanden and (e.akku_w is None or e.akku_soc is None):
            return None
        akku = e.akku_w if e.akku_vorhanden else 0.0
        soc = e.akku_soc if e.akku_vorhanden else 0.0
        unterstuetzung = p.akku_unterstuetzung_w if soc >= p.akku_unterstuetzung_soc else 0.0
        wert = e.p_auto - e.netz_w - max(akku - unterstuetzung, 0.0)
        if soc >= p.akku_soc_schwelle:
            wert += max(-akku, 0.0)
        return wert

    def _pt1(self, t: float, x: float) -> float:
        if self._glatt is None or self._t_letzt is None:
            self._glatt = x
        else:
            dt = max(t - self._t_letzt, 0.0)
            tau = self.param.tau_s
            self._glatt += (x - self._glatt) * (dt / (tau + dt) if tau > 0 else 1.0)
        self._t_letzt = t
        return self._glatt

    def _stoppen(self, t: float) -> None:
        if self.laedt:
            self._pause_seit = t
        self.laedt, self._laden_seit, self._seit_bedingung = False, None, None

    def _starten(self, t: float) -> None:
        self.laedt, self._laden_seit, self._seit_bedingung = True, t, None

    def _aus(self, t, grund, roh=None, glatt=None, zustand="bereit") -> Ausgang:
        self._stoppen(t)
        return Ausgang(False, 0.0, roh, glatt, zustand, grund)

    def start_wirksam(self) -> float:
        """Start nie unter der kleinsten Ladeleistung (Treiber A dreiphasig: 4,1 kW)."""
        return max(self.param.start_w, self.p_min)

    def stopp_wirksam(self) -> float:
        """Stopp-Schwelle mit derselben Hysterese unter dem wirksamen Start."""
        p = self.param
        return max(p.stopp_w, self.start_wirksam() - (p.start_w - p.stopp_w))

    def _begrenzen(self, p: float) -> float:
        return min(max(p, self.p_min), self.p_max)

    # -- Zyklus -------------------------------------------------------------------------
    def schritt(self, e: Eingang, modus: str | None = None) -> Ausgang:
        """modus: wirksamer Modus, falls abweichend vom Parameter (Zielzeit -> Nur PV/Sofort)."""
        p, t = self.param, e.t
        modus = modus or p.modus
        if modus == AUS:
            self._glatt = None
            return self._aus(t, "Modus Aus")
        if e.steckt is not True:
            self._glatt = None
            return self._aus(t, "kein Fahrzeug angesteckt" if e.steckt is False
                             else "Fahrzeugstatus unbekannt")
        if modus == SOFORT:
            if not self.laedt:
                self._starten(t)
            return Ausgang(True, self.p_max, None, None, "laedt", "Modus Sofort")

        roh = self.verfuegbar(e)
        if roh is None:
            # Watchdog: kein gueltiger Messwert = kein Ueberschuss, ohne Verzoegerung
            self._glatt, self._t_letzt = None, None
            if modus == MIN_PV:
                if not self.laedt:
                    self._starten(t)
                return Ausgang(True, self.p_min, None, None, "laedt",
                               "Messwerte ungültig – nur Mindestleistung")
            return self._aus(t, "Messwerte ungültig oder veraltet – kein Überschuss")

        glatt = self._pt1(t, roh)

        if modus == MIN_PV:
            if not self.laedt:
                self._starten(t)
            erlaubt = self._begrenzen(glatt)
            grund = "Min + PV: Mindestleistung" if glatt <= self.p_min else "Min + PV: Überschuss"
            return Ausgang(True, erlaubt, roh, glatt, "laedt", grund)

        # NUR_PV
        start_w, stopp_w = self.start_wirksam(), self.stopp_wirksam()
        if self.laedt:
            if glatt < stopp_w:
                self._seit_bedingung = self._seit_bedingung if self._seit_bedingung is not None else t
                gelaufen = t - self._laden_seit
                gewartet = t - self._seit_bedingung
                if gewartet >= p.stopp_verz_s and gelaufen >= p.min_ladedauer_s:
                    self._stoppen(t)
                    return Ausgang(False, 0.0, roh, glatt, "pause",
                                   f"gestoppt: Überschuss {glatt:.0f} W < {stopp_w:.0f} W")
                rest = max(p.stopp_verz_s - gewartet, p.min_ladedauer_s - gelaufen)
                return Ausgang(True, self._begrenzen(glatt), roh, glatt, "stoppt",
                               f"Überschuss {glatt:.0f} W < {stopp_w:.0f} W – Stopp in {rest:.0f} s")
            self._seit_bedingung = None
            return Ausgang(True, self._begrenzen(glatt), roh, glatt, "laedt",
                           f"PV-Überschuss {glatt:.0f} W")

        # laedt nicht
        if self._pause_seit is not None and t - self._pause_seit < p.min_pause_s:
            self._seit_bedingung = None
            rest = p.min_pause_s - (t - self._pause_seit)
            return Ausgang(False, 0.0, roh, glatt, "pause", f"Mindestpause – noch {rest:.0f} s")
        if glatt >= start_w:
            self._seit_bedingung = self._seit_bedingung if self._seit_bedingung is not None else t
            gewartet = t - self._seit_bedingung
            if gewartet >= p.start_verz_s:
                self._starten(t)
                return Ausgang(True, self._begrenzen(glatt), roh, glatt, "laedt",
                               f"gestartet: Überschuss {glatt:.0f} W")
            return Ausgang(False, 0.0, roh, glatt, "startet",
                           f"Überschuss {glatt:.0f} W – Start in {p.start_verz_s - gewartet:.0f} s")
        self._seit_bedingung = None
        return Ausgang(False, 0.0, roh, glatt, "bereit",
                       f"Überschuss {glatt:.0f} W < Start {start_w:.0f} W")
