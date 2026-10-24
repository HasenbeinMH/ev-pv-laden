# -*- coding: utf-8 -*-
"""
Meldungen an HA (M8): "Auto fertig geladen" und "Ziel-SoC erreicht" – je einmal pro
Ansteckvorgang, als MQTT-Ereignis (event.ev_pv_laden_ladung). Die Benachrichtigung selbst
(Telegram) macht eine HA-Automation, siehe docs/automationen.yaml.

fertig:        Fahrzeugstatus wechselt auf "Abgeschlossen" (complete), nachdem in diesem
               Ansteckvorgang geladen wurde, UND das Add-on gibt in diesem Moment frei.
               Die go-e meldet "Abgeschlossen" auch, wenn sie gesperrt wird (Stopp, frc=1 –
               gesehen 24.10.2026). Dann ist die Freigabe schon weg, bevor der Status
               wechselt. Gezaehlt wird nur der Wechsel: steht der Status nach einer Pause
               schon auf "Abgeschlossen" und kommt die Freigabe danach, ist das Auto nicht voll.
ziel_erreicht: Zielzeit meldet Ziel-SoC erreicht
"""
LADE_SCHWELLE_W = 100.0
# Fahrzeugstatus (sensor.goe_..._car_value), deutsch und englisch
_FERTIG = ("abgeschlossen", "beendet", "complete")


def status_fertig(auto_status: str | None) -> bool:
    status = (auto_status or "").lower()
    return any(s in status for s in _FERTIG)


class FertigErkennung:
    def __init__(self):
        self.geladen = False
        self.gemeldet: set[str] = set()
        self._fertig_letzt: bool | None = None   # Status im letzten Zyklus "Abgeschlossen"?

    @property
    def voll(self) -> bool:
        """Auto in diesem Ansteckvorgang als voll erkannt."""
        return "fertig" in self.gemeldet

    def zyklus(self, steckt: bool | None, auto_w: float | None, auto_status: str | None,
               freigabe: bool, ziel_erreicht: bool) -> list[str]:
        if steckt is False:
            self.geladen, self.gemeldet, self._fertig_letzt = False, set(), None
            return []
        if steckt is not True:
            return []
        if auto_w is not None and auto_w >= LADE_SCHWELLE_W:
            self.geladen = True
        neu = []
        fertig = status_fertig(auto_status)
        if self.geladen and fertig and self._fertig_letzt is False and freigabe:
            neu.append("fertig")
        self._fertig_letzt = fertig
        if ziel_erreicht and self.geladen:
            neu.append("ziel_erreicht")
        neu = [n for n in neu if n not in self.gemeldet]
        self.gemeldet.update(neu)
        return neu
