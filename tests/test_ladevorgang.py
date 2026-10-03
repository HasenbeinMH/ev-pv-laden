from datetime import datetime, timedelta

from ladevorgang import ENDE_S, START_S, Erkennung, Stand

T0 = datetime(2026, 10, 3, 12, 0, 0)


def lauf(e, start, sekunden, p, steckt=True, stand_fn=lambda t: Stand()):
    alle = []
    for s in range(0, sekunden, 5):
        t = start + timedelta(seconds=s)
        alle += e.schritt(t, p, steckt, stand_fn(t))
    return alle


def test_start_erst_nach_einer_minute_mit_zeit_der_ersten_ueberschreitung():
    e = Erkennung()
    assert lauf(e, T0, int(START_S) - 5, 3000) == []
    ev = e.schritt(T0 + timedelta(seconds=START_S), 3000, True, Stand())
    assert ev[0].art == "start" and ev[0].vorgang.start == T0


def test_kurze_spitze_startet_nichts():
    e = Erkennung()
    lauf(e, T0, 30, 3000)
    lauf(e, T0 + timedelta(seconds=30), 60, 0)
    assert e.offen is None


def test_pause_unter_15_min_bleibt_eine_ladung():
    e = Erkennung()
    lauf(e, T0, 120, 3000)
    ev = lauf(e, T0 + timedelta(seconds=120), int(ENDE_S) - 60, 0)
    assert ev == [] and e.offen is not None


def test_ende_nach_15_min_ohne_leistung_mit_energie():
    e = Erkennung()
    stand = lambda t: Stand(pv=(t - T0).total_seconds() / 3600 * 4, eto=(t - T0).total_seconds() / 3600 * 4)
    lauf(e, T0, 3600, 4000, stand_fn=stand)
    ende_leistung = T0 + timedelta(seconds=3595)
    ev = lauf(e, T0 + timedelta(seconds=3600), int(ENDE_S) + 10, 0,
              stand_fn=lambda t: stand(T0 + timedelta(seconds=3600)))
    assert ev[0].art == "ende" and ev[0].grund == "keine Leistung"
    assert ev[0].ende == ende_leistung
    assert abs(ev[0].energie.pv - 4.0) < 0.01


def test_abstecken_beendet_sofort():
    e = Erkennung()
    lauf(e, T0, 120, 3000)
    ev = e.schritt(T0 + timedelta(seconds=125), 0, False, Stand())
    assert ev[0].art == "ende" and ev[0].grund == "abgesteckt"


def test_monatswechsel_teilt():
    e = Erkennung()
    spaet = datetime(2026, 10, 31, 23, 50)
    lauf(e, spaet, 120, 3000, stand_fn=lambda t: Stand(netz=1.0))
    ev = e.schritt(datetime(2026, 11, 1, 0, 0, 5), 3000, True, Stand(netz=1.5))
    assert [x.art for x in ev] == ["ende", "start"]
    assert ev[0].ende == datetime(2026, 11, 1)
    assert ev[1].vorgang.start == datetime(2026, 11, 1)
    assert abs(ev[0].energie.netz - 0.5) < 1e-9


def test_unbekannte_leistung_ist_keine_pause():
    e = Erkennung()
    lauf(e, T0, 50, 3000)
    e.schritt(T0 + timedelta(seconds=55), None, True, Stand())
    ev = e.schritt(T0 + timedelta(seconds=65), 3000, True, Stand())
    assert ev and ev[0].art == "start"
