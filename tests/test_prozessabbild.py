from konfig import Konfig
from prozessabbild import Prozessabbild

K = Konfig(goe_seriennummer="325656", max_alter_s=15,
           sensor_lebenszeichen="sensor.se_modbus_daten_m1_ac_power")


def zst(s, einheit=None):
    return {"s": s, "a": {"unit_of_measurement": einheit} if einheit else {}}


def test_netz_invertiert_solaredge():
    """SolarEdge M1: + = Einspeisung. Intern: Bezug +. 500 W Einspeisung -> -500."""
    pa = Prozessabbild(K)
    pa.aktualisieren(K.sensor_netz, zst("500", "W"), 100.0)
    assert pa.wert("netz_w", 101.0) == -500.0


def test_akku_invertiert_und_kw():
    """SolarEdge Akku: + = Laden. 1,2 kW Laden -> intern -1200 W."""
    pa = Prozessabbild(K)
    pa.aktualisieren(K.sensor_akku_leistung, zst("1.2", "kW"), 100.0)
    assert pa.wert("akku_w", 100.0) == -1200.0


def test_unbekannte_einheit_ist_ungueltig():
    pa = Prozessabbild(K)
    pa.aktualisieren(K.sensor_netz, zst("500", "VA"), 100.0)
    assert pa.wert("netz_w", 100.0) is None


def test_unavailable_ist_ungueltig():
    pa = Prozessabbild(K)
    pa.aktualisieren(K.sensor_netz, zst("unavailable", "W"), 100.0)
    assert pa.wert("netz_w", 100.0) is None


def test_veraltet():
    pa = Prozessabbild(K)
    pa.aktualisieren(K.sensor_netz, zst("500", "W"), 100.0)
    assert pa.wert("netz_w", 115.0) is not None
    assert pa.wert("netz_w", 115.1) is None


def test_lebenszeichen_haelt_konstanten_akku_gueltig():
    """Akku 0 W kommt nur einmal; solange das Netz (Lebenszeichen) laeuft, bleibt er gueltig."""
    pa = Prozessabbild(K)
    pa.aktualisieren(K.sensor_akku_leistung, zst("0", "W"), 100.0)
    pa.aktualisieren(K.sensor_netz, zst("10", "W"), 200.0)   # gleiche Entity wie Lebenszeichen
    assert pa.wert("akku_w", 201.0) == 0.0
    assert pa.wert("akku_w", 216.0) is None   # Lebenszeichen auch weg -> ungueltig


def test_lebenszeichen_ungueltig_zaehlt_nicht():
    pa = Prozessabbild(K)
    pa.aktualisieren(K.sensor_akku_leistung, zst("0", "W"), 100.0)
    pa.aktualisieren(K.sensor_lebenszeichen, zst("unavailable", "W"), 200.0)
    assert pa.wert("akku_w", 201.0) is None


def test_goe_lebenszeichen_getrennt_vom_messgeraet():
    pa = Prozessabbild(K)
    pa.aktualisieren("sensor.goe_325656_nrg_11", zst("0", "W"), 100.0)
    pa.aktualisieren(K.sensor_netz, zst("10", "W"), 200.0)    # SolarEdge-Lebenszeichen hilft nicht
    assert pa.wert("auto_w", 201.0) is None
    pa.aktualisieren("sensor.goe_325656_rbt", zst("123456"), 200.0)
    assert pa.wert("auto_w", 201.0) == 0.0


def test_energie_wh_nach_kwh_und_binaer():
    pa = Prozessabbild(K)
    pa.aktualisieren("sensor.goe_325656_eto", zst("12345", "Wh"), 100.0)
    pa.aktualisieren("binary_sensor.goe_325656_car_0", zst("on"), 100.0)
    assert pa.wert("goe_eto", 100.0) == 12.345
    assert pa.wert("auto_steckt", 100.0) is True


def test_verbindung_weg_macht_ungueltig():
    pa = Prozessabbild(K)
    pa.aktualisieren(K.sensor_netz, zst("500", "W"), 100.0)
    pa.aktualisieren(K.sensor_netz, None, 101.0)
    assert pa.wert("netz_w", 101.0) is None


def test_jede_entity_nur_einmal_abonniert():
    pa = Prozessabbild(K)
    assert len(pa.entity_ids) == len(set(pa.entity_ids))
