import pytest

from bilanz import Bilanz, BilanzZustand, aufteilen


# --- Aufteilung "Haus zuerst, Auto bekommt den Ueberschuss" ------------------------

@pytest.mark.parametrize("p_auto,netz,akku,erwartet", [
    (5000, -2000, 0, {"pv": 5000, "akku": 0, "netz": 0}),       # reiner Ueberschuss
    (5000, 1000, 0, {"pv": 4000, "akku": 0, "netz": 1000}),     # teils Netz
    (5000, 1000, 2500, {"pv": 1500, "akku": 2500, "netz": 1000}),
    (5000, 0, 8000, {"pv": 0, "akku": 5000, "netz": 0}),         # Akku groesser als Auto
    (5000, 9000, 0, {"pv": 0, "akku": 0, "netz": 5000}),         # Netz groesser als Auto
    (5000, -500, -1500, {"pv": 5000, "akku": 0, "netz": 0}),     # Akku laedt, Einspeisung
    (0, 3000, 1000, {"pv": 0, "akku": 0, "netz": 0}),            # Auto laedt nicht
])
def test_aufteilen(p_auto, netz, akku, erwartet):
    assert aufteilen(p_auto, netz, akku) == pytest.approx(erwartet)


def test_aufteilen_konsistent_mit_tracker_vorlage():
    """Vorlage: Netz = min(Netzbezug, Wallbox), PV = Rest (Akku in PV enthalten)."""
    t = aufteilen(7000, 1200, 3000)
    assert t["netz"] == min(1200, 7000)
    assert t["pv"] + t["akku"] == 7000 - t["netz"]


# --- Integration und Buchung auf den Wallbox-Zaehler -------------------------------

def laden_simulieren(b, t0, dauer_s, p_auto, netz, akku, eto0, schritt=1.0):
    """Konstante Leistungen; eto steigt passend zur Leistung (wie die echte Wallbox)."""
    t, eto = t0, eto0
    while t < t0 + dauer_s:
        b.schritt(t, p_auto, netz, akku)
        t += schritt
        eto += p_auto * schritt / 3600 / 1000
        b.eto(t, round(eto, 3))
    return t, eto


def test_summe_exakt_gleich_eto():
    b = Bilanz(nach_neustart=False)
    b.eto(0.0, 100.0)
    t, eto = laden_simulieren(b, 0.0, 600, 6000, 1000, 2000, 100.0)
    z = b.z
    assert sum(z.kwh.values()) == pytest.approx(z.eto_letzt - 100.0, abs=1e-9)
    assert z.kwh["netz"] / sum(z.kwh.values()) == pytest.approx(1000 / 6000, rel=0.02)
    assert z.kwh["akku"] / sum(z.kwh.values()) == pytest.approx(2000 / 6000, rel=0.02)
    assert z.kwh_trapez == pytest.approx(z.kwh_eto, rel=0.02)   # Plausibilitaet


def test_erster_anstieg_nach_neustart_ohne_aufteilung():
    zustand = BilanzZustand(eto_letzt=100.0)
    b = Bilanz(zustand, nach_neustart=True)
    buchung = b.eto(10.0, 102.5)   # 2,5 kWh waehrend das Add-on aus war
    assert buchung.art == "ohne_aufteilung"
    assert b.z.kwh["netz"] == pytest.approx(2.5)
    assert b.z.kwh_ohne_aufteilung == pytest.approx(2.5)


def test_zaehler_zurueck_nichts_gebucht():
    b = Bilanz(BilanzZustand(eto_letzt=500.0), nach_neustart=False)
    buchung = b.eto(1.0, 3.0)
    assert buchung.art == "neu_angesetzt"
    assert sum(b.z.kwh.values()) == 0
    assert b.z.eto_letzt == 3.0


def test_unplausibler_sprung_nicht_gebucht():
    b = Bilanz(nach_neustart=False)
    b.eto(0.0, 100.0)
    buchung = b.eto(10.0, 150.0)   # 50 kWh in 10 s
    assert buchung.art == "neu_angesetzt"
    assert sum(b.z.kwh.values()) == 0


def test_seltene_zaehler_updates_sind_plausibel():
    """eto kommt nur jede Minute, wird aber jeden Zyklus (1 s) abgefragt."""
    b = Bilanz(nach_neustart=False)
    b.eto(0.0, 10.0)
    for t in range(1, 60):
        b.schritt(float(t), 17000, -17000, 0)
        assert b.eto(float(t), 10.0) is None
    b.schritt(60.0, 17000, -17000, 0)
    buchung = b.eto(60.0, 10.283)   # 17 kW * 60 s = 283 Wh
    assert buchung.art == "anteilig"
    assert b.z.kwh["pv"] == pytest.approx(0.283)


def test_topf_leer_nutzt_letzten_anteil_dann_netz():
    b = Bilanz(nach_neustart=False)
    b.eto(0.0, 0.0)
    b.schritt(0.0, 4000, -4000, 0)
    b.schritt(10.0, 4000, -4000, 0)
    assert b.eto(10.0, 0.011).art == "anteilig"
    # Leistungswerte fallen aus, eto laeuft weiter
    b.schritt(20.0, None, None, None)
    assert b.eto(20.0, 0.022).art == "letzter_anteil"
    assert b.z.kwh["pv"] == pytest.approx(0.022)
    # nach mehr als 5 min ohne Aufteilung: Netz
    assert b.eto(400.0, 0.030).art == "ohne_aufteilung"
    assert b.z.kwh["netz"] == pytest.approx(0.008)


def test_ungueltige_netzwerte_zaehlen_als_netz_und_unsicher():
    b = Bilanz(nach_neustart=False)
    b.eto(0.0, 0.0)
    b.schritt(0.0, 3600, None, 0)
    b.schritt(10.0, 3600, None, 0)
    b.eto(10.0, 0.010)
    assert b.z.kwh["netz"] == pytest.approx(0.010)
    assert b.z.kwh_unsicher == pytest.approx(0.010)


def test_keine_integration_ueber_luecke():
    b = Bilanz(nach_neustart=False)
    b.schritt(0.0, 3600, -5000, 0)
    b.schritt(100.0, 3600, -5000, 0)   # 100 s Luecke
    assert b.z.kwh_trapez == 0


def test_zaehler_steigen_nur():
    b = Bilanz(nach_neustart=False)
    b.eto(0.0, 0.0)
    werte = []
    for i in range(1, 50):
        b.schritt(float(i), 3000 if i % 7 else 0, (-1) ** i * 2000, 500)
        b.eto(float(i), i * 0.0008)
        werte.append(dict(b.z.kwh))
    for vorher, nachher in zip(werte, werte[1:]):
        for q in vorher:
            assert nachher[q] >= vorher[q]


def test_zustand_rundreise():
    b = Bilanz(nach_neustart=False)
    b.eto(0.0, 1.0)
    laden_simulieren(b, 0.0, 60, 5000, 0, 0, 1.0)
    z2 = BilanzZustand.aus_dict(b.z.als_dict())
    assert z2.kwh == b.z.kwh and z2.eto_letzt == b.z.eto_letzt
