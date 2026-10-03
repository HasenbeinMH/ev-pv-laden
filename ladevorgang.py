# -*- coding: utf-8 -*-
"""
Erkennung einzelner Ladevorgaenge – gleiche Regeln wie die EV-Tracker-Vorlage
ev_ladung_senden.yaml, damit beide Wege dieselben Ladungen sehen:
  Beginn: mehr als START_W fuer START_S Sekunden (Zeitpunkt = erste Ueberschreitung)
  Ende:   ENDE_S Sekunden ohne Leistung oder Fahrzeug abgesteckt
          (kurze Pausen beim PV-Ueberschussladen bleiben so eine Ladung)
  Monatswechsel: laufende Ladung wird geteilt, damit jeder Teil im richtigen Monat zaehlt

Die Energie je Quelle ergibt sich aus der Differenz der Bilanz-Zaehler zwischen Beginn
und Ende. Reine Logik; Speichern uebernimmt der Aufrufer.
"""
from dataclasses import dataclass, field
from datetime import datetime

START_W = 50.0
START_S = 60.0
ENDE_S = 900.0


@dataclass
class Stand:
    """Zaehlerstaende der Bilanz zu einem Zeitpunkt (kWh)."""
    pv: float = 0.0
    akku: float = 0.0
    netz: float = 0.0
    ohne: float = 0.0
    eto: float = 0.0
    trapez: float = 0.0

    def minus(self, o: "Stand") -> "Stand":
        return Stand(*(max(getattr(self, f) - getattr(o, f), 0.0)
                       for f in ("pv", "akku", "netz", "ohne", "eto", "trapez")))


@dataclass
class Vorgang:
    start: datetime
    stand_start: Stand
    modus: str = ""
    letzte_leistung: datetime | None = None
    id: int | None = None          # Datenbank-ID, solange offen


@dataclass
class Ereignis:
    art: str                  # "start" | "ende"
    vorgang: Vorgang
    ende: datetime | None = None
    energie: Stand | None = None
    grund: str = ""


@dataclass
class Erkennung:
    offen: Vorgang | None = None
    _kandidat: tuple[datetime, Stand] | None = field(default=None, repr=False)

    def schritt(self, jetzt: datetime, p_auto: float | None, steckt: bool | None,
                stand: Stand, modus: str = "") -> list[Ereignis]:
        """Ein Zyklus. jetzt = lokale Zeit (fuer den Monatswechsel). p_auto None =
        unbekannt: zaehlt weder als Laden noch als Pause."""
        ereignisse: list[Ereignis] = []
        laedt = p_auto is not None and p_auto > START_W

        if self.offen:
            v = self.offen
            if laedt:
                v.letzte_leistung = jetzt
            if (jetzt.year, jetzt.month) != (v.start.year, v.start.month):
                # Monatswechsel: Ende zum Monatsersten 0 Uhr, neuer Teil ab dann
                grenze = jetzt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                ereignisse.append(self._beenden(grenze, stand, "Monatswechsel"))
                self.offen = Vorgang(grenze, stand, modus, v.letzte_leistung)
                ereignisse.append(Ereignis("start", self.offen))
            elif steckt is False:
                ereignisse.append(self._beenden(v.letzte_leistung or jetzt, stand, "abgesteckt"))
            elif v.letzte_leistung and (jetzt - v.letzte_leistung).total_seconds() >= ENDE_S:
                ereignisse.append(self._beenden(v.letzte_leistung, stand, "keine Leistung"))
            return ereignisse

        if laedt:
            if self._kandidat is None:
                self._kandidat = (jetzt, stand)
            elif (jetzt - self._kandidat[0]).total_seconds() >= START_S:
                beginn, stand_beginn = self._kandidat
                self._kandidat = None
                self.offen = Vorgang(beginn, stand_beginn, modus, jetzt)
                ereignisse.append(Ereignis("start", self.offen))
        elif p_auto is not None:
            self._kandidat = None
        return ereignisse

    def _beenden(self, ende: datetime, stand: Stand, grund: str) -> Ereignis:
        v = self.offen
        self.offen = None
        return Ereignis("ende", v, ende, stand.minus(v.stand_start), grund)
