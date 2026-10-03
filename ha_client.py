# -*- coding: utf-8 -*-
"""
Home-Assistant-Client (asynchron, WebSocket).

Messwerte kommen als Push ueber "subscribe_entities" (komprimiertes Format, geprueft
gegen homeassistant/components/websocket_api/messages.py):
  {"a": {eid: {"s": state, "a": attrs, "lc": ts, "lu": ts?}}}  -> Erstbestand / neu
  {"c": {eid: {"+": {...geaendert...}, "-": {"a": [entfernte Attribute]}}}}
  {"r": [eid, ...]}                                           -> entfernt
HA sendet nur bei state_changed – ein Sensor, der denselben Wert erneut meldet
(state_reported), erzeugt kein Ereignis. Deshalb gibt es im Prozessabbild das
"Lebenszeichen" eines anderen Sensors desselben Geraets.

Dienste (spaeter: Schreiben auf die Wallbox ueber marq24) laufen ueber dieselbe
Verbindung ("call_service"). Solange schreiben_gesperrt gesetzt ist (Trockenlauf),
wird jeder Dienstaufruf hier verweigert – Verriegelung direkt am Stellglied, nicht
nur in der Strategie.

Verbindung:
  Add-on:     SUPERVISOR_TOKEN (vom Supervisor, homeassistant_api: true)
              -> ws://supervisor/core/websocket
  Entwicklung: HA_URL + HA_TOKEN (Long-Lived Access Token) als Umgebungsvariablen
"""
import asyncio
import itertools
import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass

import aiohttp

log = logging.getLogger("ha")

# Wiederverbinden: 1 s, 2 s, 4 s ... hoechstens 30 s
WARTEN_MIN_S, WARTEN_MAX_S = 1, 30
# Antwortzeit fuer einen einzelnen Befehl (auth, subscribe, call_service)
ANTWORT_TIMEOUT_S = 10
# WebSocket-Ping: erkennt eine haengende Verbindung, auch wenn kein Messwert kommt
HEARTBEAT_S = 20

IST_ADDON = bool(os.environ.get("SUPERVISOR_TOKEN"))


class SchreibschutzAktiv(Exception):
    """Dienstaufruf im Trockenlauf – es wird nichts geschrieben."""


class HAFehler(Exception):
    """HA hat einen Befehl mit Fehler beantwortet oder ist nicht erreichbar."""


@dataclass(frozen=True)
class Verbindungsdaten:
    ws_url: str
    token: str


def verbindung_aus_umgebung() -> Verbindungsdaten | None:
    if IST_ADDON:
        return Verbindungsdaten("ws://supervisor/core/websocket", os.environ["SUPERVISOR_TOKEN"])
    url, token = os.environ.get("HA_URL", "").rstrip("/"), os.environ.get("HA_TOKEN", "")
    if url and token:
        ws = url.replace("https://", "wss://").replace("http://", "ws://")
        return Verbindungsdaten(ws + "/api/websocket", token)
    return None


def zustand_anwenden(bestand: dict, ereignis: dict) -> list[str]:
    """Wendet ein subscribe_entities-Ereignis auf bestand {eid: {"s","a","lc","lu"}} an.
    Gibt die betroffenen Entity-IDs zurueck. Reine Funktion – getrennt testbar."""
    betroffen = []
    for eid, z in (ereignis.get("a") or {}).items():
        bestand[eid] = {"s": z.get("s"), "a": dict(z.get("a") or {}),
                        "lc": z.get("lc"), "lu": z.get("lu", z.get("lc"))}
        betroffen.append(eid)
    for eid, diff in (ereignis.get("c") or {}).items():
        alt = bestand.setdefault(eid, {"s": None, "a": {}, "lc": None, "lu": None})
        plus, minus = diff.get("+") or {}, diff.get("-") or {}
        if "s" in plus:
            alt["s"] = plus["s"]
        if "a" in plus:
            alt["a"].update(plus["a"])
        for schluessel in minus.get("a") or []:
            alt["a"].pop(schluessel, None)
        if "lc" in plus:
            alt["lc"] = alt["lu"] = plus["lc"]
        elif "lu" in plus:
            alt["lu"] = plus["lu"]
        betroffen.append(eid)
    for eid in ereignis.get("r") or []:
        bestand.pop(eid, None)
        betroffen.append(eid)
    return betroffen


