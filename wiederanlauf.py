# -*- coding: utf-8 -*-
"""
Wiederanlauf-Erkennung (M6) fuer den Treiber "ids".

Bekanntes Risiko bei go-e FW 59.4 (marq24 Discussion #126): Nach einer Wolkenpause laeuft
die Ladung im Eco-Modus nicht wieder an, obwohl genug Ueberschuss gemeldet wird.

Erkennung wie eine Laufzeitueberwachung in der SPS ("Befehl da, Rueckmeldung fehlt"):
  Freigabe der Strategie + Auto steckt + Ladeleistung < LADE_SCHWELLE_W seit warte_s.
Nicht als Stoerung gilt, wenn das Auto selbst nicht will (Fahrzeugstatus "beendet"/"wartet")
oder die go-e einen Fehler meldet – dann hilft kein Umschalten.

Massnahmen (Parameter "wiederanlauf"):
  melden       nur Ereignis
  fup          fup kurz aus/an, hoechstens FUP_VERSUCHE Mal, danach nur melden
  fup_dann_a   wie fup, danach Wechsel auf Treiber A bis zum Abstecken
Zwischen zwei Versuchen wird wieder warte_s gewartet. Laedt das Auto wieder, oder wird es
abgesteckt, ist alles quittiert.
"""
from dataclasses import dataclass

LADE_SCHWELLE_W = 100.0
FUP_VERSUCHE = 2
MASSNAHMEN = {"melden": "nur melden", "fup": "fup kurz umschalten",
              "fup_dann_a": "fup umschalten, dann Treiber A"}

# Fahrzeugstatus (sensor.goe_..._car_value), Texte sprachabhaengig: deutsch und englisch.
# Annahme – geprueft ist nur "Inaktiv/Frei"; die uebrigen Texte bei der Inbetriebnahme notieren.
_AUTO_WILL_NICHT = ("beendet", "complete", "warte", "wait", "fehler", "error")

# Ergebnisse
KEINE, MELDEN, FUP, TREIBER_A = None, "melden", "fup", "treiber_a"


@dataclass
class Befund:
    massnahme: str | None      # KEINE / MELDEN / FUP / TREIBER_A
    text: str = ""


class Wiederanlauf:
    def __init__(self):
        self._seit: float | None = None
        self.versuche = 0
        self.gemeldet = False      # Stoerung im aktuellen Versuch schon gemeldet
        self.zustand = "ok"        # fuer die Oberflaeche

    def zuruecksetzen(self) -> None:
        self._seit, self.versuche, self.gemeldet, self.zustand = None, 0, False, "ok"

    def zyklus(self, t: float, massnahme: str, warte_s: float, aktiv: bool, freigabe: bool,
               steckt: bool | None, auto_w: float | None, auto_status: str | None) -> Befund:
        """aktiv: Treiber ids in einem PV-Modus. Liefert hoechstens einmal je Wartezeit
        eine Massnahme."""
        if steckt is False:
            self.zuruecksetzen()
            return Befund(KEINE)
        if auto_w is not None and auto_w >= LADE_SCHWELLE_W:
            if self.versuche or self.gemeldet:
                text = f"lädt wieder ({auto_w:.0f} W) nach {self.versuche} Umschaltversuch(en)"
                self.zuruecksetzen()
                return Befund(MELDEN, text)
            self.zuruecksetzen()
            return Befund(KEINE)
        status = (auto_status or "").lower()
        if (not aktiv or not freigabe or steckt is not True or auto_w is None
                or any(s in status for s in _AUTO_WILL_NICHT)):
            self._seit, self.zustand = None, "ok"
            return Befund(KEINE)

        self._seit = t if self._seit is None else self._seit
        gewartet = t - self._seit
        if gewartet < warte_s:
            self.zustand = f"Freigabe ohne Ladung seit {gewartet:.0f} s"
            return Befund(KEINE)

        # Stoerung: Freigabe da, Auto steckt, laedt aber nicht
        grund = (f"Freigabe seit {warte_s / 60:.0f} min, Auto steckt, lädt aber nicht "
                 f"({auto_w:.0f} W, Fahrzeug: {auto_status or '?'})")
        self._seit = t           # naechster Versuch erst nach erneuter Wartezeit
        if massnahme in ("fup", "fup_dann_a") and self.versuche < FUP_VERSUCHE:
            self.versuche += 1
            self.zustand = f"Umschaltversuch {self.versuche}/{FUP_VERSUCHE}"
            return Befund(FUP, f"{grund} – fup umschalten (Versuch {self.versuche}/{FUP_VERSUCHE})")
        if massnahme == "fup_dann_a":
            self.zustand = "Wechsel auf Treiber A"
            return Befund(TREIBER_A, f"{grund} – {FUP_VERSUCHE} Umschaltversuche ohne Erfolg, "
                                     f"Wechsel auf Treiber A bis zum Abstecken")
        self.zustand = "Störung gemeldet"
        if self.gemeldet:
            return Befund(KEINE)
        self.gemeldet = True
        return Befund(MELDEN, grund)
