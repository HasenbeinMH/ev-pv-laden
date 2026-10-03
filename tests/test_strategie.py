import glob
import os

import pytest

from simulation import Akku, simulieren, ueberschuss_aus_csv
from strategie import (AUS, MIN_PV, NUR_PV, SOFORT, Eingang, Parameter, Strategie,
                       pgrid_virtuell)

P_MIN, P_MAX = 6 * 230.0, 24 * 230.0 * 3


def strat(**param):
    return Strategie(Parameter(**param), P_MIN, P_MAX)


def e(t, p_auto=0.0, netz=0.0, akku=0.0, soc=95.0, steckt=True):
    return Eingang(t, p_auto, netz, akku, soc, steckt)


# --- verfuegbare Leistung ------------------------------------------------------------------

def test_einspeisung_ist_ueberschuss():
    assert strat().verfuegbar(e(0, p_auto=2000, netz=-3000)) == 5000


def test_akku_entladung_ist_defizit():
    assert strat().verfuegbar(e(0, p_auto=5000, netz=0, akku=1500)) == 3500


def test_akku_ladung_nur_ueber_schwelle():
    unter = strat(akku_soc_schwelle=90).verfuegbar(e(0, netz=-500, akku=-3000, soc=60))
    ueber = strat(akku_soc_schwelle=90).verfuegbar(e(0, netz=-500, akku=-3000, soc=92))
    assert unter == 500 and ueber == 3500


def test_akku_unterstuetzung():
    s = strat(akku_unterstuetzung_w=1000, akku_unterstuetzung_soc=80)
    assert s.verfuegbar(e(0, p_auto=4000, akku=1500, soc=85)) == 3500   # nur 500 W Defizit
    assert s.verfuegbar(e(0, p_auto=4000, akku=1500, soc=70)) == 2500   # unter SoC: volles Defizit


def test_ohne_akku():
    s = strat()
    assert s.verfuegbar(Eingang(0, 1000, -2000, 0.0, None, True, akku_vorhanden=False)) == 3000


@pytest.mark.parametrize("feld", ["p_auto", "netz", "akku", "soc"])
def test_ungueltiger_wert_kein_ueberschuss(feld):
    werte = {"p_auto": 0.0, "netz": -5000.0, "akku": 0.0, "soc": 95.0}
    werte[feld] = None
    assert strat().verfuegbar(e(0, **werte)) is None


# --- Start/Stopp ---------------------------------------------------------------------------

def test_start_erst_nach_verzoegerung():
    s = strat(tau_s=0, start_verz_s=60)
    assert s.schritt(e(0, netz=-3000)).zustand == "startet"
    assert s.schritt(e(59, netz=-3000)).freigabe is False
    a = s.schritt(e(60, netz=-3000))
    assert a.freigabe and a.p_erlaubt == 3000


def test_unterbrochene_startbedingung_beginnt_neu():
    s = strat(tau_s=0, start_verz_s=60)
    s.schritt(e(0, netz=-3000))
    s.schritt(e(30, netz=-500))
    assert s.schritt(e(70, netz=-3000)).freigabe is False


def test_stopp_mit_verzoegerung_und_mindestladedauer():
    s = strat(tau_s=0, start_verz_s=0, stopp_verz_s=180, min_ladedauer_s=600)
    s.schritt(e(0, netz=-3000))
    a = s.schritt(e(10, p_auto=3000, netz=2500))     # Wolke: nur noch 500 W
    assert a.freigabe and a.zustand == "stoppt" and a.p_erlaubt == P_MIN
    assert s.schritt(e(400, p_auto=1380, netz=880)).freigabe is True     # Mindestladedauer
    assert s.schritt(e(600, p_auto=1380, netz=880)).freigabe is False


def test_mindestpause():
    s = strat(tau_s=0, start_verz_s=0, stopp_verz_s=0, min_ladedauer_s=0, min_pause_s=300)
    s.schritt(e(0, netz=-3000))
    s.schritt(e(1, p_auto=3000, netz=3000))
    a = s.schritt(e(100, netz=-5000))
    assert a.freigabe is False and a.zustand == "pause"
    assert s.schritt(e(301, netz=-5000)).freigabe is True


def test_glaettung_pt1():
    s = strat(tau_s=30, start_verz_s=0)
    s.schritt(e(0, netz=0))
    a = s.schritt(e(30, netz=-3000))
    assert a.p_glatt == pytest.approx(1500)     # dt = tau -> halber Sprung


def test_watchdog_stoppt_sofort():
    s = strat(tau_s=0, start_verz_s=0, stopp_verz_s=180, min_ladedauer_s=600)
    s.schritt(e(0, netz=-5000))
    a = s.schritt(Eingang(1, 5000, None, 0, 95, True))
    assert a.freigabe is False and "ungültig" in a.grund


