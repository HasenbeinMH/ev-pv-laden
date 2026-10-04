# -*- coding: utf-8 -*-
"""
Prozessabbild: letzter Wert jedes Signals mit Zeitstempel, in interner Einheit und
interner Vorzeichenkonvention. Die Regelung liest nur hieraus, nie direkt aus HA –
wie das Prozessabbild der Eingaenge einer SPS.

Interne Konvention (fest):
  Leistung in W, Energie in kWh, SoC in %
  Netz:  Bezug +, Einspeisung -
  Akku:  Entladung +, Ladung -

Gueltigkeit: Ein Wert ist gueltig, wenn er eine Zahl ist und juenger als max_alter_s.
"Juenger" heisst: seit dem letzten Empfang des Signals selbst ODER seines
Lebenszeichens. Das Lebenszeichen ist ein Sensor desselben Geraets, der sich
staendig aendert – denn HA meldet einen gleichbleibenden Wert nicht erneut
(Akku 0 W, SoC 100 %, Wallbox 0 W im Leerlauf). Zwei Geraete, zwei Lebensbits:
  lebenszeichen      Messgeraet (SolarEdge: Netzleistung, aendert sich alle ~2 s)
  goe_lebenszeichen  Wallbox (Zeit seit Boot – Annahme, wird in M3 gemessen)
"""
import time
from dataclasses import dataclass, field

from konfig import Konfig

# Art eines Signals: bestimmt Einheitenumrechnung und Anzeige
LEISTUNG, ENERGIE, PROZENT, STROM, BINAER, ZAHL, TEXT = (
    "leistung", "energie", "prozent", "strom", "binaer", "zahl", "text")

_FAKTOR = {
    LEISTUNG: {"W": 1.0, "kW": 1000.0, "MW": 1e6},
    ENERGIE: {"Wh": 0.001, "kWh": 1.0, "MWh": 1000.0},
}
UNGUELTIG = ("unknown", "unavailable", "none", "null", "")


@dataclass(frozen=True)
class Signal:
    name: str            # interner Name, z.B. "netz_w"
    entity_id: str
    art: str
    beschreibung: str
    invertieren: bool = False
    # Name des Lebenszeichen-Signals, dessen Empfang das Alter ebenfalls zuruecksetzt
    lebenszeichen: str | None = None
    pflicht: bool = True          # fehlt es, ist keine Regelung moeglich


def signale(k: Konfig) -> list[Signal]:
    g = k.goe_praefix
    mess = "lebenszeichen" if k.sensor_lebenszeichen else None
    liste = [
        Signal("netz_w", k.sensor_netz, LEISTUNG, "Netz (Bezug +)", k.sensor_netz_invertieren,
               lebenszeichen=mess),
    ]
    if k.sensor_akku_leistung:
        liste.append(Signal("akku_w", k.sensor_akku_leistung, LEISTUNG, "Hausakku (Entladung +)",
                            k.sensor_akku_leistung_invertieren, lebenszeichen=mess))
    if k.sensor_akku_soc:
        liste.append(Signal("akku_soc", k.sensor_akku_soc, PROZENT, "Hausakku SoC",
                            lebenszeichen=mess))
    if k.sensor_pv:
        liste.append(Signal("pv_w", k.sensor_pv, LEISTUNG, "PV-Erzeugung", pflicht=False,
                            lebenszeichen=mess))
    if k.sensor_haus:
        liste.append(Signal("haus_w", k.sensor_haus, LEISTUNG, "Hausverbrauch", pflicht=False,
                            lebenszeichen=mess))
    if k.sensor_lebenszeichen:
        liste.append(Signal("lebenszeichen", k.sensor_lebenszeichen, TEXT,
                            "Lebenszeichen Messgeraet", pflicht=False))

    def goe(name, entity, art, text, pflicht=True):
        return Signal(name, entity, art, text, pflicht=pflicht, lebenszeichen="goe_lebenszeichen")

    liste += [
        Signal("goe_lebenszeichen", f"sensor.{g}_rbt", TEXT, "Lebenszeichen Wallbox (Zeit seit Boot)",
               pflicht=False),
        goe("auto_w", f"sensor.{g}_nrg_11", LEISTUNG, "Ladeleistung Auto"),
        goe("auto_i1", f"sensor.{g}_nrg_4", STROM, "Strom L1", pflicht=False),
        goe("auto_i2", f"sensor.{g}_nrg_5", STROM, "Strom L2", pflicht=False),
        goe("auto_i3", f"sensor.{g}_nrg_6", STROM, "Strom L3", pflicht=False),
        goe("goe_eto", f"sensor.{g}_eto", ENERGIE, "Energiezaehler Wallbox"),
        goe("goe_wh", f"sensor.{g}_wh", ENERGIE, "Energie seit Anstecken", pflicht=False),
        goe("auto_steckt", f"binary_sensor.{g}_car_0", BINAER, "Fahrzeug verbunden"),
        goe("goe_status", f"sensor.{g}_modelstatus", TEXT, "go-e Grund (modelStatus)", pflicht=False),
        goe("goe_ama", f"number.{g}_ama", STROM, "go-e Max. Stromlimit (ama)"),
        goe("goe_amp", f"number.{g}_amp", STROM, "go-e Angeforderter Strom (amp)"),
        goe("goe_lmo", f"select.{g}_lmo", TEXT, "go-e Logik/Modus (lmo)", pflicht=False),
        goe("goe_frc", f"select.{g}_frc", TEXT, "go-e Force State (frc)", pflicht=False),
        goe("goe_psm", f"select.{g}_psm", TEXT, "go-e Phasenmodus (psm)", pflicht=False),
        goe("goe_fup", f"switch.{g}_fup", BINAER, "go-e PV-Ueberschuss (fup)", pflicht=False),
        goe("goe_frm", f"select.{g}_frm", TEXT, "go-e Rundungsmodus (frm)", pflicht=False),
        goe("goe_pgrid", f"sensor.{g}_pgrid", LEISTUNG, "go-e empfangenes pGrid", pflicht=False),
        goe("goe_inva", f"sensor.{g}_inva_delta", ZAHL, "go-e Alter Inverterdaten", pflicht=False),
    ]
    return liste


