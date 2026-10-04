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
    assert f.zyklus(True, 0.0, "Ladung beendet", False) == []      # noch nicht geladen
    assert f.zyklus(True, 7000.0, "Lädt", False) == []
    assert f.zyklus(True, 0.0, "Ladung beendet", False) == ["fertig"]
    assert f.zyklus(True, 0.0, "Ladung beendet", False) == []      # nur einmal
    f.zyklus(False, None, None, False)                              # abgesteckt
    f.zyklus(True, 5000.0, "Lädt", False)
    assert f.zyklus(True, 0.0, "Complete", False) == ["fertig"]


def test_ziel_erreicht_einmal():
    f = FertigErkennung()
    f.zyklus(True, 11000.0, "Lädt", False)
    assert f.zyklus(True, 11000.0, "Lädt", True) == ["ziel_erreicht"]
    assert f.zyklus(True, 0.0, "Lädt", True) == []


def test_zusammenfassung_ohne_vorgang(tmp_path, monkeypatch):
    l = baue(tmp_path, monkeypatch)
    l.regelung.auto_soc_setzen(80)
    assert l._ladung_zusammenfassung() == {"soc": 80, "ziel_soc": 80.0}
