# -*- coding: utf-8 -*-
"""
Erfassungszyklus (M3): laeuft jede Sekunde, liest nur aus dem Prozessabbild.
  - Bilanz: Leistung aufteilen, integrieren, auf eto-Anstiege buchen
  - Tagesbilanz und Zaehler in der Datenbank (Zaehler nur steigend)
  - Ladevorgaenge erkennen und speichern
  - Ueberwachung: ama der Wallbox gegen die konfigurierte Grenze
  - Zustand fuer MQTT/Oberflaeche bereitstellen

Schreibt nichts auf die Wallbox.
"""
import logging
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import datenbank as db
from bilanz import QUELLEN, Bilanz, BilanzZustand, aufteilen
from konfig import Konfig
from ladevorgang import Erkennung, Stand, Vorgang
from prozessabbild import Prozessabbild

log = logging.getLogger("erfassung")

# Datenbank hoechstens so oft schreiben (SD-Karte schonen). Geht bei einem Absturz
# etwas verloren, bucht die Bilanz den Rest beim Neustart "ohne Aufteilung" als Netz –
# die Summe stimmt weiter mit dem Wallbox-Zaehler.
SICHERN_S = 60.0
# MQTT: spaetestens alle ... Sekunden senden (Lebenszeichen fuer den Watchdog)
SENDEN_S = 10.0


def zeitzone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "Europe/Berlin")
    except (ZoneInfoNotFoundError, ValueError):
        log.warning("Zeitzone '%s' unbekannt – verwende Europe/Berlin", name)
        return ZoneInfo("Europe/Berlin")


