from wiederanlauf import FUP, FUP_VERSUCHE, MELDEN, TREIBER_A, Wiederanlauf

W = 300.0


def lauf(w, t, massnahme="fup_dann_a", aktiv=True, freigabe=True, steckt=True, auto_w=0.0,
         status="Inaktiv/Frei"):
    return w.zyklus(t, massnahme, W, aktiv, freigabe, steckt, auto_w, status)


def test_erst_nach_wartezeit():
    w = Wiederanlauf()
    assert lauf(w, 0).massnahme is None
    assert lauf(w, W - 1).massnahme is None
    assert lauf(w, W).massnahme == FUP


def test_eskalation_fup_dann_treiber_a():
    w = Wiederanlauf()
    lauf(w, 0)
    folge = [lauf(w, W * n).massnahme for n in range(1, FUP_VERSUCHE + 2)]
    assert folge == [FUP] * FUP_VERSUCHE + [TREIBER_A]


def test_nur_melden_einmal():
    w = Wiederanlauf()
    lauf(w, 0, "melden")
    assert lauf(w, W, "melden").massnahme == MELDEN
    assert lauf(w, 2 * W, "melden").massnahme is None


def test_fup_ohne_a_meldet_danach():
    w = Wiederanlauf()
    lauf(w, 0, "fup")
    folge = [lauf(w, W * n, "fup").massnahme for n in range(1, FUP_VERSUCHE + 3)]
    assert folge == [FUP] * FUP_VERSUCHE + [MELDEN, None]


def test_laedt_wieder_quittiert_mit_meldung():
    w = Wiederanlauf()
    lauf(w, 0)
    assert lauf(w, W).massnahme == FUP
    b = lauf(w, W + 30, auto_w=4000.0)
    assert b.massnahme == MELDEN and b.text.startswith("lädt wieder")
    assert w.versuche == 0


def test_abstecken_setzt_zurueck():
    w = Wiederanlauf()
    lauf(w, 0)
    lauf(w, W)
    assert lauf(w, W + 1, steckt=False).massnahme is None and w.versuche == 0


def test_keine_stoerung_wenn_auto_nicht_will_oder_keine_freigabe():
    for kw in ({"status": "Ladung beendet"}, {"status": "Warte auf Fahrzeug"}, {"status": "Complete"},
               {"freigabe": False}, {"aktiv": False}, {"auto_w": None}, {"steckt": None}):
        w = Wiederanlauf()
        lauf(w, 0, **kw)
        assert lauf(w, 10 * W, **kw).massnahme is None, kw


def test_unterbrochene_bedingung_beginnt_neu():
    w = Wiederanlauf()
    lauf(w, 0)
    lauf(w, W - 10, freigabe=False)
    assert lauf(w, W).massnahme is None
    assert lauf(w, 2 * W).massnahme == FUP
