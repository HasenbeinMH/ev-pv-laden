"""M9: Uebergabe an den EV Tracker – gegen einen lokalen Testserver mit dem Verhalten von
heimladung.annehmen (Bearer-Token, 422 bei ungueltigen Daten)."""
import asyncio

import pytest
from aiohttp import web

import datenbank as db
from konfig import Konfig
from tracker import Uebergabe, adresse, nutzlast

TOKEN = "test-token"


def k(**w):
    return Konfig(goe_seriennummer="325656", ev_tracker_url="http://127.0.0.1:1",
                  ev_tracker_token=TOKEN, **w)


V = {"id": 1, "start": "2026-10-05T10:00:00+02:00", "ende": "2026-10-05T12:30:00+02:00",
     "pv": 8.0, "akku": 2.0, "netz": 1.5}


def test_nutzlast_akku_zaehlt_als_pv():
    assert nutzlast(V, k()) == {"start": V["start"], "ende": V["ende"], "kwh_netz": 1.5, "kwh_pv": 10.0}


def test_nutzlast_akku_als_netz_und_fahrzeug():
    d = nutzlast(V, k(akku_als_netz=True, ev_tracker_fahrzeug="EV3"))
    assert (d["kwh_netz"], d["kwh_pv"], d["fahrzeug"]) == (3.5, 8.0, "EV3")


def test_nutzlast_ohne_energie():
    assert nutzlast(dict(V, pv=0.0, akku=0.0, netz=0.01), k()) is None


def test_adresse():
    assert adresse(k()) == "http://127.0.0.1:1/api/ladung"
    assert adresse(Konfig(ev_tracker_url="http://x:8099/api/ladung/")) == "http://x:8099/api/ladung"


# --- Durchlauf gegen Testserver --------------------------------------------------------------

@pytest.fixture
def frische_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_DATEI", str(tmp_path / "t.db"))
    db.initialisieren()


def vorgang(start, pv, netz):
    vid = db.vorgang_anlegen(start, {}, "nur_pv")
    db.vorgang_beenden(vid, start.replace("10:00", "11:00"),
                       {"pv": pv, "akku": 0.0, "netz": netz, "ohne": 0.0, "eto": pv + netz, "trapez": pv + netz},
                       "abgesteckt")
    return vid


async def mit_server(antwort, ablauf):
    empfangen = []

    async def ladung(request):
        if request.headers.get("Authorization") != f"Bearer {TOKEN}":
            return web.json_response({"ok": False, "error": "Token fehlt oder falsch"}, status=401)
        d = await request.json()
        empfangen.append(d)
        return antwort(d)

    app = web.Application()
    app.router.add_post("/api/ladung", ladung)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        return await ablauf(f"http://127.0.0.1:{port}"), empfangen
    finally:
        await runner.cleanup()


def gesendet():
    return {v["start"]: v["gesendet"] for v in db.vorgaenge()}


def test_senden_ok_und_abgelehnt(frische_db):
    vorgang("2026-10-05T10:00:00+02:00", 5.0, 1.0)
    vorgang("2026-10-06T10:00:00+02:00", 0.0, 0.0)          # leer: wird nicht gesendet
    vorgang("2026-10-07T10:00:00+02:00", 3.0, 0.0)

    def antwort(d):
        if d["start"].startswith("2026-10-07"):
            return web.json_response({"ok": False, "error": "Fahrzeug „X“ unbekannt"}, status=422)
        return web.json_response({"ok": True})

    async def ablauf(url):
        u = Uebergabe(Konfig(ev_tracker_url=url, ev_tracker_token=TOKEN))
        return await u.durchlauf(), u

    (ok, u), empfangen = asyncio.run(mit_server(antwort, ablauf))
    assert ok and u.offen == 0 and len(empfangen) == 2
    g = gesendet()
    assert g["2026-10-05T10:00:00+02:00"][:4] == "2026"
    assert g["2026-10-06T10:00:00+02:00"].startswith("nicht gesendet")
    assert g["2026-10-07T10:00:00+02:00"] == "abgelehnt: Fahrzeug „X“ unbekannt"


def test_falscher_token_bleibt_im_puffer(frische_db):
    vorgang("2026-10-05T10:00:00+02:00", 5.0, 1.0)

    async def ablauf(url):
        u = Uebergabe(Konfig(ev_tracker_url=url, ev_tracker_token="falsch"))
        return await u.durchlauf(), u

    (ok, u), _ = asyncio.run(mit_server(lambda d: web.json_response({"ok": True}), ablauf))
    assert not ok and u.offen == 1 and "Token" in u.letzter_fehler
    assert gesendet()["2026-10-05T10:00:00+02:00"] is None


def test_nicht_erreichbar_bleibt_im_puffer(frische_db):
    vorgang("2026-10-05T10:00:00+02:00", 5.0, 1.0)
    u = Uebergabe(Konfig(ev_tracker_url="http://127.0.0.1:9", ev_tracker_token=TOKEN))
    assert asyncio.run(u.durchlauf()) is False
    assert u.offen == 1 and "nicht erreichbar" in u.letzter_fehler


def test_offener_vorgang_wird_nicht_gesendet(frische_db):
    db.vorgang_anlegen("2026-10-05T10:00:00+02:00", {}, "nur_pv")
    assert db.vorgaenge_ungesendet() == []


# --- Verbindungstest -------------------------------------------------------------------------

def test_verbindungstest_token_richtig(frische_db):
    def antwort(d):          # wie heimladung.annehmen: leere Ladung -> 422 (nach Token-Pruefung)
        assert d == {}
        return web.json_response({"ok": False, "error": "start: keine gültige Zeit (None)"}, status=422)

    async def ablauf(url):
        return await Uebergabe(Konfig(ev_tracker_url=url, ev_tracker_token=TOKEN)).verbindung_pruefen()

    e, empfangen = asyncio.run(mit_server(antwort, ablauf))
    assert e["ok"] and "Token angenommen" in e["text"] and empfangen == [{}]


def test_verbindungstest_token_falsch(frische_db):
    async def ablauf(url):
        return await Uebergabe(Konfig(ev_tracker_url=url, ev_tracker_token="falsch")).verbindung_pruefen()

    e, _ = asyncio.run(mit_server(lambda d: web.json_response({"ok": True}), ablauf))
    assert not e["ok"] and "401" in e["text"]


def test_verbindungstest_nicht_erreichbar(frische_db):
    u = Uebergabe(Konfig(ev_tracker_url="http://127.0.0.1:9", ev_tracker_token=TOKEN))
    e = asyncio.run(u.verbindung_pruefen())
    assert not e["ok"] and "nicht erreichbar" in e["text"]


def test_verbindungstest_ohne_konfiguration(frische_db):
    assert not asyncio.run(Uebergabe(Konfig()).verbindung_pruefen())["ok"]
