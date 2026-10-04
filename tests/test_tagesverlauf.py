from konfig import Konfig
from prozessabbild import signale
from tagesverlauf import Tagesverlauf, aus_historie

K = Konfig(goe_seriennummer="325656", sensor_haus="sensor.haus", sensor_pv="sensor.pv")
SIG = {s.name: s for s in signale(K)}
T0 = 1_000_020 * 60.0       # Minutengrenze


def sig(name, einheit="W"):
    return SIG[name], einheit


def test_historie_einheit_vorzeichen_und_mittel():
    h = {
        # PV in kW, wechselt in der Minutenmitte von 2 auf 4 kW -> Mittel 3000 W
        "sensor.pv": [{"s": "2", "lu": T0 - 5}, {"s": "4", "lu": T0 + 30}],
        # SolarEdge M1: + = Einspeisung -> intern invertiert (Bezug +)
        K.sensor_netz: [{"s": "1500", "lu": T0 - 100}],
        "sensor.haus": [{"s": "900", "lu": T0 - 100}],
        "sensor.goe_325656_nrg_11": [{"s": "unavailable", "lu": T0 - 100}],
    }
    s = {"pv_w": sig("pv_w", "kW"), "netz_w": sig("netz_w"), "haus_w": sig("haus_w"), "auto_w": sig("auto_w")}
    p = aus_historie(h, s, T0, T0 + 120, haus_enthaelt_auto=True)
    assert [t for t, _ in p] == [T0, T0 + 60]
    m0, m1 = p[0][1], p[1][1]
    assert m0["pv"] == 3000 and m1["pv"] == 4000
    assert m0["netz"] == -1500                       # Einspeisung
    assert m0["auto"] is None and m0["haus"] == 900  # Wallbox unbekannt: Hauswert wie gemessen


def test_vor_dem_ersten_wert_nichts():
    h = {K.sensor_netz: [{"s": "100", "lu": T0 + 120}]}
    p = aus_historie(h, {"netz_w": sig("netz_w")}, T0, T0 + 180, True)
    assert [t for t, _ in p] == [T0 + 120]


def test_vorfuellen_nur_vor_live_daten():
    v = Tagesverlauf()
    v.hinzufuegen(T0 + 120, {"pv": 100})
    v.hinzufuegen(T0 + 180, {"pv": 200})            # schliesst Minute T0+120 ab
    n = v.vorfuellen([(T0, {"pv": 1}), (T0 + 60, {"pv": 2}), (T0 + 120, {"pv": 9})])
    assert n == 2
    assert [t for t, _ in v.punkte] == [T0, T0 + 60, T0 + 120]
    assert v.punkte[2][1]["pv"] == 100              # Live-Wert bleibt
