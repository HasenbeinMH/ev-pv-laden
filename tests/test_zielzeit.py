from datetime import datetime, timedelta, timezone

import pytest

import datenbank as db
from konfig import Konfig
from prozessabbild import Prozessabbild
from regelung import Regelung
from strategie import Parameter, SOFORT, ZIELZEIT
from zielzeit import SocSchaetzer, Zielzeit, naechste_abfahrt

TZ = timezone(timedelta(hours=2))
KAP, WG = 58.3, 0.9
P_MAX = 24 * 230.0 * 3          # 16,56 kW: Wallbox begrenzt (EV3 koennte 22 kW)


def um(h, m=0, tag=5):
    return datetime(2026, 10, tag, h, m, tzinfo=TZ)


# --- SoC-Schaetzung -------------------------------------------------------------------------

def test_hochrechnung_mit_wallbox_zaehler():
    s = SocSchaetzer(KAP, WG)
    s.setzen(40.0, 1000.0, 0.0)
    assert s.soc(1000.0) == 40.0
    # 10 kWh aus der Wallbox x 0,9 / 58,3 kWh = +15,4 %
    assert s.soc(1010.0) == pytest.approx(40.0 + 9.0 / KAP * 100)
    assert s.soc(1200.0) == 100.0


def test_abstecken_verwirft_anker():
    s = SocSchaetzer(KAP, WG)
    s.setzen(40.0, 1000.0, 0.0)
    s.zyklus(1.0, 1000.0, False, None)
    assert s.soc(1000.0) is None and s.geaendert


def test_sensor_setzt_anker_nur_bei_neuem_wert():
    s = SocSchaetzer(KAP, WG)
    s.zyklus(0.0, 1000.0, True, 50.0)
    assert s.anker.quelle == "Sensor"
    s.setzen(55.0, 1002.0, 10.0)                     # Eingabe danach hat Vorrang ...
    s.zyklus(11.0, 1002.0, True, 50.0)               # ... alter Sensorwert ueberschreibt nicht
    assert s.anker.soc == 55.0
    s.zyklus(12.0, 1003.0, True, 60.0)               # neuer Sensorwert setzt
    assert (s.anker.soc, s.anker.eto_kwh) == (60.0, 1003.0)


def test_zaehler_unbekannt_wird_nachgetragen():
    s = SocSchaetzer(KAP, WG)
    s.setzen(30.0, None, 0.0)
    assert s.soc(None) == 30.0
    s.zyklus(1.0, 500.0, True, None)
    assert s.soc(505.0) > 30.0


def test_anker_ueberlebt_neustart():
    s = SocSchaetzer(KAP, WG)
    s.setzen(40.0, 1000.0, 123.0)
    neu = SocSchaetzer(KAP, WG, s.anker.als_dict())
    assert neu.soc(1010.0) == s.soc(1010.0)


# --- Plan -----------------------------------------------------------------------------------

def test_naechste_abfahrt():
    assert naechste_abfahrt(um(6), "07:00") == um(7)
    assert naechste_abfahrt(um(8), "07:00") == um(7, tag=6)


def test_vor_spaetestem_start_nur_pv():
    z = Zielzeit()
    # 40 -> 80 %: 23,32 kWh / 0,9 = 25,9 kWh; bei 16,56 kW 1 h 34 min; + 30 min -> 04:56
    p = z.planen(um(0), "07:00", 80, 30, 40.0, KAP, WG, P_MAX, True)
    assert p.modus == "nur_pv" and not p.sofort
    assert p.benoetigt_kwh == pytest.approx(25.91, abs=0.01)
    assert p.spaetester_start.strftime("%H:%M") == "04:56"


def test_ab_spaetestem_start_sofort_und_selbsthaltend():
    z = Zielzeit()
    assert z.planen(um(5), "07:00", 80, 30, 40.0, KAP, WG, P_MAX, True).modus == SOFORT
    # Abfahrtszeit vorbei, Ziel noch nicht erreicht: weiter Netz (naechste Abfahrt waere morgen)
    assert z.planen(um(7, 30), "07:00", 80, 30, 75.0, KAP, WG, P_MAX, True).modus == SOFORT
    assert z.planen(um(7, 40), "07:00", 80, 30, 80.0, KAP, WG, P_MAX, True).modus == "nur_pv"
    assert z.planen(um(7, 41), "07:00", 80, 30, 79.0, KAP, WG, P_MAX, True).modus == "nur_pv"


def test_abstecken_beendet_sofort():
    z = Zielzeit()
    z.planen(um(5), "07:00", 80, 30, 40.0, KAP, WG, P_MAX, True)
    z.planen(um(5, 1), "07:00", 80, 30, 40.0, KAP, WG, P_MAX, False)
    assert z.planen(um(12), "07:00", 80, 30, 40.0, KAP, WG, P_MAX, True).modus == "nur_pv"


def test_ohne_soc_nur_pv_mit_hinweis():
    p = Zielzeit().planen(um(6, 50), "07:00", 80, 30, None, KAP, WG, P_MAX, True)
    assert p.modus == "nur_pv" and "SoC" in p.grund


def test_parameter_pruefen():
    assert Parameter(abfahrt="7:00").pruefen()
    assert Parameter(abfahrt="24:00").pruefen()
    assert Parameter(ziel_soc=5).pruefen()
    assert not Parameter(abfahrt="06:45", ziel_soc=90, puffer_min=0).pruefen()


# --- Regelung: wirksamer Modus ---------------------------------------------------------------

@pytest.fixture
def reg(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_DATEI", str(tmp_path / "t.db"))
    db.initialisieren()
    k = Konfig(goe_seriennummer="325656")
    return Regelung(k, Prozessabbild(k))


def z(s, e=None):
    return {"s": str(s), "a": {"unit_of_measurement": e} if e else {}}


def test_regelung_zielzeit_schaltet_auf_sofort(reg):
    pa, g = reg.abbild, "goe_325656"
    for eid, zst in {"binary_sensor.goe_325656_car_0": z("on"), f"sensor.{g}_eto": z(1000, "kWh"),
                     f"sensor.{g}_rbt": z(1), f"sensor.{g}_nrg_11": z(0, "W")}.items():
        pa.aktualisieren(eid, zst, 0.0)
    reg.tz = TZ
    assert reg.p_plan == P_MAX                       # min(22 kW, 16,56 kW)
    reg.parameter_setzen({"modus": ZIELZEIT, "abfahrt": "07:00", "ziel_soc": 80, "puffer_min": 30})
    reg.starten()
    reg.zyklus(0.0, um(5).timestamp())
    assert reg.modus_wirksam == "nur_pv" and "SoC" in reg.aus.grund
    reg.auto_soc_setzen(40)
    a = reg.zyklus(1.0, um(5).timestamp())
    assert reg.modus_wirksam == SOFORT and a.freigabe and a.p_erlaubt == reg.p_max
    assert db.einstellung("auto_soc")["soc"] == 40
