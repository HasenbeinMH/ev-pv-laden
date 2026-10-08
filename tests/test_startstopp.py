"""Start/Stopp: jede Ladung bewusst starten, waehrend der Ladung gesperrt, Abstecken stoppt,
Ladung von aussen (go-e-App) wird erkannt und nicht gestoert."""
import pytest

import datenbank as db
import mqtt_ha
from erfassung import Erfassung
from konfig import Konfig
from laufzeit import Laufzeit
from prozessabbild import Prozessabbild
from regelung import Regelung
from strategie import AUS, NUR_PV, SOFORT

K = Konfig(goe_seriennummer="325656")


def z(s, e=None):
    return {"s": str(s), "a": {"unit_of_measurement": e} if e else {}}


@pytest.fixture
def reg(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_DATEI", str(tmp_path / "t.db"))
    db.initialisieren()
    r = Regelung(K, Prozessabbild(K))
    stecken(r, True)
    return r


def stecken(r, an, t=0.0, auto_w=0):
    for eid, zst in {"binary_sensor.goe_325656_car_0": z("on" if an else "off"),
                     "sensor.goe_325656_nrg_0": z(1), "sensor.goe_325656_nrg_11": z(auto_w, "W")}.items():
        r.abbild.aktualisieren(eid, zst, t)


def test_gestoppt_sperrt_wallbox(reg):
    reg.parameter_setzen({"modus": SOFORT})
    a = reg.zyklus(1.0)
    assert reg.modus_wirksam == AUS and not a.freigabe and "Start" in a.grund


def test_start_und_sperre_waehrend_der_ladung(reg):
    reg.parameter_setzen({"modus": SOFORT})
    assert reg.starten() == []
    a = reg.zyklus(1.0)
    assert reg.modus_wirksam == SOFORT and a.freigabe
    assert reg.parameter_setzen({"modus": NUR_PV})            # gesperrt
    assert reg.parameter_setzen({"start_w": 2000})            # gesperrt
    assert reg.parameter_setzen({"modus": SOFORT}) == []      # unveraendert ist kein Fehler
    reg.stoppen()
    assert reg.parameter_setzen({"modus": NUR_PV}) == []


def test_ohne_modus_kein_start(reg):
    reg.parameter_setzen({"modus": AUS})
    assert reg.starten() and not reg.gestartet


def test_abstecken_stoppt(reg):
    reg.parameter_setzen({"modus": SOFORT})
    reg.starten()
    reg.zyklus(1.0)
    stecken(reg, False, 2.0)
    reg.zyklus(2.0)
    assert not reg.gestartet


def test_zustand_ueberlebt_neustart(reg):
    reg.parameter_setzen({"modus": SOFORT})
    reg.starten()
    assert Regelung(K, Prozessabbild(K)).gestartet


def test_ha_schalter():
    assert mqtt_ha.befehl_uebersetzen("laden", "ON") == ("laden", True)
    assert mqtt_ha.befehl_uebersetzen("laden", "OFF") == ("laden", False)


# --- Ladung von aussen (go-e-App) -----------------------------------------------------------

@pytest.fixture
def lz(reg):
    l = Laufzeit()
    l.konfig, l.regelung, l.abbild = K, reg, reg.abbild
    l.erfassung = Erfassung(K, reg.abbild)
    l._treiber_setzen("ids")
    return l


def test_extern_kurz_nach_start_erkannt_und_bis_abstecken(lz):
    lz._extern_pruefen(0.0, {"auto_w": 0.0})                  # Fenster beginnt
    lz._extern_pruefen(30.0, {"auto_w": 7000.0})              # laedt ohne Start im Add-on
    assert lz.regelung.extern
    stecken(lz.regelung, True, 31.0, 7000)
    lz.regelung.zyklus(31.0)
    stecken(lz.regelung, False, 40.0)
    lz.regelung.zyklus(40.0)
    assert not lz.regelung.extern


def test_spaetes_einschalten_ist_nicht_extern(lz):
    lz._extern_pruefen(0.0, {"auto_w": 0.0})
    lz._extern_pruefen(300.0, {"auto_w": 7000.0})             # HA laeuft normal: Add-on gilt
    assert not lz.regelung.extern


def test_gestartet_ist_nie_extern(lz):
    lz.regelung.parameter_setzen({"modus": SOFORT})
    lz.regelung.starten()
    lz._extern_pruefen(0.0, {"auto_w": 7000.0})
    assert not lz.regelung.extern


# --- Ladekurve (Autokarte) --------------------------------------------------------------------

def test_ladekurve_schnittstelle(lz):
    from datetime import datetime
    from fastapi.testclient import TestClient
    from ladevorgang import Vorgang
    from webapp.app import app

    app.state.lz = lz
    c = TestClient(app)
    assert c.get("/api/ladekurve").json() == {"aktiv": False}
    start = datetime.now(lz.erfassung.tz).replace(second=0, microsecond=0)
    lz.erfassung.erkennung.offen = Vorgang(start, lz.erfassung.stand())
    from tagesverlauf import GROESSEN
    t = start.timestamp()
    m = lambda w: {g: (w if g == "auto" else 0) for g in GROESSEN}
    lz.tagesverlauf.vorfuellen([(t - 60, m(9)), (t, m(4000)), (t + 60, m(4100))])
    d = c.get("/api/ladekurve").json()
    assert d["aktiv"] and [z[0] for z in d["daten"]] == [t, t + 60]     # erst ab Ladebeginn
