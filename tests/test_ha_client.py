import asyncio

import pytest

from ha_client import HAClient, SchreibschutzAktiv, Verbindungsdaten, zustand_anwenden


def test_erstbestand_und_aenderung():
    b = {}
    zustand_anwenden(b, {"a": {"sensor.x": {"s": "5", "a": {"unit_of_measurement": "W"}, "lc": 1.0}}})
    assert b["sensor.x"]["s"] == "5" and b["sensor.x"]["lu"] == 1.0

    zustand_anwenden(b, {"c": {"sensor.x": {"+": {"s": "7", "lc": 2.0}}}})
    assert b["sensor.x"]["s"] == "7"
    assert b["sensor.x"]["a"]["unit_of_measurement"] == "W"   # Attribute bleiben erhalten
    assert b["sensor.x"]["lu"] == 2.0


def test_nur_attribut_geaendert_und_entfernt():
    b = {"sensor.x": {"s": "1", "a": {"unit_of_measurement": "W", "foo": 1}, "lc": 1.0, "lu": 1.0}}
    zustand_anwenden(b, {"c": {"sensor.x": {"+": {"a": {"unit_of_measurement": "kW"}, "lu": 3.0},
                                            "-": {"a": ["foo"]}}}})
    assert b["sensor.x"]["a"] == {"unit_of_measurement": "kW"}
    assert b["sensor.x"]["lc"] == 1.0 and b["sensor.x"]["lu"] == 3.0


def test_entfernt():
    b = {"sensor.x": {"s": "1", "a": {}, "lc": 1, "lu": 1}}
    assert zustand_anwenden(b, {"r": ["sensor.x"]}) == ["sensor.x"]
    assert b == {}


def test_dienstaufruf_im_trockenlauf_gesperrt():
    c = HAClient(Verbindungsdaten("ws://x", "t"), [], lambda *a: None)
    assert c.schreiben_gesperrt is True   # Grundzustand: gesperrt
    with pytest.raises(SchreibschutzAktiv):
        asyncio.run(c.dienst_aufrufen("goecharger_api2", "set_pv_data", {"pgrid": 0}))
