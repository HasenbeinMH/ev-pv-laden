"""Morgentau-Korrektur: Einstufung der Nacht und Abschwaechung der ersten Sonnenstunden."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import morgentau as mt
import pvmodell as pm

TZ = ZoneInfo("Europe/Berlin")
LAT, LON = 51.0, 7.0


def n(spreizung=1.0, wolken=20, wind=5, regen=0.0):
    return {"spreizung": spreizung, "wolken": wolken, "wind": wind, "regen": regen}


def test_klassen():
    assert mt.klasse(n()) == mt.WAHRSCHEINLICH
    assert mt.klasse(n(spreizung=2.5, wolken=60)) == mt.MOEGLICH
    assert mt.klasse(n(spreizung=5)) == mt.TROCKEN
    assert mt.klasse(n(regen=1.0)) == mt.NASS
    assert mt.klasse(None) is None


def wetter_nacht(tag_utc: datetime, temp, taupunkt, wolken=10, wind=4):
    """Konstantes Nachtwetter von 18 Uhr Vortag bis 12 Uhr UTC."""
    aus, t = {}, tag_utc - timedelta(hours=6)
    while t < tag_utc + timedelta(hours=12):
        aus[t] = {"temperature_2m": temp, "dew_point_2m": taupunkt, "cloud_cover": wolken,
                  "wind_speed_10m": wind, "precipitation": 0.0}
        t += timedelta(hours=1)
    return aus


def tageswerte(tag_utc):
    return [(tag_utc + timedelta(hours=h), 1.0) for h in range(24)]


def sonnenstunden(tag_utc):
    return [t for t, _ in tageswerte(tag_utc) if pm.bin_von(t, LAT, LON, t.astimezone(TZ).month)[0]]


def test_winter_tau_schwaecht_die_ersten_vier_sonnenstunden():
    tag = datetime(2026, 10, 8, tzinfo=timezone.utc)
    neu, tage = mt.korrigieren(tageswerte(tag), wetter_nacht(tag, 8.0, 7.5), LAT, LON, TZ)
    sonne = sonnenstunden(tag)
    werte = dict(neu)
    assert [werte[t] for t in sonne[:4]] == [0.7] * 4
    assert all(werte[t] == 1.0 for t in sonne[4:])
    info = tage[tag.date()]
    assert info["klasse"] == mt.WAHRSCHEINLICH and info["faktor"] == 0.7
    assert info["morgen_ohne_kwh"] == 4.0 and info["morgen_mit_kwh"] == 2.8
    assert "×0,7" in mt.text(tag.date(), info)


def test_trocken_und_sommer_unveraendert():
    tag = datetime(2026, 10, 8, tzinfo=timezone.utc)
    neu, tage = mt.korrigieren(tageswerte(tag), wetter_nacht(tag, 12.0, 4.0), LAT, LON, TZ)
    assert tage[tag.date()]["klasse"] == mt.TROCKEN and all(v == 1.0 for _, v in neu)
    sommer = datetime(2026, 7, 8, tzinfo=timezone.utc)
    neu, tage = mt.korrigieren(tageswerte(sommer), wetter_nacht(sommer, 8.0, 7.5), LAT, LON, TZ)
    assert tage[sommer.date()]["klasse"] == mt.WAHRSCHEINLICH and tage[sommer.date()]["faktor"] == 1.0
    assert all(v == 1.0 for _, v in neu)


def test_ohne_wetter_keine_korrektur():
    tag = datetime(2026, 10, 8, tzinfo=timezone.utc)
    neu, tage = mt.korrigieren(tageswerte(tag), {}, LAT, LON, TZ)
    assert all(v == 1.0 for _, v in neu) and tage[tag.date()]["klasse"] is None
