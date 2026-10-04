# -*- coding: utf-8 -*-
"""
Tagesverlauf fuer das Dashboard ("Heute"): Minutenmittel von PV, Haus, Auto, Netz und Akku.

Nur im Speicher (max. 26 h) – nach einem Neustart beginnt die Kurve neu. Gespeicherte
Energiewerte (Bilanz) sind davon nicht betroffen.
"""
from collections import deque

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

    def liste(self, seit_epoch: float) -> dict:
        daten = [[t] + [m[g] for g in GROESSEN] for t, m in self.punkte if t >= seit_epoch]
        return {"spalten": ("zeit",) + GROESSEN, "daten": daten}


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
