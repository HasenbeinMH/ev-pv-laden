# -*- coding: utf-8 -*-
"""
FastAPI-App des Add-ons (Ingress). Startet beim Hochfahren die Laufzeit:
Konfiguration -> Protokoll -> Datenbank -> HA-Verbindung -> Prozessabbild.

Ingress: alle Links und Abfragen pfad-relativ (kein fuehrender "/"), weil HA die
Oberflaeche unter /api/hassio_ingress/<token>/ einblendet.
"""
import asyncio
import logging
import os
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(BASE_DIR))

import datenbank as db  # noqa: E402
import konfig as konfig_mod  # noqa: E402
import protokoll  # noqa: E402
from ha_client import HAClient, IST_ADDON, verbindung_aus_umgebung  # noqa: E402
from prozessabbild import Prozessabbild  # noqa: E402
from version import VERSION  # noqa: E402

log = logging.getLogger("app")


class Laufzeit:
    """Alles, was zwischen Start und Stopp des Add-ons lebt (Instanz-DB des Ganzen)."""

    def __init__(self):
        self.konfig: konfig_mod.Konfig | None = None
        self.konfig_fehler: list[str] = []
        self.abbild: Prozessabbild | None = None
        self.ha: HAClient | None = None
        self.ha_fehler: str | None = None
        self.gestartet = time.time()
        self._task: asyncio.Task | None = None

    async def starten(self) -> None:
        try:
            self.konfig = konfig_mod.laden()
        except konfig_mod.KonfigFehler as e:
            self.konfig_fehler = e.fehler
        protokoll.einrichten(self.konfig.log_level if self.konfig else "info", konfig_mod.DATA_DIR)
        log.info("EV PV-Laden %s startet (%s)", VERSION, "Add-on" if IST_ADDON else "Entwicklung")
        if self.konfig_fehler:
            for f in self.konfig_fehler:
                log.error("Konfiguration: %s", f)
            return

        log.info("Konfiguration: %s", self.konfig.ohne_geheimnisse())
        version = db.initialisieren()
        log.info("Datenbank %s (Schema %d)", db.DB_DATEI, version)
        db.ereignis("info", "start", f"Add-on {VERSION} gestartet, Trockenlauf "
                                     f"{'an' if self.konfig.trockenlauf else 'AUS'}")

        self.abbild = Prozessabbild(self.konfig)
        daten = verbindung_aus_umgebung()
        if daten is None:
            self.ha_fehler = "Keine Verbindungsdaten (SUPERVISOR_TOKEN bzw. HA_URL/HA_TOKEN fehlen)"
            log.error(self.ha_fehler)
            return
        self.ha = HAClient(daten, self.abbild.entity_ids, self.abbild.aktualisieren)
        # In M2 gibt es noch keinen Schreibpfad – Sperre bleibt unabhaengig vom Trockenlauf gesetzt
        self.ha.schreiben_gesperrt = True
        self._task = asyncio.create_task(self.ha.laufen(), name="ha_client")

    async def stoppen(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("EV PV-Laden beendet")

    def status(self) -> dict:
        k = self.konfig
        return {
            "version": VERSION,
            "addon": IST_ADDON,
            "laufzeit_s": round(time.time() - self.gestartet),
            "konfig_ok": not self.konfig_fehler,
            "konfig_fehler": self.konfig_fehler,
            "trockenlauf": k.trockenlauf if k else True,
            "grenzen": None if not k else {
                "max_strom_a": k.max_strom_a, "strom_1ph_max_a": k.strom_1ph_max_a,
                "min_strom_a": k.min_strom_a, "max_alter_s": k.max_alter_s,
            },
            "ha": {
                "verbunden": bool(self.ha and self.ha.verbunden),
                "version": self.ha.ha_version if self.ha else None,
                "fehler": self.ha_fehler or (self.ha.letzter_fehler if self.ha else None),
            },
            "signale": self.abbild.uebersicht() if self.abbild else [],
        }


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.lz = Laufzeit()
    await app.state.lz.starten()
    yield
    await app.state.lz.stoppen()


app = FastAPI(title="EV PV-Laden", lifespan=lifespan)
app.mount("/static",StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
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
