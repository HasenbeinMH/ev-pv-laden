"""Integration „EV PV-Laden Prognose“: Rechenlogik (ohne Home Assistant) und Add-on-Schnittstelle."""
import importlib.util
import os
import py_compile
from datetime import datetime, timedelta, timezone

import pytest

ORDNER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "custom_components", "ev_pv_laden_prognose")
_spec = importlib.util.spec_from_file_location("rechnen", os.path.join(ORDNER, "rechnen.py"))
rechnen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rechnen)

TZ = timezone(timedelta(hours=2))


def h(tag, stunde):
    return datetime(2026, 10, tag, stunde, tzinfo=TZ)


# Stundenwerte: Zeitstempel = ENDE der Stunde
WERTE = {h(6, 11): 1000.0, h(6, 12): 2000.0, h(6, 13): 3000.0, h(7, 12): 500.0}


def test_einlesen():
    w = rechnen.einlesen({"2026-10-06T12:00:00+02:00": 2000, "kaputt": 1, "2026-10-06T11:00:00+02:00": None})
    assert list(w.values()) == [0.0, 2000.0]


def test_kennzahlen():
    k = rechnen.kennzahlen(WERTE, h(6, 11) + timedelta(minutes=30))     # 11:30
    assert k["heute"] == 6.0 and k["morgen"] == 0.5
    assert k["aktuelle_stunde"] == 2.0                                    # 11–12 Uhr
    assert k["naechste_stunde"] == 3.0                                   # 12–13 Uhr
    assert k["rest_heute"] == 4.0                                        # halbe 11–12 + 12–13
    assert k["naechste_3h"] == 4.0                                       # 11:30–14:30


def test_kennzahlen_ohne_daten():
    assert set(rechnen.kennzahlen({}, h(6, 12)).values()) == {None}


def test_alle_dateien_syntaktisch_gueltig():
    for datei in os.listdir(ORDNER):
        if datei.endswith(".py"):
            py_compile.compile(os.path.join(ORDNER, datei), doraise=True)


def test_manifest_und_uebersetzungen():
    import json
    m = json.load(open(os.path.join(ORDNER, "manifest.json"), encoding="utf-8"))
    assert m["domain"] == "ev_pv_laden_prognose" and m["config_flow"] is True and "version" in m
    for datei in ("strings.json", "translations/de.json", "translations/en.json"):
        d = json.load(open(os.path.join(ORDNER, datei), encoding="utf-8"))
        assert {"cannot_connect", "addon_zu_alt"} <= set(d["config"]["error"])


def test_markenbilder():
    from PIL import Image
    groessen = {"icon.png": (256, 256), "icon@2x.png": (512, 512), "logo.png": (320, 128), "logo@2x.png": (640, 256)}
    for datei, groesse in groessen.items():
        assert Image.open(os.path.join(ORDNER, "brand", datei)).size == groesse


# --- Add-on: Schnittstelle /api/prognose/stunden ----------------------------------------------

def test_addon_schnittstelle():
    from fastapi.testclient import TestClient
    from laufzeit import Laufzeit
    from webapp.app import app

    lz = Laufzeit()
    lz.prognose_eigen.setzen({"eigenes_modell": {"wh_hours": {"2026-10-06T12:00:00+02:00": 2000}}}, h(6, 10))
    app.state.lz = lz
    d = TestClient(app).get("/api/prognose/stunden").json()
    assert d["verfuegbar"] and d["wh_hours"] == {"2026-10-06T12:00:00+02:00": 2000}


def test_eigene_prognose_wird_herausgerechnet():
    import asyncio
    from laufzeit import Laufzeit

    class HA:
        async def anfrage(self, befehl, timeout=None):
            assert befehl == {"type": "config_entries/get", "domain": "ev_pv_laden_prognose"}
            return [{"entry_id": "eigen", "domain": "ev_pv_laden_prognose"}]

    lz = Laufzeit()
    lz.ha = HA()
    antwort = {"eigen": {"wh_hours": {}}, "forecast_solar_1": {"wh_hours": {}}}
    assert list(asyncio.run(lz._ohne_eigene_prognose(antwort))) == ["forecast_solar_1"]
