# -*- coding: utf-8 -*-
"""
Laufzeit: alles, was zwischen Start und Stopp des Add-ons lebt.
Konfiguration -> Protokoll -> Datenbank -> Prozessabbild -> HA-Verbindung ->
Zyklus (1 s): Erfassung/Bilanz -> Regelung (Strategie) -> Treiber (Aktionen) -> MQTT.
Die Aktionen des Treibers werden im Trockenlauf nur protokolliert, sonst asynchron ueber
Home Assistant ausgefuehrt (der Zyklus wartet nicht auf die Antwort).
"""
import asyncio
import logging
import os
import time
from collections import deque
from datetime import datetime

import datenbank as db
import konfig as konfig_mod
import mqtt_ha
import protokoll
from erfassung import Erfassung
from ha_client import IST_ADDON, HAClient, verbindung_aus_umgebung
from prognose import ABFRAGE_S as PROGNOSE_S, Prognose
from pvprognose import PVPrognose
from prozessabbild import Prozessabbild
from regelung import Regelung
from treiber import Aktion, TreiberIds
from version import VERSION

log = logging.getLogger("app")

ZYKLUS_S = 1.0


class Laufzeit:
    def __init__(self):
        self.konfig: konfig_mod.Konfig | None = None
        self.konfig_fehler: list[str] = []
        self.abbild: Prozessabbild | None = None
        self.ha: HAClient | None = None
        self.ha_fehler: str | None = None
        self.erfassung: Erfassung | None = None
        self.regelung: Regelung | None = None
        self.mqtt: mqtt_ha.MqttHA | None = None
        self.mqtt_fehler: str | None = None
        self.gestartet = time.time()
        self.zyklus_fehler: str | None = None
        self.simulator = None
        self.treiber: TreiberIds | None = None
        # PV-Prognose: eigenes Modell; die HA-Prognose (Energie-Dashboard) dient als Vergleich
        # und als Ersatz, solange das eigene Modell noch nicht trainiert ist
        self.prognose_eigen = Prognose()
        self.prognose_ha = Prognose()
        self.pv: PVPrognose | None = None
        # Letzte Aktionen des Treibers fuer die Oberflaeche: (Zeit, Text, Ergebnis)
        self.aktionen: deque = deque(maxlen=60)
        self._trocken_letzt: frozenset = frozenset()
        self._ids_fehler = 0
        self._tasks: list[asyncio.Task] = []

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
        self.erfassung = Erfassung(self.konfig, self.abbild)
        self.regelung = Regelung(self.konfig, self.abbild)
        self.treiber = TreiberIds(self.konfig, self.konfig.ids_ppv_senden)
        self.regelung.treiber = f"ids{' (Trockenlauf)' if self.konfig.trockenlauf else ''}"
        self._tasks.append(asyncio.create_task(self._zyklus(), name="zyklus"))

        daten = verbindung_aus_umgebung()
        if os.environ.get("EVPV_SIMULATION") and not IST_ADDON:
            # Nur Entwicklung: Anlagenmodell statt Home Assistant
            from simulation import LiveSimulator, prognose_simuliert, pvmodell_demo
            self.simulator = LiveSimulator(self.konfig, self.abbild, self.regelung)
            jetzt = datetime.now(self.erfassung.tz)
            self.prognose_eigen.setzen(prognose_simuliert(jetzt), jetzt)
            self.pv = PVPrognose(self.konfig, self.prognose_eigen)
            self.pv.modell, self.pv.zustand = pvmodell_demo(), "Simulation"
            self.ha_fehler = "Simulation (EVPV_SIMULATION) – keine Verbindung zu Home Assistant"
            log.warning(self.ha_fehler)
        elif daten is None:
            self.ha_fehler = "Keine Verbindungsdaten (SUPERVISOR_TOKEN bzw. HA_URL/HA_TOKEN fehlen)"
            log.error(self.ha_fehler)
        else:
            self.ha = HAClient(daten, self.abbild.entity_ids, self.abbild.aktualisieren)
            # Verriegelung direkt im Client: im Trockenlauf geht kein Dienstaufruf raus
            self.ha.schreiben_gesperrt = self.konfig.trockenlauf
            self._tasks.append(asyncio.create_task(self.ha.laufen(), name="ha_client"))
            self._tasks.append(asyncio.create_task(self._prognose_holen(), name="prognose"))
            self.pv = PVPrognose(self.konfig, self.prognose_eigen)
            self._tasks.append(asyncio.create_task(self.pv.laufen(self.ha), name="pvmodell"))

        zugang = await mqtt_ha.zugang_holen()
        if zugang is None:
            self.mqtt_fehler = "kein MQTT-Broker (HA-Entitäten werden nicht angelegt)"
            log.warning(self.mqtt_fehler)
        else:
            self.mqtt = mqtt_ha.MqttHA(zugang)
            self._tasks.append(asyncio.create_task(self.mqtt.laufen(), name="mqtt"))

    async def _zyklus(self) -> None:
        """Feste Zykluszeit wie eine SPS-Task; ein Fehler im Zyklus beendet ihn nicht."""
        naechster = time.monotonic()
        while True:
            try:
                if self.simulator:
                    self.simulator.schritt(time.monotonic())
                if self.ha and self.ha.zeitzone:
                    self.erfassung.zeitzone_setzen(self.ha.zeitzone)
                self.erfassung.zyklus()
                vorher = self.regelung.aus
                a = self.regelung.zyklus()
                if vorher is None or (vorher.freigabe, vorher.zustand) != (a.freigabe, a.zustand):
                    self.erfassung.senden_noetig = True
                mono = time.monotonic()
                werte = {n: self.abbild.wert(n, mono) for n in self.abbild.werte}
                self._ausfuehren(self.treiber.zyklus(mono, self.regelung.param.modus, a,
                                                     self.regelung.pgrid_v, werte))
                if self.erfassung.senden_noetig and self.mqtt:
                    self.mqtt.zustand_setzen({**self.erfassung.mqtt_zustand(),
                                              **self.regelung.mqtt_zustand(),
                                              **self._pv_mqtt()})
                self.erfassung.senden_noetig = False
                self.zyklus_fehler = None
            except Exception as e:
                if self.zyklus_fehler != str(e):
                    log.exception("Fehler im Erfassungszyklus")
                self.zyklus_fehler = str(e)
            naechster += ZYKLUS_S
            await asyncio.sleep(max(naechster - time.monotonic(), 0))
            if time.monotonic() - naechster > 5 * ZYKLUS_S:
                naechster = time.monotonic()   # nach Haenger nicht nachholen

    async def _prognose_holen(self) -> None:
        """PV-Prognose alle 15 min (sobald HA verbunden ist)."""
        while True:
            if self.ha and self.ha.verbunden:
                try:
                    antwort = await self.ha.anfrage({"type": "energy/solar_forecast"})
                    self.prognose_ha.setzen(antwort or {}, datetime.now(self.erfassung.tz))
                    if self.prognose_ha.fehler:
                        log.info("PV-Prognose (HA): %s", self.prognose_ha.fehler)
                    await asyncio.sleep(PROGNOSE_S)
                    continue
                except Exception as e:
                    self.prognose_ha.fehler = f"Abfrage fehlgeschlagen: {e}"
                    log.warning("PV-Prognose: %s", e)
            await asyncio.sleep(30)

    def _pv_mqtt(self) -> dict:
        p, _ = self.prognose()
        u = p.uebersicht(datetime.now(self.erfassung.tz)) if p.werte else {}
        s = self.pv.modell.sauberkeit if self.pv else None
        return {"pv_prognose_heute": u.get("heute_kwh"), "pv_prognose_rest_heute": u.get("heute_rest_kwh"),
                "pv_prognose_morgen": u.get("morgen_kwh"),
                "pv_sauberkeit": None if s is None else round(s * 100)}

    def prognose(self) -> tuple[Prognose, str]:
        """Angezeigte Prognose: eigenes Modell, sonst HA (Energie-Dashboard)."""
        if self.prognose_eigen.werte:
            return self.prognose_eigen, "eigenes Modell"
        return self.prognose_ha, "Home Assistant (Energie-Dashboard)"

    def _ausfuehren(self, aktionen: list[Aktion]) -> None:
        jetzt = datetime.now().strftime("%H:%M:%S")
        if self.konfig.trockenlauf or self.ha is None:
            for akt in aktionen:
                self.aktionen.append((jetzt, akt.text, "Trockenlauf"))
            # Ereignis nur, wenn sich die geplanten Einstellungen aendern (nicht alle 30 s)
            texte = frozenset(akt.text for akt in aktionen if not akt.ids)
            if texte and texte != self._trocken_letzt:
                db.ereignis("info", "stellglied", "würde schreiben: " + "; ".join(sorted(texte)))
            if texte:
                self._trocken_letzt = texte
            return
        for akt in aktionen:
            asyncio.create_task(self._aufrufen(akt))

    async def _aufrufen(self, akt: Aktion) -> None:
        jetzt = datetime.now().strftime("%H:%M:%S")
        try:
            await self.ha.dienst_aufrufen(akt.domain, akt.service, akt.daten, akt.ziel)
            self.aktionen.append((jetzt, akt.text, "ok"))
            if akt.ids:
                if self._ids_fehler >= 3:
                    db.ereignis("info", "stellglied", "ids wird wieder angenommen")
                self._ids_fehler = 0
            else:
                db.ereignis("info", "stellglied", f"geschrieben: {akt.text}")
        except Exception as e:
            self.aktionen.append((jetzt, akt.text, f"Fehler: {e}"))
            if akt.ids:
                self._ids_fehler += 1
                if self._ids_fehler == 3:
                    log.warning("ids dreimal nicht gesendet: %s", e)
                    db.ereignis("warnung", "stellglied", f"ids wird nicht gesendet: {e}")
            else:
                log.warning("Schreiben fehlgeschlagen (%s): %s", akt.text, e)
                db.ereignis("warnung", "stellglied", f"nicht geschrieben: {akt.text} – {e}")

    async def stoppen(self) -> None:
        for t in reversed(self._tasks):
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        if self.erfassung:
            try:
                self.erfassung.sichern()
            except Exception:
                log.exception("Bilanz beim Beenden nicht gesichert")
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
            "mqtt": {
                "verbunden": bool(self.mqtt and self.mqtt.verbunden),
                "fehler": self.mqtt_fehler or (self.mqtt.letzter_fehler if self.mqtt else None),
            },
            "zyklus_fehler": self.zyklus_fehler,
            "treiber": None if not self.treiber else {
                "name": self.treiber.name, "verriegelt": self.treiber.verriegelt,
                "aktionen": list(self.aktionen)[::-1][:30]},
            "signale": self.abbild.uebersicht() if self.abbild else [],
        }
