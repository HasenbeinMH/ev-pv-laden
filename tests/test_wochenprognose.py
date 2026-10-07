"""7-Tage-Vorschau: Ueberschuss nach Hausverbrauch und Hausakku, Rest fuers Auto (wie Min + PV)."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import wochenprognose as wp

TZ = ZoneInfo("Europe/Berlin")


def tag(pv_je_stunde: dict[int, float], d=date(2026, 10, 8)):
    """{Uhrzeit lokal: PV kWh} -> Werte (Stundenbeginn UTC, kWh) fuer einen Tag."""
    return [(datetime(d.year, d.month, d.day, h, tzinfo=TZ).astimezone(timezone.utc), pv_je_stunde.get(h, 0.0))
            for h in range(24)]


def test_profil_mittelt_je_uhrzeit():
    t0 = datetime(2026, 10, 1, 10, tzinfo=TZ).astimezone(timezone.utc)
    p = wp.haus_profil({t0: 400.0, t0 + timedelta(days=1): 600.0, t0 + timedelta(hours=1): 1000.0}, TZ)
    assert p == {10: 0.5, 11: 1.0}


def test_akku_zuerst_dann_jeder_rest_fuers_auto():
    profil = {h: 0.5 for h in range(24)}
    # 10-14 Uhr je 3 kWh PV -> je 2,5 kWh Ueberschuss; Akku braucht 4 kWh
    w = wp.berechnen(tag({h: 3.0 for h in range(10, 15)}), profil, 4.0, TZ, date(2026, 10, 8))
    t = w[0]
    assert t["pv_kwh"] == 15.0 and t["akku_kwh"] == 4.0
    # 10 Uhr: 2,5 in den Akku; 11 Uhr: 1,5 Akku + 1,0 Auto; 12-14 Uhr: 3 x 2,5 Auto
    assert t["auto_kwh"] == 8.5 and t["bewertung"] == wp.LOHNT


def test_bewertung_und_zeitraum():
    assert wp.bewertung(0.9) == wp.KAUM and wp.bewertung(1.0) == wp.MAESSIG and wp.bewertung(3.0) == wp.LOHNT
    werte = tag({12: 2.0}) + tag({12: 2.0}, date(2026, 10, 20))
    w = wp.berechnen(werte, {}, 0.0, TZ, date(2026, 10, 8))
    assert [t["datum"] for t in w] == ["2026-10-08"]          # nur 7 Tage ab heute
    assert w[0]["auto_kwh"] == 1.5                             # ohne Profil 0,5 kW Haus angenommen
