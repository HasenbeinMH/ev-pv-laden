# -*- coding: utf-8 -*-
"""
Tagesverlauf fuer das Dashboard ("Heute"): Minutenmittel von PV, Haus, Auto, Netz und Akku.

Laufend im Speicher (max. 26 h). Nach einem Neustart fuellt die Laufzeit die Minuten seit
Mitternacht aus der HA-Historie nach (aus_historie / vorfuellen) – mit denselben
Umrechnungen wie das Prozessabbild (Einheit, Vorzeichen).
"""
from collections import deque

from prozessabbild import Signal, umrechnen

ABTAST_S = 10      # Historie: Stufenfunktion alle 10 s abtasten, je Minute mitteln
# Prozessabbild-Signal -> Groesse im Tagesverlauf
SIGNALE = {"pv_w": "pv", "netz_w": "netz", "akku_w": "akku", "auto_w": "auto", "haus_w": "haus_w"}

GROESSEN = ("pv", "haus", "auto", "netz", "akku")
MAX_MINUTEN = 26 * 60


class Tagesverlauf:
    def __init__(self):
        self.punkte: deque = deque(maxlen=MAX_MINUTEN)   # (minute_epoch_s, {groesse: W|None})
        self._minute: int | None = None
        self._summe: dict[str, float] = {}
        self._anzahl: dict[str, int] = {}

    def hinzufuegen(self, t_epoch: float, werte: dict) -> None:
        minute = int(t_epoch // 60) * 60
        if self._minute is not None and minute != self._minute:
            self._abschliessen()
        self._minute = minute
        for g in GROESSEN:
            v = werte.get(g)
            if v is not None:
                self._summe[g] = self._summe.get(g, 0.0) + v
                self._anzahl[g] = self._anzahl.get(g, 0) + 1

    def _abschliessen(self) -> None:
        mittel = {g: (round(self._summe[g] / self._anzahl[g]) if self._anzahl.get(g) else None)
                  for g in GROESSEN}
        self.punkte.append((self._minute, mittel))
        self._summe, self._anzahl = {}, {}

    def vorfuellen(self, punkte: list[tuple[int, dict]]) -> int:
        """Minuten aus der Historie VOR den bereits live erfassten einfuegen. Gibt die Anzahl
        eingefuegter Minuten zurueck."""
        grenze = self.punkte[0][0] if self.punkte else self._minute
        alt = [(t, m) for t, m in punkte if grenze is None or t < grenze]
        if not alt:
            return 0
        neu = deque(alt, maxlen=MAX_MINUTEN)
        neu.extend(self.punkte)
        self.punkte = neu
        return len(alt)

    def liste(self, seit_epoch: float) -> dict:
        daten = [[t] + [m[g] for g in GROESSEN] for t, m in self.punkte if t >= seit_epoch]
        return {"spalten": ("zeit",) + GROESSEN, "daten": daten}


def aus_historie(historie: dict, signale: dict[str, tuple[Signal, str | None]],
                 von: float, bis: float, haus_enthaelt_auto: bool) -> list[tuple[int, dict]]:
    """Antwort von history/history_during_period (minimal_response, no_attributes) ->
    Minutenmittel wie im Live-Betrieb.
    signale: Signalname (pv_w, netz_w, ...) -> (Signal, Einheit aus dem aktuellen Zustand)."""
    reihen: dict[str, list[tuple[float, float | None]]] = {}
    for name, (sig, einheit) in signale.items():
        punkte = []
        for z in historie.get(sig.entity_id) or []:
            t = z.get("lu", z.get("lc"))
            if t is None:
                continue
            wert = umrechnen(sig, {"s": z.get("s"), "a": {"unit_of_measurement": einheit}})
            punkte.append((float(t), wert if isinstance(wert, (int, float)) else None))
        punkte.sort(key=lambda p: p[0])
        reihen[name] = punkte

    def wert_zu(reihe, t, start):
        # Stufenfunktion: letzter Wert vor t (Zeiger 'start' laeuft mit, Reihe ist sortiert)
        i = start
        while i + 1 < len(reihe) and reihe[i + 1][0] <= t:
            i += 1
        if not reihe or reihe[i][0] > t:
            return None, i
        return reihe[i][1], i

    zeiger = {n: 0 for n in reihen}
    ergebnis = []
    minute = int(von // 60) * 60
    while minute + 60 <= bis:
        summen: dict[str, list[float]] = {}
        for k in range(0, 60, ABTAST_S):
            t = minute + k
            werte = {}
            for name, reihe in reihen.items():
                werte[name], zeiger[name] = wert_zu(reihe, t, zeiger[name])
            groessen = {"pv": werte.get("pv_w"), "netz": werte.get("netz_w"), "akku": werte.get("akku_w"),
                        "auto": werte.get("auto_w"),
                        "haus": hausverbrauch(werte, haus_enthaelt_auto)}
            for g, v in groessen.items():
                if v is not None:
                    summen.setdefault(g, []).append(v)
        if summen:
            ergebnis.append((minute, {g: (round(sum(summen[g]) / len(summen[g])) if g in summen else None)
                                      for g in GROESSEN}))
        minute += 60
    return ergebnis


def hausverbrauch(werte: dict, haus_enthaelt_auto: bool) -> float | None:
    """Wie im Energiefluss: eigener Sensor (ohne Wallbox), sonst Bilanz der Knoten."""
    haus, auto = werte.get("haus_w"), werte.get("auto_w")
    if haus is not None:
        if haus_enthaelt_auto and auto is not None:
            haus -= auto
        return max(haus, 0.0)
    teile = [werte.get(n) for n in ("pv_w", "netz_w", "akku_w")]
    if any(v is None for v in teile) or auto is None:
        return None
    return max(sum(teile) - auto, 0.0)