class HAClient:
    def __init__(self, daten: Verbindungsdaten, entity_ids: list[str],
                 rueckruf: Callable[[str, dict | None, float], None]):
        """rueckruf(entity_id, zustand oder None wenn entfernt, Empfangszeit monotonic)"""
        self.daten = daten
        self.entity_ids = sorted(set(entity_ids))
        self.rueckruf = rueckruf
        self.schreiben_gesperrt = True
        self.verbunden = False
        self.letzter_fehler: str | None = None
        self.ha_version: str | None = None
        self.zeitzone: str | None = None      # aus get_config, fuer Tagesgrenzen
        self._bestand: dict[str, dict] = {}
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._ids = itertools.count(1)
        self._offen: dict[int, asyncio.Future] = {}
        self._abo_id: int | None = None
        self._config_id: int | None = None

    async def laufen(self) -> None:
        """Dauerschleife mit Wiederverbinden. Als Task starten, mit cancel() beenden."""
        warten = WARTEN_MIN_S
        async with aiohttp.ClientSession() as sitzung:
            while True:
                try:
                    await self._sitzung(sitzung)
                    warten = WARTEN_MIN_S
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # Netz, Auth, Protokoll – alles fuehrt zum Neuaufbau
                    self.letzter_fehler = f"{type(e).__name__}: {e}"
                    log.warning("Verbindung zu Home Assistant: %s – neuer Versuch in %d s",
                                self.letzter_fehler, warten)
                finally:
                    self._getrennt()
                await asyncio.sleep(warten)
                warten = min(warten * 2, WARTEN_MAX_S)

    def _getrennt(self) -> None:
        if self.verbunden:
            log.warning("Verbindung zu Home Assistant getrennt")
        self.verbunden = False
        self._ws = None
        for fut in self._offen.values():
            if not fut.done():
                fut.set_exception(HAFehler("Verbindung getrennt"))
        self._offen.clear()
        # Ohne Verbindung gibt es keine gueltigen Werte: allen Abnehmern melden
        jetzt = time.monotonic()
        for eid in list(self._bestand):
            self.rueckruf(eid, None, jetzt)
        self._bestand.clear()

    async def _sitzung(self, sitzung: aiohttp.ClientSession) -> None:
        async with sitzung.ws_connect(self.daten.ws_url, heartbeat=HEARTBEAT_S,
                                      max_msg_size=0) as ws:
            # Anmeldung: auth_required -> auth -> auth_ok
            hallo = await asyncio.wait_for(ws.receive_json(), ANTWORT_TIMEOUT_S)
            if hallo.get("type") != "auth_required":
                raise HAFehler(f"unerwartete Begruessung: {hallo}")
            await ws.send_json({"type": "auth", "access_token": self.daten.token})
            antwort = await asyncio.wait_for(ws.receive_json(), ANTWORT_TIMEOUT_S)
            if antwort.get("type") != "auth_ok":
                raise HAFehler(f"Anmeldung abgelehnt: {antwort.get('message', antwort)}")
            self.ha_version = antwort.get("ha_version")
            self._ws = ws

            self._config_id = next(self._ids)
            await ws.send_json({"id": self._config_id, "type": "get_config"})
            self._abo_id = next(self._ids)
            await ws.send_json({"id": self._abo_id, "type": "subscribe_entities",
                                "entity_ids": self.entity_ids})
            self.verbunden, self.letzter_fehler = True, None
            log.info("Mit Home Assistant %s verbunden, %d Entitaeten abonniert",
                     self.ha_version, len(self.entity_ids))

            async for nachricht in ws:
                if nachricht.type == aiohttp.WSMsgType.TEXT:
                    self._verarbeiten(json.loads(nachricht.data))
                elif nachricht.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    raise HAFehler(f"WebSocket {nachricht.type.name}")

    def _verarbeiten(self, nachricht: dict) -> None:
        # HA buendelt bei Last mehrere Nachrichten in einer Liste
        if isinstance(nachricht, list):
            for n in nachricht:
                self._verarbeiten(n)
            return
        art, nid = nachricht.get("type"), nachricht.get("id")
        if art == "event" and nid == self._abo_id:
            jetzt = time.monotonic()
            for eid in zustand_anwenden(self._bestand, nachricht.get("event") or {}):
                self.rueckruf(eid, self._bestand.get(eid), jetzt)
        elif art == "result":
            if nid == self._config_id:
                if nachricht.get("success"):
                    self.zeitzone = (nachricht.get("result") or {}).get("time_zone")
            elif nid == self._abo_id:
                if not nachricht.get("success"):
                    raise HAFehler(f"subscribe_entities abgelehnt: {nachricht.get('error')}")
            elif (fut := self._offen.pop(nid, None)) and not fut.done():
                if nachricht.get("success"):
                    fut.set_result(nachricht.get("result"))
                else:
                    fut.set_exception(HAFehler(str(nachricht.get("error"))))

    async def dienst_aufrufen(self, domain: str, service: str, daten: dict | None = None,
                              ziel: dict | None = None) -> dict | None:
        """call_service ueber die bestehende Verbindung. Im Trockenlauf gesperrt."""
        if self.schreiben_gesperrt:
            raise SchreibschutzAktiv(f"{domain}.{service} im Trockenlauf nicht ausgefuehrt")
        if not self._ws or not self.verbunden:
            raise HAFehler("keine Verbindung zu Home Assistant")
        nid = next(self._ids)
        befehl = {"id": nid, "type": "call_service", "domain": domain, "service": service,
                  "service_data": daten or {}}
        if ziel:
            befehl["target"] = ziel
        fut = asyncio.get_running_loop().create_future()
        self._offen[nid] = fut
        await self._ws.send_json(befehl)
        try:
            return await asyncio.wait_for(fut, ANTWORT_TIMEOUT_S)
        finally:
            self._offen.pop(nid, None)
