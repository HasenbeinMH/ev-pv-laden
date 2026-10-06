import pytest

import datenbank as db
from konfig import Konfig
from prozessabbild import Prozessabbild
from regelung import Regelung
import mqtt_ha
from strategie import MIN_PV, NUR_PV, SOFORT, Parameter
from tageslicht import Tageslicht

ARG = dict(unter_w=50, unter_s=900, ueber_w=300, ueber_s=300)


def test_erster_wert_setzt_sofort():
    assert Tageslicht().zyklus(0, 10, **ARG) is True
    assert Tageslicht().zyklus(0, 2000, **ARG) is False
    assert Tageslicht().zyklus(0, None, **ARG) is None


def test_hysterese_und_verzoegerung():
    t = Tageslicht()
    t.zyklus(0, 2000, **ARG)
    assert t.zyklus(10, 30, **ARG) is False           # unter 50 W, Zeit laeuft
    assert t.zyklus(909, 30, **ARG) is False
    assert t.zyklus(910, 30, **ARG) is True           # 15 min -> Nacht
    assert t.zyklus(920, 200, **ARG) is True          # 200 W reicht nicht (Hysterese)
    assert t.zyklus(930, 400, **ARG) is True          # ueber 300 W, Zeit laeuft
    assert t.zyklus(1230, 400, **ARG) is False        # 5 min -> Tag


def test_kurzer_einbruch_setzt_zeit_zurueck():
    t = Tageslicht()
    t.zyklus(0, 2000, **ARG)
    t.zyklus(10, 30, **ARG)
    t.zyklus(500, 800, **ARG)                         # Wolke vorbei
    assert t.zyklus(1000, 30, **ARG) is False         # Zeit beginnt neu


def test_parameter_pruefen():
    assert Parameter(ohne_pv="nacht").pruefen()
    assert Parameter(ohne_pv_unter_w=400, ohne_pv_ueber_w=300).pruefen()
    assert not Parameter(ohne_pv="pause").pruefen()
    assert Parameter(ohne_pv="mindest").pruefen()                       # gibt es nicht mehr ...
    assert Parameter.aus_dict({"ohne_pv": "mindest", "modus": "min_pv"}).ohne_pv == "pause"   # ... Umstellung
    assert Parameter().ohne_pv == "pause"


def test_schalter_nachtladen_aus_ha():
    assert mqtt_ha.befehl_uebersetzen("nachtladen", "ON") == ("ohne_pv", "voll")
    assert mqtt_ha.befehl_uebersetzen("nachtladen", "OFF") == ("ohne_pv", "pause")
    assert mqtt_ha.bedien_zustand(Parameter(ohne_pv="voll"), True, None)["nachtladen"] == "ON"


@pytest.fixture
def reg(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_DATEI", str(tmp_path / "t.db"))
    db.initialisieren()
    k = Konfig(goe_seriennummer="325656", sensor_pv="sensor.pv")
    r = Regelung(k, Prozessabbild(k))
    for eid, s, e in (("binary_sensor.goe_325656_car_0", "on", None), ("sensor.goe_325656_rbt", "1", None),
                      ("sensor.goe_325656_nrg_11", "0", "W"), ("sensor.pv", "0", "W"),
                      (k.sensor_netz, "0", "W"), (k.sensor_akku_leistung, "0", "W"), (k.sensor_akku_soc, "50", "%")):
        r.abbild.aktualisieren(eid, {"s": s, "a": {"unit_of_measurement": e} if e else {}}, 0.0)
    return r


@pytest.mark.parametrize("modus, ohne_pv, erwartet", [(MIN_PV, "voll", SOFORT), (MIN_PV, "pause", NUR_PV),
                                                       (NUR_PV, "voll", SOFORT), (NUR_PV, "pause", NUR_PV)])
def test_nachts(reg, modus, ohne_pv, erwartet):
    reg.parameter_setzen({"modus": modus, "ohne_pv": ohne_pv})
    assert reg.starten() == []
    a = reg.zyklus(1.0)
    assert reg.modus_wirksam == erwartet
    if ohne_pv == "voll":
        assert a.freigabe and a.p_erlaubt == reg.p_max and "Netz" in a.grund
    if ohne_pv == "pause":
        assert not a.freigabe and "Pause" in a.grund


def test_ohne_pv_sensor_bleibt_min_pv(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_DATEI", str(tmp_path / "t.db"))
    db.initialisieren()
    k = Konfig(goe_seriennummer="325656")             # kein PV-Sensor
    r = Regelung(k, Prozessabbild(k))
    r.parameter_setzen({"modus": MIN_PV, "ohne_pv": "voll"})
    r.starten()
    r.zyklus(1.0)
    assert r.modus_wirksam == MIN_PV
