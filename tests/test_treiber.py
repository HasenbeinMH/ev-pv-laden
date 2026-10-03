from konfig import Konfig
from strategie import AUS, MIN_PV, NUR_PV, SOFORT, Ausgang
from treiber import IDS_TAKT_S, NACHSTELLEN_S, UEBERSTROM_S, TreiberIds

K = Konfig(goe_seriennummer="325656", max_strom_a=24, ev_max_strom_1ph_a=16)
FREI = Ausgang(True, 3000.0, 3000.0, 3000.0, "laedt", "test")

# go-e im Zustand, den evcc hinterlassen hat: Standardmodus, gesperrt
EVCC_REST = {"goe_lebenszeichen": "123", "goe_lmo": "3", "goe_frc": "1", "goe_fup": True,
             "goe_psm": "0", "goe_frm": "1", "goe_amp": 24.0, "auto_i1": 0.0, "auto_i2": 0.0, "auto_i3": 0.0,
             "pv_w": 4200.0}


def texte(aktionen):
    return [a.text for a in aktionen]


def test_eco_sollkonfiguration_und_ids():
    t = TreiberIds(K)
    akt = t.zyklus(0.0, NUR_PV, FREI, -1500.0, dict(EVCC_REST))
    dienste = {(a.domain, a.service, str(a.daten)) for a in akt}
    assert ("select", "select_option", "{'option': '4'}") in dienste      # lmo=4
    assert ("select", "select_option", "{'option': '0'}") in dienste      # frc=0
    amp = next(a for a in akt if a.ziel and a.ziel["entity_id"].endswith("_amp"))
    assert amp.daten == {"value": 16}       # Phasen unbekannt -> einphasige Grenze
    ids = next(a for a in akt if a.ids)
    assert ids.domain == "goecharger_api2" and ids.service == "set_pv_data"
    assert ids.daten == {"pgrid": -1500, "pakku": 0, "ppv": 4200}


def test_ids_takt_und_kein_dauerfeuer_bei_sollwerten():
    t = TreiberIds(K)
    w = dict(EVCC_REST, goe_lmo="4", goe_frc="0", goe_frm="2", goe_amp=16.0)
    assert sum(a.ids for a in t.zyklus(0.0, NUR_PV, FREI, 0.0, w)) == 1
    assert t.zyklus(1.0, NUR_PV, FREI, 0.0, w) == []              # nichts zu tun
    assert sum(a.ids for a in t.zyklus(IDS_TAKT_S, NUR_PV, FREI, 0.0, w)) == 1


def test_nachstellen_hoechstens_alle_30_s():
    t = TreiberIds(K)
    w = dict(EVCC_REST)
    erst = [x for x in texte(t.zyklus(0.0, NUR_PV, FREI, None, w)) if x.startswith("lmo")]
    zweit = [x for x in texte(t.zyklus(5.0, NUR_PV, FREI, None, w)) if x.startswith("lmo")]
    dritt = [x for x in texte(t.zyklus(NACHSTELLEN_S, NUR_PV, FREI, None, w)) if x.startswith("lmo")]
    assert erst and not zweit and dritt


def test_dreiphasig_volle_grenze():
    t = TreiberIds(K)
    w = dict(EVCC_REST, goe_amp=16.0, auto_i1=10.0, auto_i2=10.0, auto_i3=10.0)
    amp = [a for a in t.zyklus(0.0, NUR_PV, FREI, 0.0, w) if a.text.startswith("amp")]
    assert amp[0].daten == {"value": 24}


def test_sofort_fest_dreiphasig_ohne_ids():
    t = TreiberIds(K)
    akt = t.zyklus(0.0, SOFORT, Ausgang(True, 16560, None, None, "laedt", ""), None,
                   dict(EVCC_REST, goe_amp=16.0))
    assert not any(a.ids for a in akt)
    assert "psm=2 (Sofort: fest dreiphasig)" in texte(akt)
    assert any(a.text.startswith("amp=24") for a in akt)


def test_aus_sperrt():
    t = TreiberIds(K)
    akt = t.zyklus(0.0, AUS, Ausgang(False, 0, None, None, "bereit", ""), None,
                   dict(EVCC_REST, goe_frc="0"))
    assert texte(akt) == ["frc=1 (Modus Aus)"]


def test_schieflast_verriegelt_und_moduswechsel_hebt_auf():
    t = TreiberIds(K)
    w = dict(EVCC_REST, goe_lmo="4", goe_frc="0", goe_frm="2", goe_amp=16.0, auto_i1=18.5)   # einphasig 18,5 A > 16+1
    assert t.zyklus(0.0, MIN_PV, FREI, 0.0, w)[0].ids          # Toleranzzeit laeuft
    akt = t.zyklus(UEBERSTROM_S, MIN_PV, FREI, 0.0, w)
    assert t.verriegelt and texte(akt)[0].startswith("frc=1 (verriegelt")
    assert not any(a.ids for a in akt)
    t.zyklus(UEBERSTROM_S + 1, NUR_PV, FREI, 0.0, dict(w, auto_i1=0.0))
    assert t.verriegelt is None


def test_wallbox_nicht_erreichbar_sendet_nichts():
    t = TreiberIds(K)
    assert t.zyklus(0.0, NUR_PV, FREI, -2000.0, dict(EVCC_REST, goe_lebenszeichen=None)) == []


def test_ppv_abschaltbar():
    t = TreiberIds(K, ppv_senden=False)
    ids = next(a for a in t.zyklus(0.0, NUR_PV, FREI, -100.0, dict(EVCC_REST)) if a.ids)
    assert ids.daten["ppv"] == 0


def test_sollwert_erreicht_keine_aktion():
    t = TreiberIds(K)
    w = dict(EVCC_REST, goe_amp=24.0, auto_i1=10.0, auto_i2=10.0, auto_i3=10.0)
    assert not [a for a in t.zyklus(0.0, NUR_PV, FREI, 0.0, w) if a.text.startswith("amp")]
