# -*- coding: utf-8 -*-
"""
Add-on-Konfiguration aus /data/options.json (vom Supervisor aus config.yaml erzeugt).

Die elektrischen Grenzen stehen zusaetzlich als Konstanten im Code: Das Schema in
config.yaml begrenzt die Eingabe zwar schon, aber options.json koennte auch von Hand
oder von einer aelteren Version stammen. Wie bei einer SPS: Grenzwert im Programm,
nicht nur im Bedienbild.
"""
import json
import os
import re
from dataclasses import MISSING, dataclass, field, fields

DATA_DIR = os.environ.get("EVPV_DATA", "/data")
OPTIONS_DATEI = os.environ.get("EVPV_OPTIONS", os.path.join(DATA_DIR, "options.json"))

# Zuleitung 25 A Typ B, Ladeleistung auf ~17 kW begrenzt
GRENZE_STROM_A = 24
# VDE-AR-N 4100: Schieflast hoechstens 4,6 kVA je Aussenleiter = 20 A bei 230 V
GRENZE_STROM_1PH_A = 20
# IEC 61851: kleinster zulaessiger Ladestrom
GRENZE_MIN_STROM_A = 6

_ENTITY = re.compile(r"^sensor\.[a-z0-9_]+$")


class KonfigFehler(Exception):
    """options.json fehlt, ist kaputt oder enthaelt unzulaessige Werte."""
    def __init__(self, fehler: list[str]):
        super().__init__("; ".join(fehler))
        self.fehler = fehler


@dataclass(frozen=True)
class Konfig:
    trockenlauf: bool = True
    log_level: str = "info"
    sensor_netz: str = "sensor.se_modbus_daten_m1_ac_power"
    sensor_netz_invertieren: bool = True
    sensor_akku_leistung: str = "sensor.se_modbus_daten_battery1_power"
    sensor_akku_leistung_invertieren: bool = True
    sensor_akku_soc: str = "sensor.se_modbus_daten_battery1_state_of_charge"
    sensor_pv: str = ""
    sensor_lebenszeichen: str = ""
    max_alter_s: int = 15
    goe_seriennummer: str = ""
    # Treiber ids: echte PV-Leistung als pPv mitsenden (sonst 0) – Wirkung wird getestet
    ids_ppv_senden: bool = True
    max_strom_a: int = GRENZE_STROM_A
    max_strom_1ph_a: int = GRENZE_STROM_1PH_A
    ev_max_strom_1ph_a: int = 16
    min_strom_a: int = GRENZE_MIN_STROM_A
    akku_kapazitaet_kwh: float = 58.3
    ladewirkungsgrad: float = 0.9
    ev_tracker_url: str = ""
    ev_tracker_token: str = ""
    akku_als_netz: bool = False
    # PV-Prognose (eigenes Modell): Dachflaechen und Quelle der gemessenen PV-Erzeugung
    pv_flaechen: list = field(default_factory=list)
    # Entweder ein Energiezaehler der PV-Erzeugung (kWh) ...
    sensor_pv_energie: str = ""
    # ... oder SolarEdge-Hybrid: PV = DC-Leistung + Akku geladen - Akku entladen
    sensor_pv_dc_leistung: str = "sensor.se_modbus_daten_dc_power"
    sensor_akku_geladen: str = "sensor.se_modbus_daten_battery1_charged"
    sensor_akku_entladen: str = "sensor.se_modbus_daten_battery1_discharged"

    @property
    def strom_1ph_max_a(self) -> int:
        """Hoechster Strom bei einphasigem Laden: Schieflast, Auto und Zuleitung zugleich."""
        return min(self.max_strom_1ph_a, self.ev_max_strom_1ph_a, self.max_strom_a)

    @property
    def goe_praefix(self) -> str:
        return f"goe_{self.goe_seriennummer}"

    def ohne_geheimnisse(self) -> dict:
        """Fuer Anzeige und Protokoll – Token nie im Klartext."""
        d = {f.name: getattr(self, f.name) for f in fields(self)}
        if d["ev_tracker_token"]:
            d["ev_tracker_token"] = "***"
        return d


