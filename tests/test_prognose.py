from datetime import datetime
from zoneinfo import ZoneInfo

from prognose import Prognose, zusammenfassen

TZ = ZoneInfo("Europe/Berlin")


def antwort():
    # zwei Dachflaechen, Wh je Stunde (Zeitstempel = Ende der Stunde)
    return {
        "a": {"wh_hours": {"2026-10-04T11:00:00+02:00": 1000, "2026-10-04T12:00:00+02:00": 2000,
                           "2026-10-05T12:00:00+02:00": 500}},
        "b": {"wh_hours": {"2026-10-04T12:00:00+02:00": 1000}},
    }


def test_summe_ueber_dachflaechen():
    z = zusammenfassen(antwort())
    assert z[datetime(2026, 10, 4, 12, tzinfo=TZ)] == 3000


def test_heute_rest_morgen_anteilig():
    p = Prognose()
    jetzt = datetime(2026, 10, 4, 11, 30, tzinfo=TZ)
    p.setzen(antwort(), jetzt)
    u = p.uebersicht(jetzt)
    assert u["heute_kwh"] == 4.0
    assert u["heute_rest_kwh"] == 1.5      # halbe Stunde 11-12 Uhr von 3000 Wh
    assert u["morgen_kwh"] == 0.5
    assert u["verfuegbar"] and u["fehler"] is None


def test_nicht_zugeordnet():
    p = Prognose()
    p.setzen({}, datetime(2026, 10, 4, 12, tzinfo=TZ))
    u = p.uebersicht(datetime(2026, 10, 4, 12, tzinfo=TZ))
    assert not u["verfuegbar"] and "Energie-Dashboard" in u["fehler"]
