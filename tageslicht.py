# -*- coding: utf-8 -*-
"""
Erkennung „keine PV“ fuer den Modus Min + PV (0.11). Reine Logik wie ein FB.

Schwellwertschalter mit Hysterese und Verzoegerung (gemessene PV-Leistung, nicht der
Sonnenstand – passt zu Verschattung und Winter):
  keine PV  : PV < unter_w   laenger als unter_s   (Standard 50 W, 15 min)
  PV wieder : PV > ueber_w   laenger als ueber_s   (Standard 300 W, 5 min)
Beim ersten gueltigen Wert wird der Zustand sofort gesetzt (Neustart in der Nacht = Nacht).
Ungueltiger Wert: Zustand bleibt, Zeitglieder laufen nicht weiter.
"""


class Tageslicht:
    def __init__(self):
        self.nacht: bool | None = None       # None = noch kein Messwert
        self._seit: float | None = None      # Wechselbedingung erfuellt seit

    def zyklus(self, t: float, pv_w: float | None, unter_w: float, unter_s: float,
               ueber_w: float, ueber_s: float) -> bool | None:
        if pv_w is None:
            self._seit = None
            return self.nacht
        if self.nacht is None:
            self.nacht = pv_w < unter_w
            return self.nacht
        wechsel = pv_w > ueber_w if self.nacht else pv_w < unter_w
        if not wechsel:
            self._seit = None
            return self.nacht
        self._seit = t if self._seit is None else self._seit
        if t - self._seit >= (ueber_s if self.nacht else unter_s):
            self.nacht, self._seit = not self.nacht, None
        return self.nacht

    def rest_s(self, t: float, unter_s: float, ueber_s: float) -> float | None:
        """Restzeit bis zum Wechsel (fuer die Anzeige), None wenn keiner ansteht."""
        if self._seit is None or self.nacht is None:
            return None
        return max((ueber_s if self.nacht else unter_s) - (t - self._seit), 0.0)
