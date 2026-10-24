"""M8: Bedienung aus HA (MQTT-Befehle), Trockenlauf in zwei Stufen, Meldungen."""
import asyncio

import pytest

import datenbank as db
import mqtt_ha
from erfassung import Erfassung
from konfig import Konfig
from laufzeit import Laufzeit
from meldungen import FertigErkennung
from prozessabbild import Prozessabbild
from regelung import Regelung
from strategie import Ausgang


def baue(tmp_path, monkeypatch, **konfig):
    monkeypatch.setattr(db, "DB_DATEI", str(tmp_path / "t.db"))
    db.initialisieren()
    k = Konfig(goe_seriennummer="325656", **konfig)
    l = Laufzeit()
    l.konfig = k
    l.abbild = Prozessabbild(k)
    l.erfassung = Erfassung(k, l.abbild)
    l.regelung = Regelung(k, l.abbild)
    l._treiber_setzen("ids")
    return l


# --- Befehle übersetzen ----------------------------------------------------------------------

def test_befehle_uebersetzen():
    u = mqtt_ha.befehl_uebersetzen
    assert u("lademodus", "Nur PV") == ("modus", "nur_pv")
    assert u("lademodus", "zielzeit") == ("modus", "zielzeit")
    assert u("treiber_wahl", "A (Add-on stellt Strom)") == ("treiber", "a")
    assert u("trockenlauf", "OFF") == ("trockenlauf", False)
    assert u("ziel_soc", "85") == ("ziel_soc", 85.0)
    assert u("abfahrt", "06:30") == ("abfahrt", "06:30")
    for schluessel, text in (("lademodus", "Turbo"), ("trockenlauf", "an"), ("ziel_soc", "x"),
                             ("unbekannt", "1")):
        with pytest.raises(ValueError):
            u(schluessel, text)


def test_befehl_setzt_parameter_und_lehnt_ungueltiges_ab(tmp_path, monkeypatch):
    l = baue(tmp_path, monkeypatch)
    asyncio.run(l._befehl("lademodus", "Min + PV"))
    asyncio.run(l._befehl("abfahrt", "25:00"))           # ungueltig -> bleibt
    assert l.regelung.param.modus == "min_pv" and l.regelung.param.abfahrt == "07:00"
    assert any("abgelehnt" in e["text"] for e in db.ereignisse(5))
    z = l.mqtt_zustand()
    assert z["lademodus"] == "Min + PV" and z["trockenlauf"] == "ON"


# --- Trockenlauf -----------------------------------------------------------------------------

def test_option_sperrt_trockenlauf_fest(tmp_path, monkeypatch):
    l = baue(tmp_path, monkeypatch, trockenlauf=True)
    assert asyncio.run(l.trockenlauf_setzen(False))      # Fehlermeldung
    assert l.trockenlauf


def test_ohne_option_schaltbar_und_gespeichert(tmp_path, monkeypatch):
    l = baue(tmp_path, monkeypatch, trockenlauf=False)
    assert l.trockenlauf                                  # Anfangswert: an
    assert asyncio.run(l.trockenlauf_setzen(False)) == []
    assert not l.trockenlauf and l.regelung.treiber == "ids"
    assert db.einstellung("trockenlauf_bedienung") is False
    asyncio.run(l.trockenlauf_setzen(True))
    assert l.trockenlauf and l.regelung.treiber == "ids (Trockenlauf)"


# --- Meldungen -------------------------------------------------------------------------------

def test_fertig_einmal_je_ansteckvorgang():
    f = FertigErkennung()
    assert f.zyklus(True, 0.0, "Warte auf Fahrzeug", True, False) == []
    assert f.zyklus(True, 0.0, "Abgeschlossen", True, False) == []   # noch nicht geladen
    assert f.zyklus(True, 7000.0, "Laden", True, False) == []
    assert f.zyklus(True, 0.0, "Abgeschlossen", True, False) == ["fertig"]
    assert f.voll
    assert f.zyklus(True, 0.0, "Abgeschlossen", True, False) == []   # nur einmal
    f.zyklus(False, None, None, False, False)                          # abgesteckt
    assert not f.voll
    f.zyklus(True, 5000.0, "Charging", True, False)
    assert f.zyklus(True, 0.0, "Complete", True, False) == ["fertig"]


def test_stopp_ist_nicht_fertig():
    # Ablauf 24.10.2026: Laden, Stopp im Add-on (Freigabe weg), ~3 s spaeter "Abgeschlossen"
    f = FertigErkennung()
    f.zyklus(True, 10150.0, "Laden", True, False)
    f.zyklus(True, 10150.0, "Laden", False, False)                    # Stopp
    assert f.zyklus(True, 0.0, "Abgeschlossen", False, False) == []
    assert not f.voll
    # erneuter Start: Status steht schon auf "Abgeschlossen" - das ist kein Wechsel
    assert f.zyklus(True, 0.0, "Abgeschlossen", True, False) == []
    f.zyklus(True, 10150.0, "Laden", True, False)
    assert f.zyklus(True, 0.0, "Abgeschlossen", True, False) == ["fertig"]


GESPERRT = Ausgang(False, 0.0, None, None, "bereit", "Gestoppt")


def test_laden_erlaubt_bei_ladung_von_aussen(tmp_path, monkeypatch):
    l = baue(tmp_path, monkeypatch)
    assert not l._laden_erlaubt(GESPERRT, {"goe_frc": "0"})      # normal: Freigabe zaehlt
    l.regelung.extern = True                                      # Ladung ueber die go-e-App
    assert l._laden_erlaubt(GESPERRT, {"goe_frc": "0"})
    assert not l._laden_erlaubt(GESPERRT, {"goe_frc": "1"})       # in der App gestoppt
    assert not l._laden_erlaubt(GESPERRT, {"goe_frc": None})      # unbekannt: lieber nicht


def test_fertig_bei_ladung_von_aussen(tmp_path, monkeypatch):
    # Ablauf 24.10.2026: Start in der App (frc=0), Add-on gestoppt -> "von aussen"
    l = baue(tmp_path, monkeypatch)
    l.regelung.extern = True

    def zyklus(frc, auto_w, status):
        w = {"auto_steckt": True, "auto_w": auto_w, "auto_status": status, "goe_frc": frc}
        l._meldungen(w, l._laden_erlaubt(GESPERRT, w))

    zyklus("0", 13200.0, "Laden")
    zyklus("1", 13200.0, "Laden")                                 # Stopp in der App ...
    zyklus("1", 0.0, "Abgeschlossen")                             # ... ist nicht fertig
    assert not l.fertig.voll
    zyklus("0", 0.0, "Abgeschlossen")                             # Start: Status steht schon
    zyklus("0", 16300.0, "Laden")
    zyklus("0", 0.0, "Abgeschlossen")                             # Auto voll
    assert l.fertig.voll
    assert any("Auto fertig geladen" in e["text"] for e in db.ereignisse(10))


def test_ziel_erreicht_einmal():
    f = FertigErkennung()
    f.zyklus(True, 11000.0, "Laden", True, False)
    assert f.zyklus(True, 11000.0, "Laden", True, True) == ["ziel_erreicht"]
    assert f.zyklus(True, 0.0, "Laden", True, True) == []


def test_zusammenfassung_ohne_vorgang(tmp_path, monkeypatch):
    l = baue(tmp_path, monkeypatch)
    l.regelung.auto_soc_setzen(80)
    assert l._ladung_zusammenfassung() == {"soc": 80, "ziel_soc": 80.0}