def umrechnen(sig: Signal, zustand: dict | None) -> float | str | bool | None:
    """HA-Zustand -> interner Wert. None = ungueltig (fehlt, unavailable, keine Zahl,
    unbekannte Einheit). Lieber kein Wert als ein falsch skalierter."""
    if not zustand:
        return None
    roh = zustand.get("s")
    if roh is None or str(roh).strip().lower() in UNGUELTIG:
        return None
    if sig.art == TEXT:
        return str(roh)
    if sig.art == BINAER:
        return {"on": True, "off": False}.get(str(roh).lower())
    try:
        wert = float(roh)
    except (TypeError, ValueError):
        return None
    if sig.art in _FAKTOR:
        einheit = (zustand.get("a") or {}).get("unit_of_measurement")
        faktor = _FAKTOR[sig.art].get(einheit)
        if faktor is None:
            return None
        wert *= faktor
    return -wert if sig.invertieren else wert


@dataclass
class Messwert:
    signal: Signal
    wert: float | str | bool | None = None
    roh: str | None = None
    einheit: str | None = None
    empfangen: float | None = None        # time.monotonic() des letzten Empfangs
    empfangen_wand: float | None = None   # time.time() fuer die Anzeige
    # Abstand zwischen zwei Empfaengen (Diagnose: wie oft kommt der Wert wirklich?)
    intervall_letzt: float | None = None
    intervall_max: float | None = None


@dataclass
class Prozessabbild:
    konfig: Konfig
    werte: dict[str, Messwert] = field(default_factory=dict)

    def __post_init__(self):
        self._nach_entity: dict[str, list[Messwert]] = {}
        for sig in signale(self.konfig):
            mw = Messwert(sig)
            self.werte[sig.name] = mw
            self._nach_entity.setdefault(sig.entity_id, []).append(mw)

    @property
    def entity_ids(self) -> list[str]:
        return list(self._nach_entity)

    def aktualisieren(self, entity_id: str, zustand: dict | None, mono: float) -> None:
        """Rueckruf des HA-Clients. zustand None = Entitaet weg oder Verbindung getrennt."""
        for mw in self._nach_entity.get(entity_id, []):
            if zustand is not None and mw.empfangen is not None and mw.wert is not None:
                dt = mono - mw.empfangen
                mw.intervall_letzt = dt
                mw.intervall_max = dt if mw.intervall_max is None else max(mw.intervall_max, dt)
            mw.wert = umrechnen(mw.signal, zustand)
            mw.roh = None if zustand is None else zustand.get("s")
            mw.einheit = None if zustand is None else (zustand.get("a") or {}).get("unit_of_measurement")
            mw.empfangen = mono
            mw.empfangen_wand = time.time() - (time.monotonic() - mono)

    def alter_s(self, name: str, jetzt: float | None = None) -> float | None:
        mw = self.werte[name]
        jetzt = time.monotonic() if jetzt is None else jetzt
        zeiten = [mw.empfangen] if mw.empfangen is not None else []
        lz = self.werte.get(mw.signal.lebenszeichen) if mw.signal.lebenszeichen else None
        # Lebenszeichen zaehlt nur, wenn es selbst einen gueltigen Wert hat
        if lz is not None and lz.empfangen is not None and lz.wert is not None:
            zeiten.append(lz.empfangen)
        return (jetzt - max(zeiten)) if zeiten else None

    def gueltig(self, name: str, jetzt: float | None = None) -> bool:
        mw = self.werte.get(name)
        if mw is None or mw.wert is None:
            return False
        alter = self.alter_s(name, jetzt)
        return alter is not None and alter <= self.konfig.max_alter_s

    def wert(self, name: str, jetzt: float | None = None):
        """Gueltiger Wert oder None – die Regelung bekommt nie einen veralteten Wert."""
        return self.werte[name].wert if self.gueltig(name, jetzt) else None

    def uebersicht(self, jetzt: float | None = None) -> list[dict]:
        jetzt = time.monotonic() if jetzt is None else jetzt
        zeilen = []
        for name, mw in self.werte.items():
            alter = self.alter_s(name, jetzt)
            zeilen.append({
                "name": name, "entity_id": mw.signal.entity_id,
                "beschreibung": mw.signal.beschreibung, "art": mw.signal.art,
                "invertiert": mw.signal.invertieren, "pflicht": mw.signal.pflicht,
                "lebenszeichen": mw.signal.lebenszeichen,
                "wert": mw.wert, "roh": mw.roh, "einheit": mw.einheit,
                "alter_s": None if alter is None else round(alter, 1),
                "gueltig": self.gueltig(name, jetzt),
                "empfangen": mw.empfangen is not None,
                "intervall_s": None if mw.intervall_letzt is None else round(mw.intervall_letzt, 1),
                "intervall_max_s": None if mw.intervall_max is None else round(mw.intervall_max, 1),
            })
        return zeilen
