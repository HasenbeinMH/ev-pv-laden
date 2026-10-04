# -*- coding: utf-8 -*-
"""
Meldungen an HA (M8): "Auto fertig geladen" und "Ziel-SoC erreicht" – je einmal pro
Ansteckvorgang, als MQTT-Ereignis (event.ev_pv_laden_ladung). Die Benachrichtigung selbst
(Telegram) macht eine HA-Automation, siehe docs/automationen.yaml.

fertig:        Fahrzeugstatus meldet "beendet/complete", nachdem in diesem Ansteckvorgang
               geladen wurde (Texte sprachabhaengig – Annahme, bei Inbetriebnahme pruefen)
ziel_erreicht: Zielzeit meldet Ziel-SoC erreicht
"""
LADE_SCHWELLE_W = 100.0
_FERTIG = ("beendet", "complete")


class FertigErkennung:
    def __init__(self):
        self.geladen = False
        self.gemeldet: set[str] = set()

    def zyklus(self, steckt: bool | None, auto_w: float | None, auto_status: str | None,
               ziel_erreicht: bool) -> list[str]:
        if steckt is False:
            self.geladen, self.gemeldet = False, set()
            return []
        if steckt is not True:
            return []
        if auto_w is not None and auto_w >= LADE_SCHWELLE_W:
            self.geladen = True
        neu = []
        status = (auto_status or "").lower()
        if self.geladen and any(s in status for s in _FERTIG):
            neu.append("fertig")
        if ziel_erreicht and self.geladen:
            neu.append("ziel_erreicht")
        neu = [n for n in neu if n not in self.gemeldet]
        self.gemeldet.update(neu)
        return neu
