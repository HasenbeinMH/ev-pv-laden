# -*- coding: utf-8 -*-
"""
Stellglied: setzt die Entscheidung der Strategie auf der go-e um.

Reine Logik: liefert eine Liste von Aktionen (HA-Dienstaufrufe). Die Laufzeit fuehrt
sie aus – oder protokolliert sie im Trockenlauf nur ("wuerde schreiben").
Geschrieben wird ausschliesslich ueber die Integration goecharger_api2 (marq24), damit
nur ein Client mit der Wallbox spricht.

Treiber "ids" (Hybrid, M5):
  Die go-e regelt selbst im Eco-Modus (lmo=4, fup=an, frc=0) und waehlt die Phasen
  (psm=0); Rundung "PreferPowerToGrid" (frm=2), damit sie nie eine Stufe zu viel nimmt. Das Add-on sendet alle IDS_TAKT_S (2 s) einen virtuellen Netzwert:
      pGrid = P_auto - P_erlaubt   (negativ = Ueberschuss -> go-e erhoeht)
  pAkku = 0 (Akku-Logik steckt in der Strategie), pPv real oder 0 (konfigurierbar).
  Kommt nichts mehr, verwirft die go-e die Werte nach ~5 s und sieht keinen Ueberschuss –
  das ist der Watchdog im ids-Betrieb.

Modus Sofort: lmo=3, frc=0, psm=2 (fest dreiphasig), amp=Maximum, kein ids.
Modus Aus:    frc=1 (Laden gesperrt).

Sollkonfiguration: Die Einstellungen der go-e werden laufend mit dem Prozessabbild
verglichen und bei Abweichung neu gesetzt (hoechstens alle NACHSTELLEN_S je Wert) – wie
eine Sollwertueberwachung, die auch Eingriffe aus App oder HA wieder einfaengt.

Schieflast/Zuleitung (harte Grenzen, unabhaengig von der Strategie):
  amp wird einphasig auf strom_1ph_max_a begrenzt, dreiphasig auf max_strom_a.
  Phasenzahl unbekannt -> konservativ einphasige Grenze.
  Gemessener Strom ueber der Grenze laenger als UEBERSTROM_S -> frc=1, Verriegelung bis
  zum naechsten Moduswechsel.
"""
from dataclasses import dataclass

from konfig import Konfig
from strategie import AUS, SOFORT, Ausgang

# Die go-e verwirft ids nach ~5 s. Bei 1-s-Zyklus und Jitter wird aus 3 s schnell 4 s –
# deshalb 2 s: hoechstens 3 s zwischen zwei Sendungen.
IDS_TAKT_S = 2.0
NACHSTELLEN_S = 30.0
UEBERSTROM_S = 5.0
UEBERSTROM_TOLERANZ_A = 1.0
PHASE_AKTIV_A = 1.0     # ab diesem Strom gilt eine Phase als belegt


@dataclass(frozen=True)
class Aktion:
    domain: str
    service: str
    daten: dict
    ziel: dict | None = None
    text: str = ""
    ids: bool = False      # zyklische ids-Sendung (nicht einzeln ins Ereignisprotokoll)


