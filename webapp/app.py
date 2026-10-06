# -*- coding: utf-8 -*-
"""
FastAPI-App des Add-ons (Ingress). Startet beim Hochfahren die Laufzeit.

Ingress: alle Links und Abfragen pfad-relativ (kein fuehrender "/"), weil HA die
Oberflaeche unter /api/hassio_ingress/<token>/ einblendet.
Die eigentliche Arbeit steckt in laufzeit.py.
"""
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(BASE_DIR))

import datenbank as db  # noqa: E402
import konfig as konfig_mod  # noqa: E402
import protokoll  # noqa: E402
from laufzeit import Laufzeit  # noqa: E402
from version import VERSION  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.lz = Laufzeit()
    await app.state.lz.starten()
    yield
    await app.state.lz.stoppen()


app = FastAPI(title="EV PV-Laden", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@app.get("/", response_class=HTMLResponse)
def startseite(request: Request):
    return templates.TemplateResponse(request, "index.html", {"version": VERSION})


@app.get("/api/status")
def api_status(request: Request):
    return request.app.state.lz.status()


@app.get("/api/protokoll")
def api_protokoll(zeilen: int = 200):
    return {"zeilen": protokoll.letzte_zeilen(konfig_mod.DATA_DIR, min(max(zeilen, 1), 2000))}


@app.get("/api/ereignisse")
def api_ereignisse(request: Request, anzahl: int = 100):
    if request.app.state.lz.konfig_fehler:
        return {"ereignisse": []}
    return {"ereignisse": db.ereignisse(min(max(anzahl, 1), 1000))}


@app.get("/api/bilanz")
def api_bilanz(request: Request):
    lz = request.app.state.lz
    return lz.erfassung.uebersicht() if lz.erfassung else {}


@app.get("/api/regelung")
def api_regelung(request: Request):
    lz = request.app.state.lz
    return lz.regelung.status() if lz.regelung else {}


@app.get("/api/verlauf")
def api_verlauf(request: Request, sekunden: int = 1800, schritt: int = 2):
    lz = request.app.state.lz
    if not lz.regelung:
        return {"spalten": [], "daten": []}
    return lz.regelung.verlauf_liste(min(max(sekunden, 10), 3600), min(max(schritt, 1), 60))


@app.post("/api/parameter")
async def api_parameter(request: Request):
    lz = request.app.state.lz
    if not lz.regelung:
        return JSONResponse({"ok": False, "fehler": ["Regelung nicht aktiv"]}, status_code=409)
    try:
        neu = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "fehler": ["kein gueltiges JSON"]}, status_code=400)
    if not isinstance(neu, dict):
        return JSONResponse({"ok": False, "fehler": ["JSON-Objekt erwartet"]}, status_code=400)
    fehler = lz.regelung.parameter_setzen(neu)
    if fehler:
        return JSONResponse({"ok": False, "fehler": fehler}, status_code=422)
    return {"ok": True, "parameter": lz.regelung.param.als_dict()}


@app.post("/api/laden")
async def api_laden(request: Request):
    """Start/Stopp: {"start": true|false}."""
    lz = request.app.state.lz
    if not lz.regelung:
        return JSONResponse({"ok": False, "fehler": ["Regelung nicht aktiv"]}, status_code=409)
    try:
        start = (await request.json())["start"]
        if not isinstance(start, bool):
            raise ValueError
    except Exception:
        return JSONResponse({"ok": False, "fehler": ['{"start": true/false} erwartet']}, status_code=400)
    fehler = lz.laden_setzen(start)
    if fehler:
        return JSONResponse({"ok": False, "fehler": fehler}, status_code=409)
    return {"ok": True, "gestartet": lz.regelung.gestartet}


@app.post("/api/trockenlauf")
async def api_trockenlauf(request: Request):
    """Trockenlauf schalten (nur wenn die Add-on-Option ihn nicht fest sperrt)."""
    lz = request.app.state.lz
    if not lz.regelung:
        return JSONResponse({"ok": False, "fehler": ["Regelung nicht aktiv"]}, status_code=409)
    try:
        an = (await request.json())["an"]
        if not isinstance(an, bool):
            raise ValueError
    except Exception:
        return JSONResponse({"ok": False, "fehler": ['{"an": true/false} erwartet']}, status_code=400)
    fehler = await lz.trockenlauf_setzen(an)
    if fehler:
        return JSONResponse({"ok": False, "fehler": fehler}, status_code=409)
    return {"ok": True, "trockenlauf": lz.trockenlauf}


@app.get("/api/heute")
def api_heute(request: Request):
    """Minutenmittel seit Mitternacht (Ortszeit von HA) fuer das Dashboard."""
    lz = request.app.state.lz
    if not lz.erfassung:
        return {"spalten": [], "daten": []}
    from datetime import datetime
    mitternacht = datetime.now(lz.erfassung.tz).replace(hour=0, minute=0, second=0, microsecond=0)
    return lz.tagesverlauf.liste(mitternacht.timestamp())