class Erfassung:
    def __init__(self, konfig: Konfig, abbild: Prozessabbild):
        self.konfig = konfig
        self.abbild = abbild
        self.tz = zeitzone(None)
        gespeichert = db.bilanz_laden()
        self.bilanz = Bilanz(BilanzZustand.aus_dict(gespeichert) if gespeichert else None,
                             nach_neustart=gespeichert is not None)
        self.erkennung = Erkennung()
        offen = db.vorgang_offen()
        if offen:
            # Laufende Ladung ueber den Neustart retten; endet nach 15 min ohne Leistung
            self.erkennung.offen = Vorgang(datetime.fromisoformat(offen["start"]),
                                           Stand(**offen["stand_start"]), offen["modus"] or "",
                                           datetime.now(self.tz).replace(tzinfo=None), offen["id"])
            log.info("Offene Ladung seit %s fortgesetzt", offen["start"])
        self.live: dict[str, float] | None = None
        self._trapez_gesichert = self.bilanz.z.kwh_trapez
        self._zuletzt_gesichert = time.monotonic()
        self._zuletzt_gesendet = 0.0
        self._ama_gemeldet: float | None = None
        # Tagesbuchungen seit dem letzten Sichern: {datum: {pv, akku, netz, ohne, eto}}
        self._offen_tag: dict[str, dict] = {}
        self.senden_noetig = True

    def zeitzone_setzen(self, name: str | None) -> None:
        tz = zeitzone(name)
        if str(tz) != str(self.tz):
            log.info("Zeitzone aus Home Assistant: %s", tz)
            self.tz = tz

    def stand(self) -> Stand:
        z = self.bilanz.z
        return Stand(z.kwh["pv"], z.kwh["akku"], z.kwh["netz"], z.kwh_ohne_aufteilung,
                     z.kwh_eto, z.kwh_trapez)

    def zyklus(self, mono: float | None = None, lokal: datetime | None = None) -> None:
        mono = time.monotonic() if mono is None else mono
        lokal = lokal or datetime.now(self.tz).replace(tzinfo=None)
        pa = self.abbild
        p_auto = pa.wert("auto_w", mono)
        netz = pa.wert("netz_w", mono)
        # Ohne konfigurierten Akku-Sensor gibt es keinen Akku: 0 statt "ungueltig"
        akku = pa.wert("akku_w", mono) if "akku_w" in pa.werte else 0.0

        self.bilanz.schritt(mono, p_auto, netz, akku)
        self.live = (aufteilen(p_auto, netz, akku)
                     if None not in (p_auto, netz, akku) else None)

        tag = lokal.strftime("%Y-%m-%d")
        eto = pa.wert("goe_eto", mono)
        if eto is not None:
            buchung = self.bilanz.eto(mono, eto)
            if buchung is not None:
                self._buchung_sichern(tag, buchung)

        if mono - self._zuletzt_gesichert >= SICHERN_S:
            self._sichern(tag)

        for e in self.erkennung.schritt(lokal, p_auto, pa.wert("auto_steckt", mono), self.stand()):
            self._ladevorgang(e)

        self._ama_pruefen(pa.wert("goe_ama", mono))
        if mono - self._zuletzt_gesendet >= SENDEN_S:
            self.senden_noetig = True
        if self.senden_noetig:
            self._zuletzt_gesendet = mono

    # -- Speichern ------------------------------------------------------------------------
    def _buchung_sichern(self, tag: str, buchung) -> None:
        delta = sum(buchung.kwh.values())
        if delta > 0:
            t = self._offen_tag.setdefault(tag, {"pv": 0.0, "akku": 0.0, "netz": 0.0,
                                                 "ohne": 0.0, "eto": 0.0})
            for q in QUELLEN:
                t[q] += buchung.kwh[q]
            t["eto"] += delta
            if buchung.art == "ohne_aufteilung":
                t["ohne"] += delta
        if len(self._offen_tag) > 1:   # Tageswechsel: alten Tag sofort abschliessen
            self._sichern(tag)
        self.senden_noetig = True
        if buchung.art == "neu_angesetzt":
            ebene = "info" if buchung.hinweis == "erster Zaehlerstand" else "warnung"
            self._ereignis(ebene, "bilanz", f"Zaehler neu angesetzt: {buchung.hinweis}")
        elif buchung.art == "ohne_aufteilung":
            self._ereignis("warnung", "bilanz",
                           f"{delta:.3f} kWh ohne Aufteilung als Netz gebucht ({buchung.hinweis})")

    def _sichern(self, tag: str) -> None:
        """Zustand, Zaehler und gesammelte Tagesbuchungen in einer Transaktion je Tag."""
        trapez = self.bilanz.z.kwh_trapez - self._trapez_gesichert
        offen = self._offen_tag or {tag: None}
        for i, (datum, buchung) in enumerate(sorted(offen.items())):
            # Trapez-Anteil dem aktuellen Tag zuschlagen (Plausibilitaet, keine Abrechnung)
            db.bilanz_speichern(self.bilanz.z.als_dict(), datum, buchung,
                                trapez if datum == tag or (i == len(offen) - 1) else 0.0)
        self._offen_tag = {}
        self._trapez_gesichert = self.bilanz.z.kwh_trapez
        self._zuletzt_gesichert = time.monotonic()

    def sichern(self) -> None:
        """Beim Beenden des Add-ons."""
        self._sichern(datetime.now(self.tz).strftime("%Y-%m-%d"))

    def _ladevorgang(self, e) -> None:
        # Ladung beginnt/endet: Bilanz vorher sichern, damit Ladung und Zaehler zusammenpassen
        self._sichern(e.vorgang.start.strftime("%Y-%m-%d") if e.art == "start"
                      else e.ende.strftime("%Y-%m-%d"))
        v = e.vorgang
        if e.art == "start":
            v.id = db.vorgang_anlegen(v.start.isoformat(timespec="seconds"),
                                      v.stand_start.__dict__, v.modus)
            self._ereignis("info", "ladung", f"Ladung erkannt ab {v.start:%d.%m. %H:%M}")
        else:
            en = e.energie
            if v.id is not None:
                db.vorgang_beenden(v.id, e.ende.isoformat(timespec="seconds"), en.__dict__, e.grund)
            self._ereignis("info", "ladung",
                           f"Ladung beendet ({e.grund}): {en.eto:.2f} kWh – PV {en.pv:.2f}, "
                           f"Akku {en.akku:.2f}, Netz {en.netz:.2f}")

    def _ama_pruefen(self, ama: float | None) -> None:
        """marq24 kann ama nach einem HA-Neustart auf 16 A setzen ("16A checker")."""
        if ama is None or ama == self._ama_gemeldet:
            return
        self._ama_gemeldet = ama
        if ama > self.konfig.max_strom_a:
            self._ereignis("warnung", "ueberwachung",
                           f"ama der Wallbox {ama:.0f} A liegt UEBER der Grenze {self.konfig.max_strom_a} A")
        elif ama < self.konfig.max_strom_a:
            self._ereignis("warnung", "ueberwachung",
                           f"ama der Wallbox {ama:.0f} A begrenzt unter {self.konfig.max_strom_a} A "
                           f"(evtl. 16A-Checker von marq24 – in der go-e-App auf "
                           f"{self.konfig.max_strom_a} A setzen)")
        else:
            self._ereignis("info", "ueberwachung", f"ama der Wallbox = {ama:.0f} A")

    def _ereignis(self, ebene: str, quelle: str, text: str) -> None:
        getattr(log, "warning" if ebene == "warnung" else "info")(text)
        db.ereignis(ebene, quelle, text)

    # -- Ausgabe --------------------------------------------------------------------------
    def mqtt_zustand(self) -> dict:
        z, live = self.bilanz.z, self.live
        return {
            **{f"kwh_{q}": round(z.kwh[q], 5) for q in QUELLEN},
            "kwh_ohne_aufteilung": round(z.kwh_ohne_aufteilung, 5),
            **{f"leistung_{q}": (round(live[q]) if live else None) for q in QUELLEN},
            "lebenszeichen": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    def uebersicht(self) -> dict:
        z = self.bilanz.z
        offen = self.erkennung.offen
        ladung = None
        if offen:
            en = self.stand().minus(offen.stand_start)
            ladung = {"start": offen.start.isoformat(timespec="seconds"), **en.__dict__}
        return {
            "zaehler": {**{q: z.kwh[q] for q in QUELLEN}, "ohne": z.kwh_ohne_aufteilung,
                        "unsicher": z.kwh_unsicher, "eto": z.kwh_eto, "trapez": z.kwh_trapez},
            "live": self.live,
            "ladung": ladung,
            "tage": db.bilanz_tage(14),
            "vorgaenge": db.vorgaenge(20),
        }
