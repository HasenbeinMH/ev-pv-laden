# -*- coding: utf-8 -*-
"""
Laufzeit: alles, was zwischen Start und Stopp des Add-ons lebt.
Konfiguration -> Protokoll -> Datenbank -> Prozessabbild -> HA-Verbindung ->
Zyklus (1 s): Erfassung/Bilanz + Regelung (Trockenlauf) -> MQTT.
"""
import asyncio
import logging
import os
import time

import datenbank as db
import konfig as konfig_mod
import mqtt_ha
import protokoll
from erfassung import Erfassung
from ha_client import IST_ADDON, HAClient, verbindung_aus_umgebung
from prozessabbild import Prozessabbild
from regelung import Regelung
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
        self._tasks.append(asyncio.create_task(self._zyklus(), name="zyklus"))

        daten = verbindung_aus_umgebung()
        if os.environ.get("EVPV_SIMULATION") and not IST_ADDON:
            # Nur Entwicklung: Anlagenmodell statt Home Assistant
            from simulation import LiveSimulator
            self.simulator = LiveSimulator(self.konfig, self.abbild, self.regelung)
            self.ha_fehler = "Simulation (EVPV_SIMULATION) – keine Verbindung zu Home Assistant"
            log.warning(self.ha_fehler)
        elif daten is None:
            self.ha_fehler = "Keine Verbindungsdaten (SUPERVISOR_TOKEN bzw. HA_URL/HA_TOKEN fehlen)"
            log.error(self.ha_fehler)
        else:
            self.ha = HAClient(daten, self.abbild.entity_ids, self.abbild.aktualisieren)
            # Bis M5 gibt es keinen Schreibpfad – Sperre unabhaengig vom Trockenlauf gesetzt
            self.ha.schreiben_gesperrt = True
            self._tasks.append(asyncio.create_task(self.ha.laufen(), name="ha_client"))

        zugang = await mqtt_ha.zugang_holen()
        if zugang is None:
            self.mqtt_fehler = "kein MQTT-Broker (HA-Entitaeten werden nicht angelegt)"
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
                if self.erfassung.senden_noetig and self.mqtt:
                    self.mqtt.zustand_setzen({**self.erfassung.mqtt_zustand(),
                                              **self.regelung.mqtt_zustand()})
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
            "signale": self.abbild.uebersicht() if self.abbild else [],
        }
