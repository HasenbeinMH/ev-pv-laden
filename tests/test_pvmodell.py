"""PV-Modell: Sonnenstand, Kennfeld, Sauberkeit – mit einer kuenstlichen Anlage, deren
Verschattung (morgens) und Verschmutzung (Woche fuer Woche) vorgegeben sind."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

import pvdaten
import pvmodell as pm

TZ = ZoneInfo("Europe/Berlin")
LAT, LON = 51.0, 7.0   # neutraler Beispielstandort
FL = [pm.Flaeche("sued", 30, 180, 5.0)]


def test_sonnenstand_mittag_sommer():
    # Sonnenmittag bei 7 Grad Ost am 21.06. etwa 11:32 UTC; Hoehe ~ 90 - 51 + 23,44
    el, az = pm.sonnenstand(datetime(2026, 6, 21, 11, 32, tzinfo=timezone.utc), LAT, LON)
    assert el == pytest.approx(62.4, abs=0.6)
    assert az == pytest.approx(180, abs=3)


def test_sonnenstand_morgens_osten_nachts_negativ():
    el, az = pm.sonnenstand(datetime(2026, 6, 21, 5, 0, tzinfo=timezone.utc), LAT, LON)
    assert 0 < el < 25 and 50 < az < 100
    el, _ = pm.sonnenstand(datetime(2026, 12, 21, 23, 0, tzinfo=timezone.utc), LAT, LON)
    assert el < 0


@pytest.mark.parametrize("az,om", [(180, 0), (90, -90), (270, 90), (0, 180)])   # +-180 = Nord
def test_open_meteo_azimut(az, om):
    assert pm.Flaeche("x", 10, az, 1).om_azimut == om


def kuenstliche_anlage(tage=730, schmutz=lambda tag: 1.0):
    """Klarer Himmel (GTI ~ sin(Sonnenhoehe)), morgens bis Azimut 150 verschattet (40 %),
    sonst 90 % Wirkungsgrad, dazu die vorgegebene Verschmutzung."""
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    mess, gti = {}, {}
    for h in range(tage * 24):
        t = start + timedelta(hours=h)
        el, az = pm.sonnenstand(t + timedelta(minutes=30), LAT, LON)
        if el <= 0:
            continue
        g = 900 * max(el, 0) / 90 + 50
        gti[t] = {"sued": g}
        k = 0.4 if az < 150 else 0.9
        mess[t] = pm.phys_kwh(gti[t], FL) * k * schmutz((t - start).days)
    return mess, gti


def test_kennfeld_findet_verschattung():
    mess, gti = kuenstliche_anlage(tage=400)
    m = pm.trainieren(mess, gti, gti, FL, LAT, LON, TZ)
    morgens = [v for b, v in m.k_prognose.items() if int(b.split("_")[1]) < 135]
    mittags = [v for b, v in m.k_prognose.items() if 165 <= int(b.split("_")[1]) <= 195]
    assert sum(morgens) / len(morgens) == pytest.approx(0.4, abs=0.03)
    assert sum(mittags) / len(mittags) == pytest.approx(0.9, abs=0.03)


def test_sauberkeit_folgt_schmutz_und_reinigung():
    # 300 Tage langsam schmutziger bis 0,7, dann gereinigt -> 1,0
    schmutz = lambda tag: 1.0 - 0.3 * (tag % 300) / 300   # noqa: E731
    mess, gti = kuenstliche_anlage(tage=600, schmutz=schmutz)
    m = pm.trainieren(mess, gti, gti, FL, LAT, LON, TZ)
    wochen = m.sauberkeit_wochen
    assert max(wochen.values()) == pytest.approx(1.0, abs=0.05)
    assert min(wochen.values()) < 0.8
    # laufende Schaetzung: 14 Tage kurz vor der Reinigung (Tag ~290) -> ca. 0,7 relativ zu sauber
    start = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=276)
    fenster = {t: v for t, v in mess.items() if start <= t < start + timedelta(days=14)}
    wert, _ = pm.sauberkeit_schaetzen(m, fenster, gti, FL, LAT, LON, TZ)
    assert wert is not None and wert < 0.85


def test_zuschlag_nur_nach_reinigung_und_befristet():
    m = pm.Modell(k_prognose={"x": 1}, sauberkeit=1.0, sauberkeit_mittel=0.8)
    assert m.zuschlag(date(2026, 10, 4)) == 1.0          # nie gereinigt
    m.gereinigt_am = "2026-10-01"
    assert m.zuschlag(date(2026, 10, 4)) == pytest.approx(1.25)
    assert m.zuschlag(date(2027, 3, 1)) == 1.0           # nach 90 Tagen vorbei


def test_prognose_nachts_null_und_modell_rundreise():
    mess, gti = kuenstliche_anlage(tage=400)
    m = pm.Modell.aus_dict(pm.trainieren(mess, gti, gti, FL, LAT, LON, TZ).als_dict())
    nacht = datetime(2024, 6, 1, 0, 0, tzinfo=timezone.utc)
    mittag = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)   # Azimut sicher > 150 (unverschattet)
    werte = dict(m.prognose([(nacht, {"sued": 0}), (mittag, gti[mittag])], FL, LAT, LON, TZ))
    assert werte[nacht] == 0
    assert werte[mittag] == pytest.approx(mess[mittag], rel=0.05)


def test_zu_wenig_daten():
    mess, gti = kuenstliche_anlage(tage=10)
    with pytest.raises(ValueError, match="zu wenig"):
        pm.trainieren(mess, gti, gti, FL, LAT, LON, TZ)


# ── pvdaten: reine Umrechnungen ──────────────────────────────────────────────────

def test_open_meteo_zeit_auf_stundenbeginn():
    ziel = {}
    pvdaten.gti_eintragen({"hourly": {"time": ["2026-06-01T12:00"], "global_tilted_irradiance": [500]}},
                          "sued", ziel)
    assert ziel == {datetime(2026, 6, 1, 11, tzinfo=timezone.utc): {"sued": 500.0}}


def test_pv_aus_statistik_solaredge():
    t0 = int(datetime(2026, 10, 3, 10, tzinfo=timezone.utc).timestamp() * 1000)
    t1 = t0 + 3600_000
    ids = {"dc": "sensor.dc", "geladen": "sensor.g", "entladen": "sensor.e"}
    erg = {"sensor.dc": [{"start": t0, "mean": 376.0}, {"start": t1, "mean": 900.0}],
           "sensor.g": [{"start": t0, "change": 2.127}],              # t1 fehlt = keine Ladung
           "sensor.e": [{"start": t0, "change": 0.001}, {"start": t1, "change": 1.0}]}
    pv = pvdaten.pv_aus_statistik(erg, ids)
    assert pv[datetime(2026, 10, 3, 10, tzinfo=timezone.utc)] == pytest.approx(2.502)
    assert pv[datetime(2026, 10, 3, 11, tzinfo=timezone.utc)] == 0.0   # abends: nur Akku


def test_pv_aus_energiezaehler():
    t0 = int(datetime(2026, 10, 3, 10, tzinfo=timezone.utc).timestamp() * 1000)
    pv = pvdaten.pv_aus_statistik({"sensor.pv": [{"start": t0, "change": 2.4}]}, {"energie": "sensor.pv"})
    assert list(pv.values()) == [2.4]