@app.get("/api/ladekurve")
def api_ladekurve(request: Request):
    """Minutenmittel seit Beginn der laufenden Ladung (Autokarte im Dashboard)."""
    lz = request.app.state.lz
    offen = lz.erfassung.erkennung.offen if lz.erfassung else None
    if offen is None:
        return {"aktiv": False}
    start = offen.start if offen.start.tzinfo else offen.start.replace(tzinfo=lz.erfassung.tz)
    beginn = int(start.timestamp() // 60) * 60
    daten = lz.tagesverlauf.liste(beginn)
    en = lz.erfassung.stand().minus(offen.stand_start)
    return {"aktiv": True, "start": start.isoformat(timespec="minutes"), "kwh": round(en.eto, 2), **daten}


@app.post("/api/tracker/pruefen")
async def api_tracker_pruefen(request: Request):
    """Verbindungstest zum EV Tracker (leere Ladung, wird dort nicht gespeichert)."""
    lz = request.app.state.lz
    if not lz.tracker:
        return JSONResponse({"ok": False, "text": "Add-on startet noch"}, status_code=409)
    return await lz.tracker.verbindung_pruefen()


@app.post("/api/tracker/senden")
async def api_tracker_senden(request: Request):
    """Offene Ladevorgaenge sofort an den EV Tracker uebergeben (sonst jede Minute)."""
    lz = request.app.state.lz
    if not lz.tracker or not lz.tracker.aktiv:
        return JSONResponse({"ok": False, "fehler": ["EV Tracker nicht eingerichtet (Adresse/Token)"]},
                            status_code=409)
    ok = await lz.tracker.durchlauf()
    return {"ok": ok, "tracker": lz.tracker.status()}


@app.post("/api/auto_soc")
async def api_auto_soc(request: Request):
    """SoC des Autos jetzt (Zielzeit) – ab hier rechnet der Wallbox-Zaehler hoch."""
    lz = request.app.state.lz
    if not lz.regelung:
        return JSONResponse({"ok": False, "fehler": ["Regelung nicht aktiv"]}, status_code=409)
    try:
        soc = float((await request.json())["soc"])
    except Exception:
        return JSONResponse({"ok": False, "fehler": ["{\"soc\": Zahl} erwartet"]}, status_code=400)
    fehler = lz.regelung.auto_soc_setzen(soc)
    if fehler:
        return JSONResponse({"ok": False, "fehler": fehler}, status_code=422)
    return {"ok": True, "zielzeit": lz.regelung.zielzeit_status()}


@app.get("/api/prognose")
def api_prognose(request: Request):
    lz = request.app.state.lz
    if not lz.erfassung:
        return {"verfuegbar": False}
    from datetime import datetime
    jetzt = datetime.now(lz.erfassung.tz)
    p, quelle = lz.prognose()
    aus = p.uebersicht(jetzt)
    aus["quelle"] = quelle
    if p is not lz.prognose_ha and lz.prognose_ha.werte:
        aus["vergleich"] = lz.prognose_ha.uebersicht(jetzt)
    # Gemessene PV-Erzeugung heute (Tageskurve) als Stundenwerte zum Vergleich
    from datetime import timedelta
    mitternacht = jetzt.replace(hour=0, minute=0, second=0, microsecond=0)
    stunden = lz.tagesverlauf.stunden_wh(mitternacht.timestamp())
    aus["gemessen"] = [{"zeit": (datetime.fromtimestamp(h, lz.erfassung.tz) + timedelta(hours=1)).isoformat(),
                        "wh": round(wh), "minuten": n} for h, wh, n in stunden]
    if stunden:
        aus["gemessen_kwh"] = round(sum(wh for _, wh, _ in stunden) / 1000, 2)
        # Prognose fuer denselben Zeitraum (ab der ersten gemessenen Minute bis jetzt)
        von = datetime.fromtimestamp(lz.tagesverlauf.punkte[0][0], lz.erfassung.tz) if lz.tagesverlauf.punkte else mitternacht
        # ... bis zum Ende der letzten abgeschlossenen Minute – derselbe Zeitraum wie gemessen
        bis = datetime.fromtimestamp(lz.tagesverlauf.punkte[-1][0] + 60, lz.erfassung.tz)
        aus["prognose_bis_jetzt_kwh"] = round(p._summe(max(von, mitternacht), bis) / 1000, 2) if p.werte else None
    return aus


@app.get("/api/prognose/stunden")
def api_prognose_stunden(request: Request):
    """Stundenprognose des eigenen Modells fuer die HA-Integration „EV PV-Laden Prognose“
    (Energie-Dashboard). Format wie energy/solar_forecast: Zeitstempel = Ende der Stunde, Wh."""
    lz = request.app.state.lz
    p = lz.prognose_eigen
    return {"verfuegbar": bool(p.werte), "quelle": "eigenes Modell",
            "stand": p.stand.isoformat(timespec="seconds") if p.stand else None,
            "wh_hours": {t.isoformat(): round(wh) for t, wh in p.werte.items()}}


@app.get("/api/pvmodell")
def api_pvmodell(request: Request):
    lz = request.app.state.lz
    if not lz.pv:
        return {"aktiv": False, "zustand": "keine Verbindung zu Home Assistant"}
    from datetime import datetime
    return lz.pv.status(datetime.now(lz.erfassung.tz).date())


@app.post("/api/pvmodell/gereinigt")
def api_gereinigt(request: Request):
    lz = request.app.state.lz
    if not lz.pv or not lz.pv.modell.trainiert:
        return JSONResponse({"ok": False, "fehler": ["PV-Modell noch nicht trainiert"]}, status_code=409)
    from datetime import datetime
    lz.pv.gereinigt(datetime.now(lz.erfassung.tz).date())
    return {"ok": True}
