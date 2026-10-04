"""Treiberwahl und Wiederanlauf im Zusammenspiel (Laufzeit ohne HA, nur die Logik)."""
import asyncio

import pytest

import datenbank as db
from konfig import Konfig
from laufzeit import Laufzeit
from prozessabbild import Prozessabbild
from regelung import Regelung
from strategie import Ausgang
from treiber import TreiberA, TreiberIds

K = Konfig(goe_seriennummer="325656")
FREI = Ausgang(True, 3000.0, 3000.0, 3000.0, "laedt", "test")


@pytest.fixture
def lz(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_DATEI", str(tmp_path / "t.db"))
    db.initialisieren()
    l = Laufzeit()
    l.konfig = K
    l.regelung = Regelung(K, Prozessabbild(K))
    l._treiber_setzen(l.regelung.param.treiber)
    return l


def test_wechsel_nur_ohne_ladung(lz):
    assert isinstance(lz.treiber, TreiberIds) and lz.regelung.p_min == 6 * 230
    lz.regelung.parameter_setzen({"treiber": "a"})
    assert lz._treiber_waehlen({"auto_w": 3000.0}) is False         # laedt gerade
    assert lz._treiber_waehlen({"auto_w": 0.0}) is True
    assert isinstance(lz.treiber, TreiberA) and lz.regelung.p_min == 3 * 6 * 230
    assert lz.regelung.treiber == "A (Trockenlauf)"


def test_wiederanlauf_eskaliert_auf_a_bis_abstecken(lz):
    w = {"auto_steckt": True, "auto_w": 0.0, "auto_status": "Inaktiv/Frei"}
    warte = lz.regelung.param.wiederanlauf_s
    lz._wiederanlauf(0.0, FREI, w)
    fup = lz._wiederanlauf(warte, FREI, w)
    assert [a.text for a in fup] == ["fup=aus (Wiederanlauf: kurz umschalten)"]
    lz._wiederanlauf(2 * warte, FREI, w)
    assert lz._wiederanlauf(3 * warte, FREI, w) == [] and lz.ausweich_a
    lz._treiber_waehlen(w)
    assert isinstance(lz.treiber, TreiberA) and "Ausweich" in lz.regelung.treiber
    # Treiber A: keine Wiederanlauf-Massnahmen mehr
    assert lz._wiederanlauf(10 * warte, FREI, w) == []
    lz._treiber_waehlen(dict(w, auto_steckt=False))
    assert isinstance(lz.treiber, TreiberIds) and not lz.ausweich_a


def test_sicherer_halt_im_trockenlauf_schreibt_nicht(lz):
    lz.regelung.parameter_setzen({"treiber": "a"})
    lz._treiber_waehlen({})
    asyncio.run(lz._sicherer_halt())        # ha is None, Trockenlauf: nur Protokoll
