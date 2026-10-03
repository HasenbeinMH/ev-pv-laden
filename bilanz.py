# -*- coding: utf-8 -*-
"""
Bilanz: wie viel kWh gingen aus PV, Hausakku und Netz ins Auto?

Reine Logik ohne Ein-/Ausgabe (wie ein FB mit Instanz-DB): der Zustand liegt in
BilanzZustand und wird von aussen gespeichert/geladen.

1. Aufteilung je Messzyklus, Regel "Haus zuerst, das Auto bekommt den Ueberschuss":
       netz = min(P_auto, Netzbezug+)
       akku = min(P_auto - netz, Akku-Entladung+)
       pv   = Rest
   Wie ev_pv_anteil_mit_zaehler.yaml im EV Tracker, nur mit dem Akku als eigenem Topf
   (die Vorlage zaehlt ihn als PV – beim Senden an den Tracker wird er wieder addiert).

2. Integration ueber die Zeit (Trapez) in einen "Topf" je Quelle.

3. Der Energiezaehler der Wallbox (eto) fuehrt: Jeder Anstieg wird im Verhaeltnis des
   Topfs aufgeteilt, dann wird der Topf geleert. PV + Akku + Netz ergeben so immer
   exakt den Zaehler der Wallbox. Das Trapez-Integral wird zusaetzlich aufsummiert und
   dient nur als Plausibilitaetspruefung.

Sonderfaelle (alle konservativ: im Zweifel Netz):
  - Messwerte Netz/Akku ungueltig, Auto laedt: Anteil dieses Intervalls zaehlt als Netz
    und zusaetzlich als "unsicher".
  - eto steigt, Topf leer (z.B. Werte kamen nicht): letztes Verhaeltnis, wenn juenger
    als ANTEIL_GUELTIG_S, sonst Netz + "ohne Aufteilung".
  - erster eto-Anstieg nach Neustart (Auto hat geladen, waehrend das Add-on aus war):
    Netz + "ohne Aufteilung".
  - eto faellt (Tausch/Reset der Wallbox): neu ansetzen, nichts buchen.
  - eto springt unplausibel weit: neu ansetzen, nichts buchen, Warnung.
"""
from dataclasses import asdict, dataclass, field

QUELLEN = ("pv", "akku", "netz")

# Nicht ueber Messluecken hinweg integrieren (Verbindung weg, Add-on haengt)
MAX_LUECKE_S = 30.0
# Letztes Aufteilungsverhaeltnis darf so lange weiterverwendet werden
ANTEIL_GUELTIG_S = 300.0
# Plausibilitaet eto: hoechstens 25 kW (+ Rundung 50 Wh) seit dem letzten Wert
MAX_LEISTUNG_KW = 25.0


def aufteilen(p_auto: float, netz_w: float, akku_w: float) -> dict[str, float]:
    """Momentane Aufteilung der Ladeleistung in W. Interne Vorzeichen: Netz Bezug +,
    Akku Entladung +."""
    p = max(p_auto, 0.0)
    netz = min(p, max(netz_w, 0.0))
    akku = min(p - netz, max(akku_w, 0.0))
    return {"pv": p - netz - akku, "akku": akku, "netz": netz}


@dataclass
class BilanzZustand:
    # Fortlaufende Zaehler in kWh – steigen nur
    kwh: dict = field(default_factory=lambda: {q: 0.0 for q in QUELLEN})
    kwh_ohne_aufteilung: float = 0.0   # in netz enthalten, nur zur Transparenz
    kwh_unsicher: float = 0.0          # in netz enthalten, Messwerte waren ungueltig
    kwh_trapez: float = 0.0            # Summe Trapez-Integral (Plausibilitaet)
    kwh_eto: float = 0.0               # Summe der gebuchten eto-Anstiege
    eto_letzt: float | None = None
    # Topf seit der letzten Buchung (Wh)
    topf: dict = field(default_factory=lambda: {q: 0.0 for q in QUELLEN})
    anteil_letzt: dict | None = None
    anteil_zeit: float | None = None

    def als_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def aus_dict(cls, d: dict) -> "BilanzZustand":
        z = cls()
        for k, v in (d or {}).items():
            if hasattr(z, k):
                setattr(z, k, v)
        return z


@dataclass
class Buchung:
    """Ergebnis eines eto-Anstiegs: was wurde wohin gebucht (kWh)."""
    kwh: dict
    art: str            # "anteilig", "letzter_anteil", "ohne_aufteilung", "neu_angesetzt", ...
    hinweis: str = ""