def pruefen(k: Konfig) -> list[str]:
    """Alle Verstoesse auf einmal melden, damit man nicht Fehler fuer Fehler beheben muss."""
    f = []
    if not k.sensor_netz or not _ENTITY.match(k.sensor_netz):
        f.append(f"sensor_netz ungueltig: '{k.sensor_netz}'")
    for name in ("sensor_akku_leistung", "sensor_akku_soc", "sensor_pv", "sensor_lebenszeichen"):
        wert = getattr(k, name)
        if wert and not _ENTITY.match(wert):
            f.append(f"{name} ungueltig: '{wert}'")
    if not re.fullmatch(r"[0-9]+", k.goe_seriennummer or ""):
        f.append(f"goe_seriennummer ungueltig: '{k.goe_seriennummer}'")
    if not GRENZE_MIN_STROM_A <= k.max_strom_a <= GRENZE_STROM_A:
        f.append(f"max_strom_a={k.max_strom_a} ausserhalb {GRENZE_MIN_STROM_A}..{GRENZE_STROM_A} A")
    if not GRENZE_MIN_STROM_A <= k.max_strom_1ph_a <= GRENZE_STROM_1PH_A:
        f.append(f"max_strom_1ph_a={k.max_strom_1ph_a} ausserhalb "
                 f"{GRENZE_MIN_STROM_A}..{GRENZE_STROM_1PH_A} A (Schieflast)")
    if k.ev_max_strom_1ph_a < GRENZE_MIN_STROM_A:
        f.append(f"ev_max_strom_1ph_a={k.ev_max_strom_1ph_a} kleiner {GRENZE_MIN_STROM_A} A")
    if not GRENZE_MIN_STROM_A <= k.min_strom_a <= k.max_strom_a:
        f.append(f"min_strom_a={k.min_strom_a} muss zwischen {GRENZE_MIN_STROM_A} und max_strom_a liegen")
    if not 5 <= k.max_alter_s <= 300:
        f.append(f"max_alter_s={k.max_alter_s} ausserhalb 5..300 s")
    if not 10 <= k.akku_kapazitaet_kwh <= 200:
        f.append(f"akku_kapazitaet_kwh={k.akku_kapazitaet_kwh} unplausibel")
    if not 0.5 <= k.ladewirkungsgrad <= 1:
        f.append(f"ladewirkungsgrad={k.ladewirkungsgrad} ausserhalb 0,5..1")
    if k.log_level not in ("debug", "info", "warning", "error"):
        f.append(f"log_level ungueltig: '{k.log_level}'")
    if k.ev_tracker_url and not k.ev_tracker_url.startswith(("http://", "https://")):
        f.append("ev_tracker_url muss mit http:// oder https:// beginnen")
    for name in ("sensor_pv_energie", "sensor_pv_dc_leistung", "sensor_akku_geladen", "sensor_akku_entladen"):
        wert = getattr(k, name)
        if wert and not _ENTITY.match(wert):
            f.append(f"{name} ungueltig: '{wert}'")
    namen = set()
    for i, fl in enumerate(k.pv_flaechen):
        if not isinstance(fl, dict):
            f.append(f"pv_flaechen[{i}]: Eintrag mit name, neigung, azimut, kwp erwartet")
            continue
        try:
            if not str(fl.get("name", "")).strip():
                raise ValueError("name fehlt")
            if not 0 <= float(fl["neigung"]) <= 90:
                raise ValueError("neigung 0..90")
            if not 0 <= float(fl["azimut"]) <= 360:
                raise ValueError("azimut 0..360 (0 Nord, 90 Ost, 180 Sued)")
            if not 0.05 <= float(fl["kwp"]) <= 100:
                raise ValueError("kwp 0,05..100")
        except (KeyError, TypeError, ValueError) as e:
            f.append(f"pv_flaechen[{i}] ungueltig: {e}")
            continue
        if fl["name"] in namen:
            f.append(f"pv_flaechen: Name '{fl['name']}' doppelt")
        namen.add(fl["name"])
    return f


def laden(pfad: str = OPTIONS_DATEI) -> Konfig:
    """Liest options.json. Unbekannte Schluessel werden ignoriert (aeltere/neuere Version),
    fehlende bekommen den Standardwert. Bei Verstoessen: KonfigFehler, keine Teil-Konfig."""
    try:
        with open(pfad, encoding="utf-8") as fh:
            roh = json.load(fh)
    except FileNotFoundError:
        raise KonfigFehler([f"{pfad} nicht gefunden"])
    except (OSError, json.JSONDecodeError) as e:
        raise KonfigFehler([f"{pfad} nicht lesbar: {e}"])
    if not isinstance(roh, dict):
        raise KonfigFehler([f"{pfad}: JSON-Objekt erwartet"])

    werte, fehler = {}, []
    for feld in fields(Konfig):
        if feld.name not in roh:
            continue
        if feld.default is MISSING:   # Listen (default_factory)
            if not isinstance(roh[feld.name], list):
                fehler.append(f"{feld.name}: Liste erwartet")
            else:
                werte[feld.name] = roh[feld.name]
            continue
        wert, typ = roh[feld.name], type(feld.default)
        # bool zuerst: in Python ist bool eine Unterklasse von int
        if typ is bool and not isinstance(wert, bool):
            fehler.append(f"{feld.name}: true/false erwartet, nicht '{wert}'")
        elif typ is int and (isinstance(wert, bool) or not isinstance(wert, int)):
            fehler.append(f"{feld.name}: ganze Zahl erwartet, nicht '{wert}'")
        elif typ is float and (isinstance(wert, bool) or not isinstance(wert, (int, float))):
            fehler.append(f"{feld.name}: Zahl erwartet, nicht '{wert}'")
        elif typ is str and not isinstance(wert, str):
            fehler.append(f"{feld.name}: Text erwartet, nicht '{wert}'")
        else:
            werte[feld.name] = float(wert) if typ is float else (wert.strip() if typ is str else wert)
    if fehler:
        raise KonfigFehler(fehler)

    k = Konfig(**werte)
    fehler = pruefen(k)
    if fehler:
        raise KonfigFehler(fehler)
    return k
