# -*- coding: utf-8 -*-
"""
Regelung (M4: nur Trockenlauf). Liest das Prozessabbild, rechnet die Strategie und
haelt das Ergebnis fuer Oberflaeche und MQTT bereit. Ein Stellglied (Treiber) gibt es
noch nicht – es wird nichts auf die Wallbox geschrieben.

Regelentscheidungen (Wechsel von Freigabe oder Zustand) landen im Ereignisprotokoll.
Der Verlauf der letzten Stunde liegt im Speicher (Diagramm in der Oberflaeche).
"""
import logging
import time
from collections import deque

import datenbank as db
from konfig import Konfig
from prozessabbild import Prozessabbild
from strategie import MODI, SPANNUNG_V, Ausgang, Eingang, Parameter, Strategie, pgrid_virtuell

log = logging.getLogger("regelung")

VERLAUF_S = 3600
PARAM_SCHLUESSEL = "strategie"


class Regelung:
    def __init__(self, konfig: Konfig, abbild: Prozessabbild):
        self.konfig = konfig
        self.abbild = abbild
        param = Parameter.aus_dict(db.einstellung(PARAM_SCHLUESSEL))
        if param.pruefen():
            log.warning("Gespeicherte Parameter ungueltig (%s) – Standardwerte", param.pruefen())
            param = Parameter()
        # Kleinste Leistung: Mindeststrom einphasig; groesste: Maximalstrom dreiphasig
        self.p_min = konfig.min_strom_a * SPANNUNG_V
        self.p_max = konfig.max_strom_a * SPANNUNG_V * 3
        self.strategie = Strategie(param, self.p_min, self.p_max)
        self.aus: Ausgang | None = None
        self.p_auto: float | None = None
        self.pgrid_v: float | None = None
        self.treiber = "keiner (Trockenlauf)"
        self.verlauf: deque = deque(maxlen=VERLAUF_S)
        self._letzt: tuple | None = None

    @property
    def param(self) -> Parameter:
        return self.strategie.param

    def parameter_setzen(self, neu: dict) -> list[str]:
        """Aenderung aus Oberflaeche/HA. Gibt Fehler zurueck; bei Fehlern bleibt alles alt."""
        try:
            p = Parameter.aus_dict({**self.param.als_dict(), **neu})
        except (TypeError, ValueError) as e:
            return [f"ungültiger Wert: {e}"]
        fehler = p.pruefen()
        if fehler:
            return fehler
        alt = self.param.als_dict()
        self.strategie.param = p
        db.einstellung_setzen(PARAM_SCHLUESSEL, p.als_dict())
        geaendert = {k: v for k, v in p.als_dict().items() if alt.get(k) != v}
        if geaendert:
            db.ereignis("info", "parameter", "geändert: " +
                        ", ".join(f"{k}={v}" for k, v in geaendert.items()))
        return []

    def zyklus(self, mono: float | None = None) -> Ausgang:
        mono = time.monotonic() if mono is None else mono
        pa = self.abbild
        akku_da = "akku_w" in pa.werte
        e = Eingang(mono, pa.wert("auto_w", mono), pa.wert("netz_w", mono),
                    pa.wert("akku_w", mono) if akku_da else 0.0,
                    pa.wert("akku_soc", mono) if "akku_soc" in pa.werte else None,
                    pa.wert("auto_steckt", mono), akku_vorhanden=akku_da)
        a = self.strategie.schritt(e)
        self.aus, self.p_auto = a, e.p_auto
        self.pgrid_v = pgrid_virtuell(e.p_auto, a)
        self.verlauf.append((round(time.time()), _r(a.p_roh), _r(a.p_glatt), _r(a.p_erlaubt),
                             _r(e.p_auto), _r(e.netz_w), _r(e.akku_w), _r(self.pgrid_v),
                             a.zustand))
        self._protokollieren(a)
        return a

    def _protokollieren(self, a: Ausgang) -> None:
        schluessel = (a.freigabe, a.zustand)
        if schluessel == self._letzt:
            return
        self._letzt = schluessel
        text = f"{'Freigabe' if a.freigabe else 'keine Freigabe'} ({a.zustand}): {a.grund}"
        if a.freigabe:
            text += f" – P_erlaubt {a.p_erlaubt:.0f} W"
        log.info(text)
        db.ereignis("info", "strategie", text)

    def status(self) -> dict:
        a = self.aus
        return {
            "modus": self.param.modus, "modi": MODI, "parameter": self.param.als_dict(),
            "p_min": self.p_min, "p_max": self.p_max, "treiber": self.treiber,
            "trockenlauf": self.konfig.trockenlauf,
            "ausgang": None if a is None else {
                "freigabe": a.freigabe, "p_erlaubt": a.p_erlaubt, "p_roh": a.p_roh,
                "p_glatt": a.p_glatt, "zustand": a.zustand, "grund": a.grund,
                "pgrid_virtuell": self.pgrid_v, "p_auto": self.p_auto},
        }

    def verlauf_liste(self, sekunden: int = VERLAUF_S, schritt: int = 1) -> dict:
        daten = list(self.verlauf)[-sekunden:][::max(schritt, 1)]
        spalten = ("zeit", "p_roh", "p_glatt", "p_erlaubt", "p_auto", "netz", "akku",
                   "pgrid_virtuell", "zustand")
        return {"spalten": spalten, "daten": daten}

    def mqtt_zustand(self) -> dict:
        a = self.aus
        return {
            "p_erlaubt": None if a is None else round(a.p_erlaubt),
            "pgrid_virtuell": None if self.pgrid_v is None else round(self.pgrid_v),
            "grund": None if a is None else a.grund[:250],
            "regelzustand": None if a is None else a.zustand,
            "modus": self.param.modus,
            "treiber": self.treiber,
        }


def _r(x):
    return None if x is None else round(x)
