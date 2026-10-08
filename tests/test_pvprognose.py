"""PVPrognose (Laufzeit): Training, Sauberkeit, Prognose, "gereinigt" – HA und Open-Meteo
nachgebildet (pvdaten.pv_messung / gti_holen ersetzt)."""
import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

import datenbank as db
import pvdaten
import pvmodell as pm
from konfig import Konfig
from prognose import Prognose
from pvprognose import PVPrognose

TZ = ZoneInfo("Europe/Berlin")
K = Konfig(goe_seriennummer="1", pv_flaechen=[{"name": "sued", "neigung": 30, "azimut": 180, "kwp": 5}])


class HA:
    verbunden, standort, zeitzone = True, (51.0, 7.0), "Europe/Berlin"


def gti_fuer(start: datetime, ende: datetime) -> dict:
    aus, t = {}, start.replace(minute=0, second=0, microsecond=0)
    while t < ende:
        el, _ = pm.sonnenstand(t + timedelta(minutes=30), 51.0, 7.0)
        aus[t] = {"sued": 900 * max(el, 0) / 90 + (50 if el > 0 else 0)}
        t += timedelta(hours=1)
    return aus


@pytest.fixture
def umgebung(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_DATEI", str(tmp_path / "p.db"))
    db.initialisieren()

    async def pv_messung(ha, k, start, ende):
        # Anlage: 85 % Wirkungsgrad; wird ueber 200 Tage um 30 % schmutziger, dann gereinigt
        g = gti_fuer(max(start, datetime.now(timezone.utc) - timedelta(days=500)), ende)
        fl = pvdaten.flaechen_aus_konfig(k.pv_flaechen)

        def schmutz(t):
            return 1.0 - 0.3 * ((t - datetime(2024, 1, 1, tzinfo=timezone.utc)).days % 200) / 200
        return {t: pm.phys_kwh(v, fl) * 0.85 * schmutz(t) for t, v in g.items()}

    async def gti_holen(sitzung, url, lat, lon, flaechen, zeitraum, modelle=()):
        if "start_date" in zeitraum:
            s = datetime.fromisoformat(zeitraum["start_date"]).replace(tzinfo=timezone.utc)
            e = datetime.fromisoformat(zeitraum["end_date"]).replace(tzinfo=timezone.utc) + timedelta(days=1)
        else:
            s = datetime.now(timezone.utc) - timedelta(days=1)
            e = s + timedelta(days=4)
        return gti_fuer(s, e)

    async def wetter_holen(sitzung, lat, lon, zeitraum):
        return {}                                   # kein Nachtwetter -> keine Tau-Korrektur

    monkeypatch.setattr(pvdaten, "wetter_holen", wetter_holen)
    monkeypatch.setattr(pvdaten, "pv_messung", pv_messung)
    monkeypatch.setattr(pvdaten, "gti_holen", gti_holen)


def test_ablauf_training_prognose_gereinigt(umgebung):
    ziel = Prognose()
    pv = PVPrognose(K, ziel)
    asyncio.run(pv._schritt(HA(), None))
    assert pv.modell.trainiert and pv.zustand == "aktiv" and pv.fehler is None
    assert ziel.werte, "Prognose gesetzt"
    jetzt = datetime.now(TZ)
    u = ziel.uebersicht(jetzt)
    assert u["morgen_kwh"] > 0

    # gespeichert: neue Instanz laedt das trainierte Modell
    assert PVPrognose(K, Prognose()).modell.trainiert

    # gereinigt -> Zuschlag > 1, Prognose steigt
    morgen_vorher = u["morgen_kwh"]
    pv.gereinigt(jetzt.date())
    asyncio.run(pv.prognose_aktualisieren(HA(), None, TZ))
    assert pv.status(jetzt.date())["zuschlag"] > 1.0
    assert ziel.uebersicht(jetzt)["morgen_kwh"] > morgen_vorher
    assert any(e["quelle"] == "pvmodell" for e in db.ereignisse(10))


def test_ohne_flaechen_inaktiv(umgebung):
    pv = PVPrognose(Konfig(goe_seriennummer="1"), Prognose())
    asyncio.run(pv.laufen(HA()))
    assert pv.zustand == "keine Dachflaechen konfiguriert"


def test_wettermodell_wechsel_trainiert_neu(umgebung):
    ziel = Prognose()
    pv = PVPrognose(K, ziel)
    asyncio.run(pv._schritt(HA(), None))
    assert pv.modell.wettermodell == "ecmwf_icon"           # Standard der Option
    from dataclasses import replace
    pv.konfig = replace(K, wettermodell="icon")
    pv._zuletzt_training_versuch = float("-inf")
    asyncio.run(pv._schritt(HA(), None))
    assert pv.modell.wettermodell == "icon"


def test_mehrere_modelle_werden_gemittelt(monkeypatch):
    import pvdaten as pd

    class Antwort:
        def __init__(self, wert):
            self.status, self.wert = 200, wert

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def json(self, content_type=None):
            return {"hourly": {"time": ["2026-10-08T12:00"], "global_tilted_irradiance": [self.wert]}}

    class Sitzung:
        def get(self, url, params, timeout):
            return Antwort(400.0 if params.get("models") == "ecmwf_ifs025" else 600.0)

    fl = pd.flaechen_aus_konfig([{"name": "sued", "neigung": 30, "azimut": 180, "kwp": 5}])
    werte = asyncio.run(pd.gti_holen(Sitzung(), pd.PROGNOSE, 51.0, 7.0, fl, {}, ("ecmwf_ifs025", "icon_seamless")))
    assert list(werte.values()) == [{"sued": 500.0}]
