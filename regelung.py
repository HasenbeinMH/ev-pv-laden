# -*- coding: utf-8 -*-
"""
Regelung: liest das Prozessabbild, rechnet die Strategie und haelt das Ergebnis fuer
Oberflaeche und MQTT bereit. Umgesetzt wird es vom Treiber (Laufzeit); die kleinste
Ladeleistung haengt vom Treiber ab (ids: einphasig, A: fest dreiphasig).

Regelentscheidungen (Wechsel von Freigabe oder Zustand) landen im Ereignisprotokoll.
Der Verlauf der letzten Stunde liegt im Speicher (Diagramm in der Oberflaeche).
"""
import logging
import time
from collections import deque
from datetime import datetime, timezone, tzinfo

import datenbank as db
from konfig import Konfig
from prozessabbild import Prozessabbild
from strategie import (MODI, SPANNUNG_V, TREIBER, WIEDERANLAUF, ZIELZEIT, Ausgang, Eingang, Parameter,
                       Strategie, pgrid_virtuell)
from zielzeit import Plan, SocSchaetzer, Zielzeit

log = logging.getLogger("regelung")

VERLAUF_S = 3600
PARAM_SCHLUESSEL = "strategie"
SOC_SCHLUESSEL = "auto_soc"


class Regelung:
    def __init__(self, konfig: Konfig, abbild: Prozessabbild):
        self.konfig = konfig
        self.abbild = abbild
        param = Parameter.aus_dict(db.einstellung(PARAM_SCHLUESSEL))
        if param.pruefen():
            log.warning("Gespeicherte Parameter ungueltig (%s) – Standardwerte", param.pruefen())
            param = Parameter()
        # Kleinste Leistung: Mindeststrom einphasig (Treiber A: dreiphasig, siehe
        # phasen_min_setzen); groesste: Maximalstrom dreiphasig
        self.p_min = konfig.min_strom_a * SPANNUNG_V
        self.p_max = konfig.max_strom_a * SPANNUNG_V * 3
        self.strategie = Strategie(param, self.p_min, self.p_max)
        self.aus: Ausgang | None = None
        self.p_auto: float | None = None
        self.pgrid_v: float | None = None
        self.treiber = "keiner (Trockenlauf)"
        self.trockenlauf = konfig.trockenlauf     # wird von der Laufzeit nachgefuehrt
        self.verlauf: deque = deque(maxlen=VERLAUF_S)
        self._letzt: tuple | None = None
        # Zielzeit: SoC des Autos (Eingabe/Sensor + Hochrechnung) und Plan
        self.soc = SocSchaetzer(konfig.akku_kapazitaet_kwh, konfig.ladewirkungsgrad,
                                db.einstellung(SOC_SCHLUESSEL))
        self.zielzeit = Zielzeit()
        self.plan: Plan | None = None
        self.modus_wirksam: str = param.modus
        self.tz: tzinfo = timezone.utc
        self.p_plan = min(konfig.ev_max_leistung_kw * 1000.0, self.p_max)

    def phasen_min_setzen(self, phasen: int) -> None:
        """Kleinste Ladeleistung nach Treiber: ids 1 Phase, A fest 3 Phasen."""
        self.p_min = self.konfig.min_strom_a * SPANNUNG_V * phasen
        self.strategie.p_min = self.p_min

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

    def auto_soc_setzen(self, soc: float) -> list[str]:
        """Eingabe in der Oberflaeche: SoC jetzt; ab hier rechnet der Wallbox-Zaehler hoch."""
        if not 0 <= soc <= 100:
            return ["SoC muss zwischen 0 und 100 % liegen"]
        self.soc.setzen(soc, self.abbild.wert("goe_eto"), time.time())
        self._soc_sichern()
        db.ereignis("info", "zielzeit", f"SoC des Autos eingetragen: {soc:.0f} %")
        return []

    def _soc_sichern(self) -> None:
        if self.soc.geaendert:
            db.einstellung_setzen(SOC_SCHLUESSEL, self.soc.anker.als_dict() if self.soc.anker else None)
            self.soc.geaendert = False

    def _soc_zyklus(self, mono: float, jetzt: float) -> float | None:
        pa = self.abbild
        eto = pa.wert("goe_eto", mono)
        sensor = pa.werte["auto_soc"].wert if "auto_soc" in pa.werte else None
        self.soc.zyklus(jetzt, eto, pa.wert("auto_steckt", mono), sensor)
        self._soc_sichern()
        return self.soc.soc(eto)

    def zyklus(self, mono: float | None = None, jetzt: float | None = None) -> Ausgang:
        mono = time.monotonic() if mono is None else mono
        jetzt = time.time() if jetzt is None else jetzt
        pa = self.abbild
        akku_da = "akku_w" in pa.werte
        e = Eingang(mono, pa.wert("auto_w", mono), pa.wert("netz_w", mono),
                    pa.wert("akku_w", mono) if akku_da else 0.0,
                    pa.wert("akku_soc", mono) if "akku_soc" in pa.werte else None,
                    pa.wert("auto_steckt", mono), akku_vorhanden=akku_da)
        soc = self._soc_zyklus(mono, jetzt)
        p = self.param
        if p.modus == ZIELZEIT:
            self.plan = self.zielzeit.planen(
                datetime.fromtimestamp(jetzt, self.tz), p.abfahrt, p.ziel_soc, p.puffer_min, soc,
                self.konfig.akku_kapazitaet_kwh, self.konfig.ladewirkungsgrad, self.p_plan, e.steckt)
            self.modus_wirksam = self.plan.modus
            a = self.strategie.schritt(e, self.modus_wirksam)
            if e.steckt is True:
                a.grund = self.plan.grund if self.plan.sofort else f"{a.grund} · {self.plan.grund}"
        else:
            self.plan, self.modus_wirksam = None, p.modus
            a = self.strategie.schritt(e)
        self.aus, self.p_auto = a, e.p_auto
        self.pgrid_v = pgrid_virtuell(e.p_auto, a)
        self.verlauf.append((round(time.time()), _r(a.p_roh), _r(a.p_glatt), _r(a.p_erlaubt),
                             _r(e.p_auto), _r(e.netz_w), _r(e.akku_w), _r(self.pgrid_v),
                             a.zustand))
        self._protokollieren(a)
        return a

    def _protokollieren(self, a: Ausgang) -> None:
        schluessel = (a.freigabe, a.zustand, self.modus_wirksam)
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
            "treiber_wahl": TREIBER, "wiederanlauf_wahl": WIEDERANLAUF,
            "start_wirksam": self.strategie.start_wirksam(), "stopp_wirksam": self.strategie.stopp_wirksam(),
            "p_min": self.p_min, "p_max": self.p_max, "treiber": self.treiber,
            "trockenlauf": self.trockenlauf,
            "modus_wirksam": self.modus_wirksam,
            "zielzeit": self.zielzeit_status(),
            "ausgang": None if a is None else {
                "freigabe": a.freigabe, "p_erlaubt": a.p_erlaubt, "p_roh": a.p_roh,
                "p_glatt": a.p_glatt, "zustand": a.zustand, "grund": a.grund,
                "pgrid_virtuell": self.pgrid_v, "p_auto": self.p_auto},
        }

    def zielzeit_status(self) -> dict:
        eto = self.abbild.wert("goe_eto")
        a = self.soc.anker
        return {
            "soc": None if self.soc.soc(eto) is None else round(self.soc.soc(eto), 1),
            "soc_quelle": None if a is None else a.quelle,
            "soc_gesetzt": None if a is None else datetime.fromtimestamp(a.zeit, self.tz).isoformat(timespec="minutes"),
            "soc_gesetzt_wert": None if a is None else a.soc,
            "sensor": self.konfig.sensor_auto_soc or None,
            "p_plan_w": self.p_plan,
            "plan": self.plan.als_dict() if self.plan else None,
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
            "auto_soc": None if self.soc.soc(self.abbild.wert("goe_eto")) is None
            else round(self.soc.soc(self.abbild.wert("goe_eto"))),
            "zielzeit_start": (self.plan.spaetester_start.isoformat()
                               if self.plan and self.plan.spaetester_start else None),
        }


def _r(x):
    return None if x is None else round(x)
