# -*- coding: utf-8 -*-
"""
Zielzeit / Ziel-SoC (M7). Reine Logik wie ein FB.

SoC des Autos (SocSchaetzer):
  Anker = letzter bekannter SoC mit dem Stand des Wallbox-Zaehlers (eto) zu diesem Zeitpunkt.
  Quellen: Eingabe in der Oberflaeche oder ein HA-Sensor (sensor_auto_soc) – wer zuletzt
  einen neuen Wert liefert, setzt den Anker. Dazwischen wird hochgerechnet:
      SoC = SoC_Anker + (eto - eto_Anker) x Ladewirkungsgrad / Akkukapazitaet
  Beim Abstecken verfaellt der Anker (das Auto faehrt, der SoC aendert sich ohne Zaehler).

Plan (planen):
  benoetigt  = (Ziel-SoC - SoC) x Kapazitaet / Ladewirkungsgrad      (kWh aus der Wallbox)
  Dauer      = benoetigt / P_max                 P_max = min(Auto, Wallbox-Grenze)
  Start spaet= Abfahrt - Dauer - Puffer
  vor dem spaetesten Start: Nur PV, danach: Sofort bis zum Ziel. Die Sofort-Phase ist
  selbsthaltend bis Ziel erreicht oder Abstecken – auch wenn die Abfahrtszeit vorbei ist.
  Ziel erreicht: weiter wie Nur PV.
  Kein SoC: wie Nur PV, mit Hinweis (nie blind Netzladen).
"""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

def _kwh(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


UHRZEIT = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


@dataclass
class Anker:
    soc: float                 # %
    eto_kwh: float | None      # Zaehlerstand der Wallbox beim Setzen (None = unbekannt)
    zeit: float                # time.time()
    quelle: str                # "Eingabe" / "Sensor"

    def als_dict(self) -> dict:
        return {"soc": self.soc, "eto_kwh": self.eto_kwh, "zeit": self.zeit, "quelle": self.quelle}


class SocSchaetzer:
    def __init__(self, kapazitaet_kwh: float, wirkungsgrad: float, anker: dict | None = None):
        self.kap = kapazitaet_kwh
        self.wg = wirkungsgrad
        self.anker: Anker | None = Anker(**anker) if anker else None
        self._sensor_letzt: float | None = None
        self.geaendert = False     # Anker neu -> speichern

    def setzen(self, soc: float, eto_kwh: float | None, zeit: float, quelle: str = "Eingabe") -> None:
        self.anker = Anker(round(min(max(soc, 0.0), 100.0), 1), eto_kwh, zeit, quelle)
        self.geaendert = True

    def zyklus(self, zeit: float, eto_kwh: float | None, steckt: bool | None,
               sensor_soc: float | None) -> None:
        if steckt is False and self.anker is not None:
            self.anker, self.geaendert = None, True
        if sensor_soc is not None and sensor_soc != self._sensor_letzt:
            # Nur ein neuer Sensorwert setzt den Anker – sonst wuerde ein alter Wert die
            # Hochrechnung und eine neuere Eingabe ueberschreiben
            self._sensor_letzt = sensor_soc
            if steckt is not False:
                self.setzen(sensor_soc, eto_kwh, zeit, "Sensor")
        if self.anker and self.anker.eto_kwh is None and eto_kwh is not None:
            # Zaehler beim Setzen unbekannt (Wallbox offline): ab jetzt hochrechnen
            self.anker.eto_kwh, self.geaendert = eto_kwh, True

    def soc(self, eto_kwh: float | None) -> float | None:
        a = self.anker
        if a is None:
            return None
        if a.eto_kwh is None or eto_kwh is None:
            return a.soc
        geladen = max(eto_kwh - a.eto_kwh, 0.0)
        return min(a.soc + geladen * self.wg / self.kap * 100.0, 100.0)


def naechste_abfahrt(jetzt: datetime, uhrzeit: str) -> datetime:
    h, m = (int(x) for x in uhrzeit.split(":"))
    ziel = jetzt.replace(hour=h, minute=m, second=0, microsecond=0)
    return ziel if ziel > jetzt else ziel + timedelta(days=1)


@dataclass
class Plan:
    modus: str                       # wirksamer Modus: "nur_pv" oder "sofort"
    grund: str
    soc: float | None = None
    benoetigt_kwh: float | None = None
    abfahrt: datetime | None = None
    spaetester_start: datetime | None = None
    erreicht: bool = False
    sofort: bool = False

    def als_dict(self) -> dict:
        return {"modus": self.modus, "grund": self.grund,
                "soc": None if self.soc is None else round(self.soc, 1),
                "benoetigt_kwh": None if self.benoetigt_kwh is None else round(self.benoetigt_kwh, 2),
                "abfahrt": self.abfahrt.isoformat(timespec="minutes") if self.abfahrt else None,
                "spaetester_start": (self.spaetester_start.isoformat(timespec="minutes")
                                     if self.spaetester_start else None),
                "erreicht": self.erreicht, "sofort": self.sofort}


class Zielzeit:
    def __init__(self):
        self.sofort = False      # selbsthaltend, bis Ziel erreicht oder abgesteckt

    def planen(self, jetzt: datetime, uhrzeit: str, ziel_soc: float, puffer_min: float,
               soc: float | None, kap_kwh: float, wirkungsgrad: float, p_max_w: float,
               steckt: bool | None) -> Plan:
        if steckt is False:
            self.sofort = False
        abfahrt = naechste_abfahrt(jetzt, uhrzeit)
        if soc is None:
            self.sofort = False
            return Plan("nur_pv", "Zielzeit: Batterie-Auto fehlt – bitte eintragen; bis dahin nur PV",
                        abfahrt=abfahrt)
        benoetigt = max(ziel_soc - soc, 0.0) / 100.0 * kap_kwh / wirkungsgrad
        if soc >= ziel_soc:
            self.sofort = False
            return Plan("nur_pv", f"Zielzeit: Ziel {ziel_soc:.0f} % erreicht (Batterie-Auto {soc:.0f} %) – weiter nur PV",
                        soc, 0.0, abfahrt, None, erreicht=True)
        dauer = timedelta(hours=benoetigt / (p_max_w / 1000.0))
        start = abfahrt - dauer - timedelta(minutes=puffer_min)
        if jetzt >= start and steckt is True:
            self.sofort = True
        if self.sofort:
            return Plan("sofort", f"Zielzeit: Netzladen bis {ziel_soc:.0f} % – noch {_kwh(benoetigt)} kWh "
                                  f"(Batterie-Auto {soc:.0f} %, Abfahrt {abfahrt:%H:%M})",
                        soc, benoetigt, abfahrt, start, sofort=True)
        return Plan("nur_pv", f"Zielzeit: nur PV bis {start:%H:%M}, danach Netz – noch {_kwh(benoetigt)} kWh "
                              f"bis {ziel_soc:.0f} % (Batterie-Auto {soc:.0f} %)",
                    soc, benoetigt, abfahrt, start)