# --- Modi ----------------------------------------------------------------------------------

def test_modus_aus_und_nicht_gesteckt():
    assert strat(modus=AUS).schritt(e(0, netz=-9000)).freigabe is False
    assert strat().schritt(e(0, netz=-9000, steckt=False)).grund == "kein Fahrzeug angesteckt"


def test_sofort_volle_leistung_ohne_sensoren():
    a = strat(modus=SOFORT).schritt(Eingang(0, None, None, None, None, True))
    assert a.freigabe and a.p_erlaubt == P_MAX


def test_min_pv_mindestens_mindestleistung():
    s = strat(modus=MIN_PV, tau_s=0)
    assert s.schritt(e(0, netz=500)).p_erlaubt == P_MIN
    assert s.schritt(e(1, netz=-6000)).p_erlaubt == 6000
    assert s.schritt(Eingang(2, None, None, None, None, True)).p_erlaubt == P_MIN


def test_nie_ueber_p_max():
    s = strat(tau_s=0, start_verz_s=0)
    assert s.schritt(e(0, netz=-50000)).p_erlaubt == P_MAX


def test_pgrid_virtuell():
    s = strat(tau_s=0, start_verz_s=0)
    a = s.schritt(e(0, p_auto=2000, netz=-3000))   # 5000 W verfuegbar
    assert pgrid_virtuell(2000, a) == -3000         # go-e soll um 3 kW erhoehen
    a2 = strat(modus=AUS).schritt(e(0, p_auto=2000))
    assert pgrid_virtuell(2000, a2) > 2000          # stoppen


def test_parameter_pruefen_und_rundreise():
    assert Parameter(stopp_w=2000, start_w=1400).pruefen()
    p = Parameter.aus_dict({"modus": "min_pv", "tau_s": "45"})
    assert p.modus == "min_pv" and p.tau_s == 45.0
    assert Parameter.aus_dict(p.als_dict()) == p


# --- Szenarien im Anlagenmodell ------------------------------------------------------------

def stunden(h, w):
    return [float(w)] * int(h * 3600)


def test_sonne_akku_voll_auto_bekommt_pv():
    erg = simulieren(stunden(2, 6000), strat(), Akku(soc=95))
    assert erg.kwh_auto > 9
    assert erg.anteil_pv > 0.97
    assert erg.starts == 1


def test_akku_unter_schwelle_laedt_zuerst():
    """4 kW Ueberschuss, Akku 60 %: erst Akku auf 90 %, dann Auto."""
    akku = Akku(soc=60, kapazitaet_kwh=7.1)
    erg = simulieren(stunden(3, 4000), strat(), akku, verlauf=True)
    erste_ladung = next(v for v in erg.verlauf if v["p_auto"] > 0)
    assert erste_ladung["soc"] >= 89.9
    assert erg.kwh["akku"] < 0.05       # Auto hat den Akku praktisch nicht entladen


def test_wolken_wenige_starts():
    profil = []
    for _ in range(30):                  # 2 h: 2 min Sonne, 2 min Wolke
        profil += [5000.0] * 120 + [400.0] * 120
    erg = simulieren(profil, strat(), Akku(soc=100))
    assert erg.starts <= 7200 / (600 + 300) + 1
    assert erg.p_erlaubt_max <= P_MAX


def test_nacht_nur_pv_laedt_nicht():
    erg = simulieren(stunden(1, -500), strat(), Akku(soc=80))
    assert erg.kwh_auto == 0


def test_watchdog_im_modell():
    ungueltig = set(range(3600, 3700))
    erg = simulieren(stunden(2, 6000), strat(), Akku(soc=100), ungueltig=ungueltig, verlauf=True)
    assert all(v["p_erlaubt"] == 0 for v in erg.verlauf[3600:3700])


# --- Aufgezeichnete Verlaeufe (dev/export_ha.py -> tests/daten/*.csv) ----------------------

CSV = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "daten", "*.csv")))


@pytest.mark.skipif(not CSV, reason="keine aufgezeichneten Verlaeufe in tests/daten/")
@pytest.mark.parametrize("pfad", CSV, ids=[os.path.basename(p) for p in CSV])
def test_aufgezeichneter_verlauf(pfad):
    ueberschuss, soc0 = ueberschuss_aus_csv(pfad)
    erg = simulieren(ueberschuss, strat(), Akku(soc=soc0 if soc0 is not None else 50))
    assert erg.p_erlaubt_max <= P_MAX
    assert erg.starts <= len(ueberschuss) / (600 + 300) + 1
    if erg.kwh_auto > 1:
        # Nur PV: Netz und Akku hoechstens durch Wolken waehrend Stopp-Verzoegerung
        assert erg.kwh["netz"] + erg.kwh["akku"] <= 0.25 * erg.kwh_auto
