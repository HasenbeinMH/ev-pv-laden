"""Erfassungszyklus mit echter (Temp-)Datenbank: Laden simulieren, Neustart, Zaehler."""
from datetime import datetime, timedelta

import pytest

import datenbank as db
import mqtt_ha
from erfassung import Erfassung
from konfig import Konfig
from prozessabbild import Prozessabbild
from regelung import Regelung

K = Konfig(goe_seriennummer="325656", sensor_lebenszeichen="sensor.se_modbus_daten_m1_ac_power")
G = "325656"
T0 = datetime(2026, 10, 3, 12, 0, 0)


@pytest.fixture
def frische_db(tmp_path, monkeypatch):
    pfad = str(tmp_path / "e.db")
    monkeypatch.setattr(db, "DB_DATEI", pfad)
    db.initialisieren()
    return pfad


def z(s, einheit=None):
    return {"s": str(s), "a": {"unit_of_measurement": einheit} if einheit else {}}


class Anlage:
    """Simuliert SolarEdge + go-e: konstante Leistungen, eto steigt passend."""
    def __init__(self, pa: Prozessabbild, eto_kwh=1000.0):
        self.pa, self.eto = pa, eto_kwh

    def schritt(self, t, p_auto, einspeisung_se, akku_se_laden, steckt=True):
        pa = self.pa
        pa.aktualisieren(K.sensor_netz, z(einspeisung_se, "W"), t)          # SolarEdge: + = Einspeisung
        pa.aktualisieren(K.sensor_akku_leistung, z(akku_se_laden, "W"), t)  # SolarEdge: + = Laden
        pa.aktualisieren(K.sensor_akku_soc, z(80, "%"), t)
        pa.aktualisieren(f"sensor.goe_{G}_rbt", z(int(t * 1000)), t)
        pa.aktualisieren(f"sensor.goe_{G}_nrg_11", z(p_auto, "W"), t)
        pa.aktualisieren(f"binary_sensor.goe_{G}_car_0", z("on" if steckt else "off"), t)
        self.eto += p_auto / 1000 / 3600
        pa.aktualisieren(f"sensor.goe_{G}_eto", z(round(self.eto, 3), "kWh"), t)


def laufen(erf, anlage, start_s, dauer_s, **leistung):
    for s in range(start_s, start_s + dauer_s):
        anlage.schritt(float(s), **leistung)
        erf.zyklus(float(s), T0 + timedelta(seconds=s))


def test_laden_buchen_neustart_ohne_ruecksprung(frische_db):
    pa = Prozessabbild(K)
    erf = Erfassung(K, pa)
    anlage = Anlage(pa)
    # 30 min: Auto 7,2 kW, 1 kW Einspeisung -> alles PV; Akku entlaedt 0
    laufen(erf, anlage, 0, 1800, p_auto=7200, einspeisung_se=1000, akku_se_laden=0)
    # 30 min: Auto 7,2 kW, 2 kW Netzbezug, Akku entlaedt 3 kW -> 2,2 PV / 3 Akku / 2 Netz
    laufen(erf, anlage, 1800, 1800, p_auto=7200, einspeisung_se=-2000, akku_se_laden=-3000)
    zaehler = erf.bilanz.z.kwh
    gesamt = sum(zaehler.values())
    assert gesamt == pytest.approx(7.2, abs=0.01)
    assert zaehler["netz"] == pytest.approx(1.0, abs=0.02)
    assert zaehler["akku"] == pytest.approx(1.5, abs=0.02)
    assert zaehler["pv"] == pytest.approx(3.6 + 1.1, abs=0.02)
    assert erf.erkennung.offen is not None                 # Ladung laeuft
    vorher = dict(zaehler)

    # Neustart: Zustand sichern, neue Instanz laedt aus der Datenbank
    erf.sichern()
    pa2 = Prozessabbild(K)
    erf2 = Erfassung(K, pa2)
    assert erf2.erkennung.offen is not None                # offene Ladung uebernommen
    for q in vorher:
        assert erf2.bilanz.z.kwh[q] == pytest.approx(vorher[q])
    # Waehrend des Neustarts wurden 0,5 kWh geladen -> ohne Aufteilung als Netz
    anlage2 = Anlage(pa2, anlage.eto + 0.5)
    laufen(erf2, anlage2, 10000, 5, p_auto=7200, einspeisung_se=1000, akku_se_laden=0)
    assert erf2.bilanz.z.kwh_ohne_aufteilung == pytest.approx(0.5, abs=0.003)
    for q in vorher:
        assert erf2.bilanz.z.kwh[q] >= vorher[q]

    # Auto abstecken -> Ladung beendet und gespeichert
    laufen(erf2, anlage2, 10005, 2, p_auto=0, einspeisung_se=1000, akku_se_laden=0, steckt=False)
    v = db.vorgaenge(5)[0]
    assert v["ende"] is not None and v["grund"] == "abgesteckt"
    assert v["eto"] == pytest.approx(7.2 + 0.5 + 0.01, abs=0.03)
    tag = db.bilanz_tage(1)[0]
    assert tag["datum"] == "2026-10-03"
    assert tag["pv"] + tag["akku"] + tag["netz"] == pytest.approx(tag["eto"], abs=1e-6)


