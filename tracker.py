# -*- coding: utf-8 -*-
"""
Uebergabe beendeter Ladevorgaenge an den EV Tracker (M9).

Schnittstelle (geprueft im Quellcode des EV Trackers, heimladung.annehmen):
  POST <ev_tracker_url>/api/ladung, Header Authorization: Bearer <Token>
  JSON: start, ende (ISO), kwh_netz, kwh_pv, kosten (optional), fahrzeug (optional, id/Name)
  Erneutes Senden derselben Startminute ueberschreibt (upsert) – Wiederholen ist gefahrlos.

Aufteilung: der Hausakku zaehlt als PV (akku_als_netz: false) oder als Netz (true).
"Ohne Aufteilung" steckt im Bilanzbaustein bereits im Netzanteil.
kosten wird nicht gesendet: der Tracker rechnet den Netzanteil mit seinem Tagestarif.

Ablauf wie ein Sendepuffer: jeder beendete Vorgang mit gesendet = NULL wird versucht.
  2xx        -> gesendet = Zeitpunkt
  401/403    -> Token/Empfang falsch: bleibt im Puffer, Meldung einmal, langsam erneut
  andere 4xx -> Daten abgelehnt (z. B. 0 kWh): gesendet = "abgelehnt: <Grund>", kein Wiederholen
  Netz/5xx   -> bleibt im Puffer, erneuter Versuch mit wachsendem Abstand
"""
import asyncio
import logging
from datetime import datetime

import aiohttp

import datenbank as db
from konfig import Konfig

log = logging.getLogger("tracker")

TAKT_S = 60.0
WARTEN_MAX_S = 3600.0
TIMEOUT_S = 15.0
MIN_KWH = 0.05            # kleinere Vorgaenge (Abstecken ohne Laden) werden nicht gesendet


def nutzlast(v: dict, k: Konfig) -> dict | None:
    """Ladevorgang (Zeile aus ladevorgaenge) -> JSON fuer den Tracker; None = nichts zu senden."""
    pv, akku, netz = (float(v.get(n) or 0.0) for n in ("pv", "akku", "netz"))
    if pv + akku + netz < MIN_KWH:
        return None
    if k.akku_als_netz:
        netz += akku
    else:
        pv += akku
    d = {"start": v["start"], "ende": v["ende"], "kwh_netz": round(netz, 3), "kwh_pv": round(pv, 3)}
    if k.ev_tracker_fahrzeug:
        d["fahrzeug"] = k.ev_tracker_fahrzeug
    return d


def adresse(k: Konfig) -> str:
    url = k.ev_tracker_url.rstrip("/")
    return url if url.endswith("/api/ladung") else url + "/api/ladung"


class Uebergabe:
    def __init__(self, konfig: Konfig):
        self.k = konfig
        self.aktiv = bool(konfig.ev_tracker_url and konfig.ev_tracker_token)
        self.letzter_fehler: str | None = None
        self.zuletzt_gesendet: str | None = None
        self.offen = 0
        self._warten = TAKT_S
        self._gemeldet: str | None = None

    async def laufen(self) -> None:
        if not self.aktiv:
            log.info("EV Tracker: keine Adresse/kein Token – Übergabe aus")
            return
        log.info("EV Tracker: Übergabe an %s", adresse(self.k))
        while True:
            try:
                ok = await self.durchlauf()
                self._warten = TAKT_S if ok else min(self._warten * 2, WARTEN_MAX_S)
            except Exception as e:
                log.exception("EV Tracker: Fehler im Durchlauf")
                self._fehler(f"interner Fehler: {e}")
                self._warten = min(self._warten * 2, WARTEN_MAX_S)
            await asyncio.sleep(self._warten)

    async def durchlauf(self, sitzung: aiohttp.ClientSession | None = None) -> bool:
        """Sendet alle offenen Vorgaenge. True = alles erledigt (oder nichts zu tun)."""
        offen = db.vorgaenge_ungesendet()
        self.offen = len(offen)
        if not offen:
            return True
        eigene = sitzung is None
        sitzung = sitzung or aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=TIMEOUT_S))
        try:
            for v in offen:
                if not await self._senden(sitzung, v):
                    return False
            return True
        finally:
            self.offen = len(db.vorgaenge_ungesendet())
            if eigene:
                await sitzung.close()

    async def _senden(self, sitzung, v: dict) -> bool:
        daten = nutzlast(v, self.k)
        if daten is None:
            db.vorgang_gesendet(v["id"], "nicht gesendet: keine Energie")
            return True
        try:
            async with sitzung.post(adresse(self.k), json=daten,
                                    headers={"Authorization": f"Bearer {self.k.ev_tracker_token}"}) as r:
                text = await r.text()
                status = r.status
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            self._fehler(f"Tracker nicht erreichbar: {type(e).__name__} {e}".strip())
            return False
        if 200 <= status < 300:
            jetzt = datetime.now().astimezone().isoformat(timespec="seconds")
            db.vorgang_gesendet(v["id"], jetzt)
            self.zuletzt_gesendet, self.letzter_fehler, self._gemeldet = jetzt, None, None
            text_ok = (f"Ladung {v['start'][:16]} an EV Tracker übergeben: "
                       f"{daten['kwh_pv']:.2f} kWh PV, {daten['kwh_netz']:.2f} kWh Netz")
            log.info(text_ok)
            db.ereignis("info", "tracker", text_ok)
            return True
        grund = _grund(text) or f"HTTP {status}"
        if status in (401, 403):
            self._fehler(f"Tracker lehnt ab ({status}): {grund} – Token in den Optionen prüfen")
            return False
        if 400 <= status < 500:
            db.vorgang_gesendet(v["id"], f"abgelehnt: {grund}"[:200])
            db.ereignis("warnung", "tracker", f"Ladung {v['start'][:16]} vom Tracker abgelehnt: {grund}")
            return True
        self._fehler(f"Tracker-Fehler {status}: {grund}")
        return False

    def _fehler(self, text: str) -> None:
        self.letzter_fehler = text
        if text != self._gemeldet:      # nicht bei jedem Wiederholen ins Protokoll
            self._gemeldet = text
            log.warning("EV Tracker: %s", text)
            db.ereignis("warnung", "tracker", text)

    def status(self) -> dict:
        return {"aktiv": self.aktiv, "adresse": adresse(self.k) if self.aktiv else None,
                "offen": self.offen, "zuletzt_gesendet": self.zuletzt_gesendet,
                "fehler": self.letzter_fehler}


def _grund(text: str) -> str:
    try:
        import json
        d = json.loads(text)
        return str(d.get("error") or d.get("fehler") or "")[:200]
    except Exception:
        return text.strip()[:200]
