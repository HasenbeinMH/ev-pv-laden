# -*- coding: utf-8 -*-
"""
Laufzeit: alles, was zwischen Start und Stopp des Add-ons lebt.
Konfiguration -> Protokoll -> Datenbank -> Prozessabbild -> HA-Verbindung ->
Zyklus (1 s): Erfassung/Bilanz -> Regelung (Strategie) -> Treiberwahl/Wiederanlauf ->
Treiber (Aktionen) -> MQTT.
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
from meldungen import FertigErkennung
from ha_client import IST_ADDON, HAClient, verbindung_aus_umgebung
from prognose import ABFRAGE_S as PROGNOSE_S, Prognose
from pvprognose import PVPrognose
from prozessabbild import Prozessabbild
from regelung import Regelung
from strategie import MIN_PV, NUR_PV
from tagesverlauf import SIGNALE as TAG_SIGNALE, Tagesverlauf, aus_historie, hausverbrauch
from tracker import Uebergabe
from treiber import Aktion, TreiberA, TreiberBasis, TreiberIds
from wiederanlauf import FUP, TREIBER_A, Wiederanlauf
from version import VERSION

log = logging.getLogger("app")

ZYKLUS_S = 1.0
# Domain der HA-Integration, die unsere Prognose ins Energie-Dashboard bringt
PROGNOSE_DOMAIN = "ev_pv_laden_prognose"
TROCKEN_SCHLUESSEL = "trockenlauf_bedienung"
# Treiberwechsel nur, wenn nicht geladen wird (sonst Sprung in der Ladeleistung)
WECHSEL_UNTER_W = 100.0
HALT_TIMEOUT_S = 5.0


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
        self.treiber: TreiberBasis | None = None
        # Ausweich auf Treiber A nach erfolglosem Wiederanlauf – gilt bis zum Abstecken
        self.ausweich_a = False
        self.wiederanlauf = Wiederanlauf()
        self.fertig = FertigErkennung()
        self.tracker: Uebergabe | None = None
        self.tagesverlauf = Tagesverlauf()
        # Trockenlauf in zwei Stufen wie Hauptschalter + Betriebsartenwahl: die Add-on-Option
        # sperrt fest; nur wenn sie aus ist, schaltet die Bedienung (Oberflaeche/HA) –
        # gespeichert, Anfangswert "an"
        self.trocken_bedienung = True
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
        gespeichert = db.einstellung(TROCKEN_SCHLUESSEL)
        self.trocken_bedienung = True if gespeichert is None else bool(gespeichert)
        db.ereignis("info", "start", f"Add-on {VERSION} gestartet, Trockenlauf "
                                     f"{'an' if self.trockenlauf else 'AUS'}"
                                     + (" (Add-on-Option)" if self.konfig.trockenlauf else ""))

        self.abbild = Prozessabbild(self.konfig)
        self.erfassung = Erfassung(self.konfig, self.abbild)
        self.regelung = Regelung(self.konfig, self.abbild)
        self._treiber_setzen(self.regelung.param.treiber)
        self._tasks.append(asyncio.create_task(self._zyklus(), name="zyklus"))
        self.tracker = Uebergabe(self.konfig)
        self._tasks.append(asyncio.create_task(self.tracker.laufen(), name="tracker"))

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
            self.ha.schreiben_gesperrt = self.trockenlauf
            self._tasks.append(asyncio.create_task(self.ha.laufen(), name="ha_client"))
            self._tasks.append(asyncio.create_task(self._prognose_holen(), name="prognose"))
            self._tasks.append(asyncio.create_task(self._heute_vorfuellen(), name="heute"))
            self.pv = PVPrognose(self.konfig, self.prognose_eigen)
            self._tasks.append(asyncio.create_task(self.pv.laufen(self.ha), name="pvmodell"))

        zugang = await mqtt_ha.zugang_holen()
        if zugang is None:
            self.mqtt_fehler = "kein MQTT-Broker (HA-Entitäten werden nicht angelegt)"
            log.warning(self.mqtt_fehler)
        else:
            self.mqtt = mqtt_ha.MqttHA(zugang, self._befehl)
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
                self.regelung.tz = self.erfassung.tz
                self.erfassung.zyklus()
                vorher = self.regelung.aus
                a = self.regelung.zyklus()
                if vorher is None or (vorher.freigabe, vorher.zustand) != (a.freigabe, a.zustand):
                    self.erfassung.senden_noetig = True
                mono = time.monotonic()
                werte = {n: self.abbild.wert(n, mono) for n in self.abbild.werte}
                aktionen = self._wiederanlauf(mono, a, werte)
                if self._treiber_waehlen(werte):
                    self.erfassung.senden_noetig = True
                self._ausfuehren(aktionen + self.treiber.zyklus(mono, self.regelung.modus_wirksam, a,
                                                                self.regelung.pgrid_v, werte))
                self._meldungen(werte)
                self.tagesverlauf.hinzufuegen(time.time(), {
                    "pv": werte.get("pv_w"), "netz": werte.get("netz_w"), "akku": werte.get("akku_w"),
                    "auto": werte.get("auto_w"),
                    "haus": hausverbrauch(werte, self.konfig.sensor_haus_enthaelt_auto)})
                if self.erfassung.senden_noetig and self.mqtt:
                    self.mqtt.zustand_setzen(self.mqtt_zustand())
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

    # -- Treiber -----------------------------------------------------------------------------
    def _treiber_setzen(self, schluessel: str) -> None:
        """Neue Instanz = sauberer Anfangszustand (wie ein Instanz-DB nach dem Laden)."""
        self.treiber = (TreiberA(self.konfig) if schluessel == "a"
                        else TreiberIds(self.konfig, self.konfig.ids_ppv_senden))
        self.regelung.phasen_min_setzen(TreiberA.PHASEN if schluessel == "a" else 1)
        text = self.treiber.name
        if self.ausweich_a and schluessel == "a":
            text += " – Ausweich nach Wiederanlauf"
        self.regelung.treiber = text + (" (Trockenlauf)" if self.trockenlauf else "")
        self.regelung.trockenlauf = self.trockenlauf

    def _treiber_waehlen(self, werte: dict) -> bool:
        """Gewaehlter Treiber (Parameter) bzw. Ausweich A; Wechsel nur ohne Ladung.
        Gibt True zurueck, wenn gewechselt wurde."""
        if self.ausweich_a and werte.get("auto_steckt") is False:
            self.ausweich_a = False
            db.ereignis("info", "treiber", "Auto abgesteckt – Ausweich auf Treiber A beendet")
        soll = "a" if self.ausweich_a else self.regelung.param.treiber
        if soll == self.treiber.schluessel:
            return False
        auto_w = werte.get("auto_w")
        if auto_w is not None and auto_w >= WECHSEL_UNTER_W:
            return False
        alt = self.treiber.name
        self._treiber_setzen(soll)
        log.info("Treiber %s -> %s", alt, self.treiber.name)
        db.ereignis("info", "treiber", f"Treiber {alt} → {self.regelung.treiber}")
        return True

    def _wiederanlauf(self, mono: float, a, werte: dict) -> list[Aktion]:
        p = self.regelung.param
        aktiv = isinstance(self.treiber, TreiberIds) and self.regelung.modus_wirksam in (NUR_PV, MIN_PV)
        b = self.wiederanlauf.zyklus(mono, p.wiederanlauf, p.wiederanlauf_s, aktiv,
                                     a.freigabe and a.zustand == "laedt", werte.get("auto_steckt"),
                                     werte.get("auto_w"), werte.get("auto_status"))
        if b.massnahme is None:
            return []
        stoerung = not b.text.startswith("lädt wieder")
        log.log(logging.WARNING if stoerung else logging.INFO, "Wiederanlauf: %s", b.text)
        db.ereignis("warnung" if stoerung else "info", "wiederanlauf", b.text)
        if b.massnahme == FUP and isinstance(self.treiber, TreiberIds):
            return self.treiber.fup_toggeln(mono)
        if b.massnahme == TREIBER_A:
            self.ausweich_a = True
        return []

    # -- Trockenlauf, Bedienung aus HA, Meldungen --------------------------------------------
    @property
    def trockenlauf(self) -> bool:
        return self.konfig is None or self.konfig.trockenlauf or self.trocken_bedienung

    async def trockenlauf_setzen(self, an: bool) -> list[str]:
        if not an and self.konfig.trockenlauf:
            return ["Trockenlauf ist in den Add-on-Optionen gesperrt (trockenlauf: true)"]
        if an == self.trocken_bedienung:
            return []
        if an and not self.trockenlauf:
            # Vor dem Sperren: Treiber ohne go-e-Watchdog (A) haelt die Ladung an
            await self._sicherer_halt()
        self.trocken_bedienung = an
        db.einstellung_setzen(TROCKEN_SCHLUESSEL, an)
        if self.ha:
            self.ha.schreiben_gesperrt = self.trockenlauf
        self._treiber_setzen(self.treiber.schluessel)
        text = ("Trockenlauf an – es wird nichts geschrieben" if an
                else "Trockenlauf AUS – das Add-on schreibt auf die Wallbox")
        log.warning(text)
        db.ereignis("info" if an else "warnung", "trockenlauf", text)
        self.erfassung.senden_noetig = True
        return []

    async def _befehl(self, schluessel: str, text: str) -> None:
        """Befehl aus HA (MQTT): wie eine Eingabe in der Oberflaeche."""
        try:
            ziel, wert = mqtt_ha.befehl_uebersetzen(schluessel, text)
        except ValueError as e:
            db.ereignis("warnung", "bedienung", f"HA-Befehl {schluessel} abgelehnt: {e}")
            return
        if ziel == "trockenlauf":
            fehler = await self.trockenlauf_setzen(wert)
        elif ziel == "auto_soc":
            fehler = self.regelung.auto_soc_setzen(wert)
        else:
            fehler = self.regelung.parameter_setzen({ziel: wert})
        if fehler:
            db.ereignis("warnung", "bedienung", f"HA-Befehl {schluessel}={text} abgelehnt: {'; '.join(fehler)}")
        self.erfassung.senden_noetig = True    # HA zeigt sofort den wirklich gueltigen Wert

    def mqtt_zustand(self) -> dict:
        r = self.regelung
        return {**self.erfassung.mqtt_zustand(), **r.mqtt_zustand(), **self._pv_mqtt(),
                **(self.tracker.mqtt_zustand() if self.tracker else {}),
                **mqtt_ha.bedien_zustand(r.param, self.trockenlauf, r.soc.soc(self.abbild.wert("goe_eto")))}

    def _meldungen(self, werte: dict) -> None:
        plan = self.regelung.plan
        for art in self.fertig.zyklus(werte.get("auto_steckt"), werte.get("auto_w"),
                                      werte.get("auto_status"), bool(plan and plan.erreicht)):
            daten = self._ladung_zusammenfassung()
            text = {"fertig": "Auto fertig geladen", "ziel_erreicht": "Ziel-SoC erreicht"}[art]
            db.ereignis("info", "meldung", f"{text}: {daten}")
            if self.mqtt:
                self.mqtt.ereignis_senden(art, daten)

    def _ladung_zusammenfassung(self) -> dict:
        r = self.regelung
        soc = r.soc.soc(self.abbild.wert("goe_eto"))
        d = {"soc": None if soc is None else round(soc), "ziel_soc": r.param.ziel_soc}
        offen = self.erfassung.erkennung.offen
        if offen:
            en = self.erfassung.stand().minus(offen.stand_start)
            pv = en.pv + en.akku            # wie beim EV Tracker: Hausakku zaehlt als PV
            d.update(kwh=round(en.eto, 2), kwh_pv=round(pv, 2), kwh_netz=round(en.netz, 2),
                     pv_anteil=round(pv / en.eto * 100) if en.eto > 0 else None,
                     start=offen.start.isoformat(timespec="minutes"))
        return d

    async def _heute_vorfuellen(self) -> None:
        """Tageskurve nach einem Neustart aus der HA-Historie seit Mitternacht nachladen."""
        for _ in range(120):              # bis HA verbunden ist und die Einheiten bekannt sind
            if self.ha and self.ha.verbunden and self.abbild.werte["netz_w"].empfangen is not None:
                break
            await asyncio.sleep(1)
        else:
            log.info("Tageskurve: HA nicht rechtzeitig verbunden – kein Nachladen")
            return
        await asyncio.sleep(3)            # Einheiten aller Signale abwarten
        signale = {n: (self.abbild.werte[n].signal, self.abbild.werte[n].einheit)
                   for n in TAG_SIGNALE if n in self.abbild.werte}
        jetzt = datetime.now(self.erfassung.tz)
        mitternacht = jetzt.replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            antwort = await self.ha.anfrage({
                "type": "history/history_during_period", "start_time": mitternacht.isoformat(),
                "end_time": jetzt.isoformat(), "entity_ids": [s.entity_id for s, _ in signale.values()],
                "minimal_response": True, "no_attributes": True, "significant_changes_only": False,
                "include_start_time_state": True}, timeout=60)
            punkte = await asyncio.to_thread(aus_historie, antwort or {}, signale, mitternacht.timestamp(),
                                             jetzt.timestamp(), self.konfig.sensor_haus_enthaelt_auto)
            n = self.tagesverlauf.vorfuellen(punkte)
            log.info("Tageskurve: %d Minuten seit Mitternacht aus der HA-Historie nachgeladen", n)
        except Exception as e:
            log.warning("Tageskurve: Historie nicht geladen: %s", e)

    async def _prognose_holen(self) -> None:
        """PV-Prognose alle 15 min (sobald HA verbunden ist)."""
        while True:
            if self.ha and self.ha.verbunden:
                try:
                    antwort = await self.ha.anfrage({"type": "energy/solar_forecast"})
                    antwort = await self._ohne_eigene_prognose(antwort or {})
                    self.prognose_ha.setzen(antwort or {}, datetime.now(self.erfassung.tz))
                    if self.prognose_ha.fehler:
                        log.info("PV-Prognose (HA): %s", self.prognose_ha.fehler)
                    await asyncio.sleep(PROGNOSE_S)
                    continue
                except Exception as e:
                    self.prognose_ha.fehler = f"Abfrage fehlgeschlagen: {e}"
                    log.warning("PV-Prognose: %s", e)
            await asyncio.sleep(30)

    async def _ohne_eigene_prognose(self, antwort: dict) -> dict:
        """Die HA-Prognose dient als Vergleich/Ersatz. Ist im Energie-Dashboard die Integration
        „EV PV-Laden Prognose“ zugeordnet, steckt darin unser eigenes Modell – herausrechnen,
        sonst liefe die Prognose im Kreis."""
        try:
            eigene = await self.ha.anfrage({"type": "config_entries/get", "domain": PROGNOSE_DOMAIN})
            ids = {e.get("entry_id") for e in (eigene or [])}
        except Exception as e:
            log.debug("Config-Entries nicht lesbar: %s", e)
            ids = set()
        return {k: v for k, v in antwort.items() if k not in ids}

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
        if self.trockenlauf or self.ha is None:
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
        await self._sicherer_halt()
        for t in reversed(self._tasks):
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        if self.erfassung:
            try:
                self.erfassung.sichern()
            except Exception:
                log.exception("Bilanz beim Beenden nicht gesichert")
        log.info("EV PV-Laden beendet")

    async def _sicherer_halt(self) -> None:
        """Treiber ohne go-e-Watchdog (A): Ladung sperren, bevor das Add-on endet."""
        if not self.treiber:
            return
        for akt in self.treiber.sicherer_halt():
            if self.trockenlauf or self.ha is None or not self.ha.verbunden:
                log.info("Beenden: würde schreiben: %s", akt.text)
                continue
            try:
                await asyncio.wait_for(self.ha.dienst_aufrufen(akt.domain, akt.service, akt.daten, akt.ziel),
                                       HALT_TIMEOUT_S)
                log.info("Beenden: geschrieben: %s", akt.text)
                db.ereignis("info", "stellglied", f"geschrieben: {akt.text}")
            except Exception as e:
                log.error("Beenden: %s nicht geschrieben: %s", akt.text, e)

    def status(self) -> dict:
        k = self.konfig
        return {
            "version": VERSION,
            "addon": IST_ADDON,
            "laufzeit_s": round(time.time() - self.gestartet),
            "konfig_ok": not self.konfig_fehler,
            "konfig_fehler": self.konfig_fehler,
            "trockenlauf": self.trockenlauf,
            "trockenlauf_option": k.trockenlauf if k else True,
            "haus_enthaelt_auto": k.sensor_haus_enthaelt_auto if k else True,
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
            "tracker": self.tracker.status() if self.tracker else None,
            "treiber": None if not self.treiber else {
                "name": self.treiber.name, "verriegelt": self.treiber.verriegelt,
                "ausweich_a": self.ausweich_a, "wiederanlauf": self.wiederanlauf.zustand,
                "aktionen": list(self.aktionen)[::-1][:30]},
            "signale": self.abbild.uebersicht() if self.abbild else [],
        }
