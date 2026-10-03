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


@app.get("/api/prognose")
def api_prognose(request: Request):
    lz = request.app.state.lz
    if not lz.erfassung:
        return {"verfuegbar": False}
    from datetime import datetime
    return lz.prognose.uebersicht(datetime.now(lz.erfassung.tz))
