import json

import pytest

import konfig
from konfig import Konfig, KonfigFehler, laden


def schreiben(tmp_path, daten):
    p = tmp_path / "options.json"
    p.write_text(json.dumps(daten), encoding="utf-8")
    return str(p)


GUELTIG = {"goe_seriennummer": "325656"}


def test_standardwerte_mit_seriennummer(tmp_path):
    k = laden(schreiben(tmp_path, GUELTIG))
    assert k.trockenlauf is True
    assert k.max_strom_a == 24
    assert k.goe_praefix == "goe_325656"


def test_datei_fehlt(tmp_path):
    with pytest.raises(KonfigFehler, match="nicht gefunden"):
        laden(str(tmp_path / "gibtsnicht.json"))


def test_kaputtes_json(tmp_path):
    p = tmp_path / "options.json"
    p.write_text("{kaputt", encoding="utf-8")
    with pytest.raises(KonfigFehler, match="nicht lesbar"):
        laden(str(p))


@pytest.mark.parametrize("feld,wert", [
    ("max_strom_a", 25),         # ueber Zuleitung
    ("max_strom_a", 32),
    ("max_strom_1ph_a", 21),     # ueber Schieflastgrenze
    ("min_strom_a", 5),          # unter IEC 61851
    ("ev_max_strom_1ph_a", 4),
])
def test_harte_grenzen_auch_ohne_schema(tmp_path, feld, wert):
    with pytest.raises(KonfigFehler):
        laden(schreiben(tmp_path, {**GUELTIG, feld: wert}))


def test_min_groesser_max(tmp_path):
    with pytest.raises(KonfigFehler, match="min_strom_a"):
        laden(schreiben(tmp_path, {**GUELTIG, "max_strom_a": 10, "min_strom_a": 12}))


def test_typfehler_werden_gesammelt(tmp_path):
    with pytest.raises(KonfigFehler) as e:
        laden(schreiben(tmp_path, {**GUELTIG, "trockenlauf": "ja", "max_strom_a": "24"}))
    assert len(e.value.fehler) == 2


def test_bool_ist_keine_zahl(tmp_path):
    with pytest.raises(KonfigFehler):
        laden(schreiben(tmp_path, {**GUELTIG, "max_strom_a": True}))


def test_ungueltige_entity(tmp_path):
    with pytest.raises(KonfigFehler, match="sensor_netz"):
        laden(schreiben(tmp_path, {**GUELTIG, "sensor_netz": "Sensor.Netz"}))


def test_leere_optionale_sensoren_erlaubt(tmp_path):
    k = laden(schreiben(tmp_path, {**GUELTIG, "sensor_pv": "", "sensor_akku_leistung": ""}))
    assert k.sensor_pv == ""


def test_unbekannte_schluessel_ignoriert(tmp_path):
    k = laden(schreiben(tmp_path, {**GUELTIG, "gibt_es_nicht": 1}))
    assert k.max_strom_a == 24


def test_strom_1ph_ist_kleinster_der_drei():
    assert Konfig(goe_seriennummer="1", ev_max_strom_1ph_a=16).strom_1ph_max_a == 16
    assert Konfig(goe_seriennummer="1", ev_max_strom_1ph_a=32).strom_1ph_max_a == 20
    assert Konfig(goe_seriennummer="1", ev_max_strom_1ph_a=32, max_strom_a=10).strom_1ph_max_a == 10


def test_token_nie_im_klartext():
    k = Konfig(goe_seriennummer="1", ev_tracker_token="geheim")
    assert k.ohne_geheimnisse()["ev_tracker_token"] == "***"


def test_konstanten_passen_zu_config_yaml():
    """Schema in config.yaml und Konstanten im Code duerfen nicht auseinanderlaufen."""
    import os
    import re
    pfad = os.path.join(os.path.dirname(konfig.__file__), "config.yaml")
    text = open(pfad, encoding="utf-8").read()
    assert re.search(rf"max_strom_a: int\(6,{konfig.GRENZE_STROM_A}\)", text)
    assert re.search(rf"max_strom_1ph_a: int\(6,{konfig.GRENZE_STROM_1PH_A}\)", text)