def test_zaehler_tabelle_verhindert_ruecksprung(frische_db):
    """Selbst wenn der JSON-Zustand kleinere Werte enthaelt, gewinnt die Tabelle."""
    db.bilanz_speichern({"kwh": {"pv": 5.0, "akku": 1.0, "netz": 2.0}})
    db.bilanz_speichern({"kwh": {"pv": 1.0, "akku": 0.0, "netz": 0.0}})   # Fehlerfall
    geladen = db.bilanz_laden()
    assert geladen["kwh"] == {"pv": 5.0, "akku": 1.0, "netz": 2.0}


def test_ama_warnung(frische_db):
    pa = Prozessabbild(K)
    erf = Erfassung(K, pa)
    pa.aktualisieren(f"sensor.goe_{G}_rbt", z(1), 1.0)
    pa.aktualisieren(f"number.goe_{G}_ama", z(16, "A"), 1.0)
    erf.zyklus(1.0, T0)
    erf.zyklus(2.0, T0)   # nur einmal melden
    texte = [e["text"] for e in db.ereignisse(10) if e["quelle"] == "ueberwachung"]
    assert len(texte) == 1 and "16 A begrenzt" in texte[0]


def test_mqtt_zustand_passt_zur_discovery(frische_db):
    pa = Prozessabbild(K)
    erf, reg = Erfassung(K, pa), Regelung(K, pa)
    reg.zyklus()
    # PV-Werte liefert die Laufzeit (Laufzeit._pv_mqtt)
    pv = {"pv_prognose_heute": 1.0, "pv_prognose_rest_heute": 0.5, "pv_prognose_morgen": 2.0,
          "pv_sauberkeit": 80}
    zustand = {**erf.mqtt_zustand(), **reg.mqtt_zustand(), **pv,
               **mqtt_ha.bedien_zustand(reg.param, True, None)}
    nutzlast = mqtt_ha.discovery_nutzlast()
    for name, komp in nutzlast["components"].items():
        if set(komp) == {"platform"} or komp.get("state_topic") == mqtt_ha.EREIGNIS:
            continue    # Entfernen einer alten Entitaet bzw. Ereignis mit eigenem Topic
        assert komp["unique_id"].startswith("ev_pv_laden_")
        if "command_topic" in komp:
            assert komp["command_topic"] == f"{mqtt_ha.BEFEHL}/{name}"
        assert name in zustand, f"{name} fehlt im Zustand"
    zaehler = [k for n, k in nutzlast["components"].items() if n.startswith("kwh_")]
    assert len(zaehler) == 4
    assert all(k["state_class"] == "total_increasing" and k["unit_of_measurement"] == "kWh"
               for k in zaehler)
    assert {"device", "origin", "components"} <= set(nutzlast)