class TreiberIds:
    name = "ids"

    def __init__(self, konfig: Konfig, ppv_senden: bool = True):
        self.k = konfig
        self.g = konfig.goe_praefix
        self.ppv_senden = ppv_senden
        self._letzte_ids: float | None = None
        self._nachgestellt: dict[str, float] = {}
        self._ueberstrom_seit: float | None = None
        self.verriegelt: str | None = None
        self._modus_letzt: str | None = None

    # -- Hilfen -----------------------------------------------------------------------------
    def phasen(self, werte: dict) -> int | None:
        """Belegte Phasen aus den gemessenen Stroemen; None = unbekannt."""
        stroeme = [werte.get(f"auto_i{n}") for n in (1, 2, 3)]
        if any(s is None for s in stroeme):
            return None
        belegt = sum(s >= PHASE_AKTIV_A for s in stroeme)
        return belegt or None

    def amp_grenze(self, phasen: int | None) -> int:
        return self.k.max_strom_a if phasen == 3 else self.k.strom_1ph_max_a

    def _soll(self, t: float, schluessel: str, ist, soll, aktion: Aktion) -> list[Aktion]:
        """Aktion nur, wenn Ist != Soll und nicht gerade erst nachgestellt."""
        if ist is not None and _gleich(ist, soll):
            self._nachgestellt.pop(schluessel, None)
            return []
        zuletzt = self._nachgestellt.get(schluessel)
        if zuletzt is not None and t - zuletzt < NACHSTELLEN_S:
            return []
        self._nachgestellt[schluessel] = t
        return [aktion]

    def _select(self, t, w, name, wert, text):
        eid = f"select.{self.g}_{name}"
        return self._soll(t, name, w.get(f"goe_{name}"), wert,
                          Aktion("select", "select_option", {"option": wert}, {"entity_id": eid},
                                 f"{name}={wert} ({text})"))

    def _schalter(self, t, w, name, an, text):
        eid = f"switch.{self.g}_{name}"
        return self._soll(t, name, w.get(f"goe_{name}"), an,
                          Aktion("switch", "turn_on" if an else "turn_off", {}, {"entity_id": eid},
                                 f"{name}={'an' if an else 'aus'} ({text})"))

    def _amp(self, t, w, wert, text):
        eid = f"number.{self.g}_amp"
        return self._soll(t, "amp", w.get("goe_amp"), float(wert),
                          Aktion("number", "set_value", {"value": int(wert)}, {"entity_id": eid},
                                 f"amp={int(wert)} A ({text})"))

    # -- Zyklus -----------------------------------------------------------------------------
    def zyklus(self, t: float, modus: str, a: Ausgang, pgrid_v: float | None,
               werte: dict) -> list[Aktion]:
        """werte: gueltige Werte aus dem Prozessabbild (Name -> Wert, None = ungueltig)."""
        if modus != self._modus_letzt:
            # Moduswechsel hebt eine Verriegelung auf (bewusste Bedienhandlung)
            self.verriegelt, self._modus_letzt = None, modus
            self._nachgestellt.clear()

        if werte.get("goe_lebenszeichen") is None:
            # Wallbox nicht erreichbar: nichts senden (ohne ids sieht sie keinen Ueberschuss)
            return []
        aktionen = self._ueberstrom(t, werte)
        if self.verriegelt:
            return aktionen + self._select(t, werte, "frc", "1", f"verriegelt: {self.verriegelt}")

        if modus == AUS:
            return aktionen + self._select(t, werte, "frc", "1", "Modus Aus")

        phasen = self.phasen(werte)
        if modus == SOFORT:
            return aktionen + (
                self._select(t, werte, "lmo", "3", "Sofort: Standardmodus")
                + self._select(t, werte, "frc", "0", "Sofort: neutral")
                + self._select(t, werte, "psm", "2", "Sofort: fest dreiphasig")
                + self._amp(t, werte, self.k.max_strom_a, "Sofort: Maximum"))

        # Nur PV / Min + PV / Zielzeit: go-e im Eco-Modus, Phasen automatisch
        aktionen += (self._select(t, werte, "lmo", "4", "Eco-Modus")
                     + self._schalter(t, werte, "fup", True, "PV-Überschuss")
                     + self._select(t, werte, "frc", "0", "neutral")
                     + self._select(t, werte, "psm", "0", "Phasen automatisch")
                     # Abrunden statt aufrunden: nie eine Stromstufe ueber P_erlaubt
                     + self._select(t, werte, "frm", "2", "Rundung zum Netz")
                     + self._amp(t, werte, self.amp_grenze(phasen),
                                 f"Grenze {'dreiphasig' if phasen == 3 else 'einphasig'}"))
        if pgrid_v is not None and (self._letzte_ids is None or t - self._letzte_ids >= IDS_TAKT_S):
            self._letzte_ids = t
            ppv = werte.get("pv_w") if self.ppv_senden else None
            daten = {"pgrid": round(pgrid_v), "pakku": 0,
                     "ppv": max(round(ppv), 0) if ppv is not None else 0}
            aktionen.append(Aktion("goecharger_api2", "set_pv_data", daten, None,
                                   f"ids pGrid={daten['pgrid']} W", ids=True))
        return aktionen

    def _ueberstrom(self, t: float, werte: dict) -> list[Aktion]:
        """Harte Grenze: gemessener Strom ueber Schieflast- bzw. Zuleitungsgrenze."""
        phasen = self.phasen(werte)
        stroeme = [werte.get(f"auto_i{n}") or 0.0 for n in (1, 2, 3)]
        grenze = self.amp_grenze(phasen)
        if max(stroeme) > grenze + UEBERSTROM_TOLERANZ_A:
            self._ueberstrom_seit = self._ueberstrom_seit if self._ueberstrom_seit is not None else t
            if t - self._ueberstrom_seit >= UEBERSTROM_S and not self.verriegelt:
                self.verriegelt = (f"Strom {max(stroeme):.1f} A über Grenze {grenze} A "
                                   f"({phasen or '?'}-phasig) seit {UEBERSTROM_S:.0f} s")
                self._nachgestellt.pop("frc", None)
        else:
            self._ueberstrom_seit = None
        return []


def _gleich(ist, soll) -> bool:
    if isinstance(soll, bool):
        return ist is soll
    if isinstance(soll, float):
        try:
            return abs(float(ist) - soll) < 0.5
        except (TypeError, ValueError):
            return False
    return str(ist) == str(soll)