class Bilanz:
    def __init__(self, zustand: BilanzZustand | None = None, nach_neustart: bool = True):
        self.z = zustand or BilanzZustand()
        # Nach dem Laden aus der Datenbank ist unbekannt, was zwischen Stopp und Start
        # geladen wurde -> erster Anstieg wird ohne Aufteilung gebucht
        self._erster_eto = nach_neustart
        self._probe: tuple[float, dict[str, float], bool] | None = None
        self._eto_zeit: float | None = None

    # -- Leistung integrieren -------------------------------------------------------
    def schritt(self, t: float, p_auto: float | None, netz_w: float | None,
                akku_w: float | None) -> None:
        """Ein Messzyklus. t = time.monotonic(). p_auto None = Wallbox-Wert ungueltig ->
        kein Integral (eto bucht spaeter trotzdem, dann ueber das letzte Verhaeltnis)."""
        if p_auto is None:
            self._probe = None
            return
        unsicher = netz_w is None or (akku_w is None)
        if unsicher:
            # Netz/Akku unbekannt: konservativ alles Netz
            teile = {"pv": 0.0, "akku": 0.0, "netz": max(p_auto, 0.0)}
        else:
            teile = aufteilen(p_auto, netz_w, akku_w)
        if self._probe is not None:
            t0, teile0, unsicher0 = self._probe
            dt = t - t0
            if 0 < dt <= MAX_LUECKE_S:
                for q in QUELLEN:
                    wh = (teile0[q] + teile[q]) / 2 * dt / 3600
                    self.z.topf[q] += wh
                summe_kwh = sum((teile0[q] + teile[q]) / 2 for q in QUELLEN) * dt / 3600 / 1000
                self.z.kwh_trapez += summe_kwh
                if unsicher or unsicher0:
                    self.z.kwh_unsicher += summe_kwh
        self._probe = (t, teile, unsicher)

    # -- Wallbox-Zaehler buchen -----------------------------------------------------
    def eto(self, t: float, eto_kwh: float) -> Buchung | None:
        """Neuer Zaehlerstand der Wallbox (kWh). Gibt die Buchung zurueck oder None."""
        z = self.z
        if z.eto_letzt is None:
            z.eto_letzt, self._eto_zeit, self._erster_eto = eto_kwh, t, False
            self._topf_leeren()
            return Buchung({q: 0.0 for q in QUELLEN}, "neu_angesetzt", "erster Zaehlerstand")
        delta = eto_kwh - z.eto_letzt
        if delta == 0:
            # _eto_zeit bleibt die Zeit der letzten AENDERUNG – sonst waere das
            # Plausibilitaetsfenster bei seltenen Zaehler-Updates zu kurz
            return None
        if delta < 0:
            hinweis = f"Zaehler der Wallbox zurueckgegangen ({z.eto_letzt:.3f} -> {eto_kwh:.3f} kWh)"
            z.eto_letzt, self._eto_zeit, self._erster_eto = eto_kwh, t, False
            self._topf_leeren()
            return Buchung({q: 0.0 for q in QUELLEN}, "neu_angesetzt", hinweis)

        if self._erster_eto:
            # Waehrend das Add-on aus war, wurde geladen – Herkunft unbekannt
            self._erster_eto = False
            return self._buchen(t, eto_kwh, {"pv": 0.0, "akku": 0.0, "netz": 1.0},
                                "ohne_aufteilung", f"{delta:.3f} kWh seit dem letzten Lauf")

        if self._eto_zeit is not None:
            erlaubt = MAX_LEISTUNG_KW * max(t - self._eto_zeit, 0) / 3600 + 0.05
            if delta > erlaubt:
                hinweis = (f"Zaehlersprung {delta:.3f} kWh in {t - self._eto_zeit:.0f} s "
                           f"unplausibel – neu angesetzt")
                z.eto_letzt, self._eto_zeit = eto_kwh, t
                self._topf_leeren()
                return Buchung({q: 0.0 for q in QUELLEN}, "neu_angesetzt", hinweis)

        summe = sum(z.topf.values())
        if summe > 0:
            anteil = {q: z.topf[q] / summe for q in QUELLEN}
            z.anteil_letzt, z.anteil_zeit = anteil, t
            return self._buchen(t, eto_kwh, anteil, "anteilig")
        if z.anteil_letzt and z.anteil_zeit is not None and t - z.anteil_zeit <= ANTEIL_GUELTIG_S:
            return self._buchen(t, eto_kwh, z.anteil_letzt, "letzter_anteil")
        return self._buchen(t, eto_kwh, {"pv": 0.0, "akku": 0.0, "netz": 1.0}, "ohne_aufteilung",
                            "keine Leistungswerte zur Aufteilung")

    def _buchen(self, t: float, eto_kwh: float, anteil: dict, art: str, hinweis: str = "") -> Buchung:
        z = self.z
        delta = eto_kwh - z.eto_letzt
        teile = {q: delta * anteil[q] for q in QUELLEN}
        # Rundungsrest dem groessten Anteil zuschlagen, damit die Summe exakt delta ist
        rest = delta - sum(teile.values())
        teile[max(QUELLEN, key=lambda q: anteil[q])] += rest
        for q in QUELLEN:
            z.kwh[q] += max(teile[q], 0.0)
        if art == "ohne_aufteilung":
            z.kwh_ohne_aufteilung += delta
        z.kwh_eto += delta
        z.eto_letzt, self._eto_zeit = eto_kwh, t
        self._topf_leeren()
        return Buchung(teile, art, hinweis)

    def _topf_leeren(self) -> None:
        self.z.topf = {q: 0.0 for q in QUELLEN}
