# -*- coding: utf-8 -*-
"""
PV-Prognose zur Laufzeit (eigenes Modell, siehe pvmodell.py).

  Training     beim ersten Start und danach woechentlich: HA-Statistik (bis 3 Jahre) +
               archivierte Open-Meteo-Prognosen + Open-Meteo-Archiv
  Sauberkeit   taeglich aus den letzten 14 Tagen (bzw. seit der letzten Reinigung)
  Prognose     stuendlich: Open-Meteo-Prognose x Kennfeld (x Zuschlag nach Reinigung)
Das Modell liegt in der Datenbank (Einstellung "pvmodell"), nicht im Repo – die
Anlagendaten bleiben lokal.
"""
import asyncio
import logging
import time
from datetime import date, datetime, timedelta, timezone

import aiohttp

import datenbank as db
import morgentau
import pvdaten
import wochenprognose
import pvmodell as pm
from prognose import Prognose

log = logging.getLogger("pvprognose")

SCHLUESSEL = "pvmodell"
TAU_PROTOKOLL = "morgentau_protokoll"   # je Tag Klasse und Morgenprognose (fuer das Nachjustieren)
TAU_PROTOKOLL_TAGE = 120
VERBRAUCH_S = 24 * 3600                 # Hausprofil und Akkubedarf einmal am Tag neu
PROGNOSE_TAGE = 8                       # heute + 7 Tage (Vorschau "lohnt sich das Laden?")
TRAINING_TAGE = 3 * 365
NEU_TRAINIEREN_TAGE = 7
PROGNOSE_S = 3600
SAUBERKEIT_S = 24 * 3600
# Startwert der Zeitgeber: "noch nie". Nicht 0.0 – time.monotonic() zaehlt ab Systemstart,
# kurz nach einem Neustart des Hosts waere sonst alles noch "gerade erst erledigt".
NIE = float("-inf")
TAKT_S = 60


class PVPrognose:
    def __init__(self, konfig, ziel: Prognose):
        self.konfig = konfig
        self.ziel = ziel                      # Prognose-Objekt, das Oberflaeche/MQTT lesen
        self.flaechen = pvdaten.flaechen_aus_konfig(konfig.pv_flaechen)
        self.modell = pm.Modell.aus_dict(db.einstellung(SCHLUESSEL))
        self.zustand = "wartet auf Home Assistant"
        self.fehler: str | None = None
        self.training_laeuft = False
        self._zuletzt_prognose = NIE
        self._zuletzt_sauberkeit = NIE
        self._zuletzt_training_versuch = NIE
        self.tau: dict[date, dict] = {}         # Morgentau je Tag (Anzeige, Protokoll)
        self.woche: list[dict] = []             # 7-Tage-Vorschau
        self.haus_profil: dict[int, float] = {}
        self.akku_bedarf: float | None = None
        self._zuletzt_verbrauch = NIE

    @property
    def _modelle(self) -> tuple[str, ...]:
        return pvdaten.WETTERMODELLE.get(self.konfig.wettermodell, ("best_match",))

    @property
    def aktiv(self) -> bool:
        return bool(self.flaechen)

    def _sichern(self) -> None:
        db.einstellung_setzen(SCHLUESSEL, self.modell.als_dict())

    # ── Ablauf ───────────────────────────────────────────────────────────────────────
    async def laufen(self, ha) -> None:
        if not self.aktiv:
            self.zustand = "keine Dachflaechen konfiguriert"
            return
        async with aiohttp.ClientSession() as sitzung:
            while True:
                try:
                    if ha.verbunden and ha.standort and ha.zeitzone:
                        await self._schritt(ha, sitzung)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    self.fehler = f"{type(e).__name__}: {e}"
                    log.warning("PV-Prognose: %s", self.fehler)
                await asyncio.sleep(TAKT_S)

    async def _schritt(self, ha, sitzung) -> None:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(ha.zeitzone)
        jetzt = time.monotonic()
        alt = (not self.modell.trainiert or not self.modell.trainiert_am or
               self.modell.wettermodell != self.konfig.wettermodell or     # Option geaendert
               (datetime.now(timezone.utc) - datetime.fromisoformat(self.modell.trainiert_am)).days
               >= NEU_TRAINIEREN_TAGE)
        if alt and jetzt - self._zuletzt_training_versuch > 6 * 3600:
            self._zuletzt_training_versuch = jetzt
            await self.trainieren(ha, sitzung, tz)
        if not self.modell.trainiert:
            self.zustand = "nicht trainiert"
            return
        if jetzt - self._zuletzt_sauberkeit > SAUBERKEIT_S:
            self._zuletzt_sauberkeit = jetzt
            await self.sauberkeit_aktualisieren(ha, sitzung, tz)
        if jetzt - self._zuletzt_prognose > PROGNOSE_S:
            self._zuletzt_prognose = jetzt
            await self.prognose_aktualisieren(ha, sitzung, tz)
        self.zustand = "aktiv"

    # ── Training ─────────────────────────────────────────────────────────────────────
    async def trainieren(self, ha, sitzung, tz) -> None:
        self.training_laeuft, self.zustand = True, "Training laeuft"
        lat, lon = ha.standort
        try:
            ende_tag = pvdaten.gestern()
            start = datetime.now(timezone.utc) - timedelta(days=TRAINING_TAGE)
            ende = datetime(ende_tag.year, ende_tag.month, ende_tag.day, tzinfo=timezone.utc)
            log.info("PV-Modell: Training mit Daten ab %s", start.date())
            mess = await pvdaten.pv_messung(ha, self.konfig, start, ende)
            if not mess:
                raise RuntimeError("keine PV-Messwerte in der HA-Statistik")
            erster = min(mess).date()
            zeitraum = {"start_date": erster.isoformat(), "end_date": ende_tag.isoformat()}
            # Juengster Lauf je Stunde des gewaehlten Wettermodells (previous-runs-api)
            prog = await pvdaten.gti_holen(sitzung, pvdaten.LAEUFE, lat, lon, self.flaechen, zeitraum,
                                           self._modelle)
            arch = await pvdaten.gti_holen(sitzung, pvdaten.ARCHIV, lat, lon, self.flaechen, zeitraum)
            neu = await asyncio.to_thread(pm.trainieren, mess, prog, arch, self.flaechen, lat, lon, tz)
            # Bedienhandlung "gereinigt" ueber das Neutraining hinweg erhalten
            neu.gereinigt_am = self.modell.gereinigt_am
            if self.modell.gereinigt_am and self.modell.sauberkeit is not None and (
                    not neu.sauberkeit_stand or neu.sauberkeit_stand < self.modell.gereinigt_am):
                neu.sauberkeit, neu.sauberkeit_stand = self.modell.sauberkeit, self.modell.sauberkeit_stand
            neu.trainiert_am = datetime.now(timezone.utc).isoformat(timespec="seconds")
            neu.wettermodell = self.konfig.wettermodell
            neu.kennzahlen["tage"] = len({t.date() for t in mess})
            self.modell = neu
            self._sichern()
            self.fehler = None
            self._zuletzt_prognose = NIE   # sofort neu rechnen
            text = (f"PV-Modell trainiert ({pvdaten.WETTERMODELL_TEXT.get(neu.wettermodell, neu.wettermodell)}): "
                    f"{neu.kennzahlen['tage']} Tage, {neu.kennzahlen['felder']} "
                    f"Kennfeld-Felder, Schmutzverlust im Mittel {neu.kennzahlen['verlust_schmutz_prozent']} %")
            log.info(text)
            db.ereignis("info", "pvmodell", text)
        except Exception as e:
            self.fehler = f"Training: {e}"
            log.warning("PV-Modell: %s", self.fehler)
            db.ereignis("warnung", "pvmodell", self.fehler)
        finally:
            self.training_laeuft = False

    # ── Sauberkeit ───────────────────────────────────────────────────────────────────
    async def sauberkeit_aktualisieren(self, ha, sitzung, tz) -> None:
        lat, lon = ha.standort
        ende_tag = pvdaten.gestern()
        ende = datetime(ende_tag.year, ende_tag.month, ende_tag.day, tzinfo=timezone.utc) + timedelta(days=1)
        start = ende - timedelta(days=pm.SAUBERKEIT_FENSTER_TAGE)
        if self.modell.gereinigt_am:
            g = date.fromisoformat(self.modell.gereinigt_am)
            start = max(start, datetime(g.year, g.month, g.day, tzinfo=timezone.utc) + timedelta(days=1))
        if start >= ende:
            return
        mess = await pvdaten.pv_messung(ha, self.konfig, start, ende)
        arch = await pvdaten.gti_holen(sitzung, pvdaten.ARCHIV, lat, lon, self.flaechen,
                                       {"start_date": start.date().isoformat(), "end_date": ende_tag.isoformat()})
        wert, sonne = pm.sauberkeit_schaetzen(self.modell, mess, arch, self.flaechen, lat, lon, tz)
        if wert is None:
            log.info("Sauberkeit: zu wenig Sonne im Fenster (%.0f kWh) – Wert bleibt", sonne)
            return
        heute = datetime.now(tz).date()
        self.modell.sauberkeit, self.modell.sauberkeit_stand = wert, heute.isoformat()
        woche = (heute - timedelta(days=heute.weekday())).isoformat()
        self.modell.sauberkeit_wochen[woche] = wert
        self._sichern()
        log.info("Sauberkeit %.0f %% (Mittel %.0f %%)", wert * 100, self.modell.sauberkeit_mittel * 100)

    def gereinigt(self, heute: date) -> None:
        """Bedienhandlung: Anlage wurde gereinigt."""
        self.modell.gereinigt_am = heute.isoformat()
        self.modell.sauberkeit, self.modell.sauberkeit_stand = 1.0, heute.isoformat()
        self._sichern()
        self._zuletzt_prognose = NIE
        db.ereignis("info", "pvmodell", f"Anlage gereinigt am {heute:%d.%m.%Y} – Prognose "
                                        f"+{(self.modell.zuschlag(heute) - 1) * 100:.0f} %")

    # ── Prognose ─────────────────────────────────────────────────────────────────────
    async def prognose_aktualisieren(self, ha, sitzung, tz) -> None:
        lat, lon = ha.standort
        einstrahlung = await pvdaten.gti_holen(sitzung, pvdaten.PROGNOSE, lat, lon, self.flaechen,
                                               {"past_days": 1, "forecast_days": PROGNOSE_TAGE}, self._modelle)
        stunden = sorted(einstrahlung.items())
        werte = self.modell.prognose(stunden, self.flaechen, lat, lon, tz)
        try:
            wetter = await pvdaten.wetter_holen(sitzung, lat, lon, {"past_days": 2, "forecast_days": PROGNOSE_TAGE})
            werte, tage = morgentau.korrigieren(werte, wetter, lat, lon, tz)
            self._tau_merken(tage, datetime.now(tz).date())
        except Exception as e:                  # ohne Wetter: Prognose ohne Tau-Korrektur
            log.warning("Morgentau: Wetter nicht geladen (%s) – Prognose ohne Korrektur", e)
        await self._woche_rechnen(ha, werte, tz)
        # Format wie energy/solar_forecast: Zeitstempel = Ende der Stunde, Wh
        wh = {(t + timedelta(hours=1)).isoformat(): round(kwh * 1000) for t, kwh in werte}
        self.ziel.setzen({"eigenes_modell": {"wh_hours": wh}}, datetime.now(tz))

    async def _woche_rechnen(self, ha, werte, tz) -> None:
        """7-Tage-Vorschau; Hausprofil und Akkubedarf einmal am Tag aus der HA-Statistik."""
        jetzt = time.monotonic()
        if jetzt - self._zuletzt_verbrauch > VERBRAUCH_S:
            try:
                haus, akku = await pvdaten.verbrauch_holen(ha, self.konfig, datetime.now(timezone.utc))
                self.haus_profil, self.akku_bedarf = wochenprognose.haus_profil(haus, tz), akku
                self._zuletzt_verbrauch = jetzt
                log.info("7-Tage-Vorschau: Hausverbrauch im Mittel %.2f kW, Hausakku %s kWh je Tag",
                         sum(self.haus_profil.values()) / max(len(self.haus_profil), 1),
                         "?" if akku is None else f"{akku:.1f}")
            except Exception as e:
                log.warning("7-Tage-Vorschau: Verbrauch nicht geladen (%s)", e)
        self.woche = wochenprognose.berechnen(werte, self.haus_profil, self.akku_bedarf or 0.0, tz,
                                              datetime.now(tz).date())

    def _tau_merken(self, tage: dict[date, dict], heute: date) -> None:
        """Heute und morgen: bei neuer oder geaenderter Einstufung protokollieren und je Tag
        speichern – die letzte Einstufung vor Sonnenaufgang zaehlt beim Nachjustieren."""
        protokoll = db.einstellung(TAU_PROTOKOLL) or {}
        for tag in (heute, heute + timedelta(days=1)):
            info = tage.get(tag)
            if not info:
                continue
            alt = self.tau.get(tag)
            if not alt or (alt["klasse"], alt["faktor"]) != (info["klasse"], info["faktor"]):
                zeile = morgentau.text(tag, info)
                log.info(zeile)
                db.ereignis("info", "pvmodell", zeile)
            protokoll[tag.isoformat()] = {**info, "stand": datetime.now(timezone.utc).isoformat(timespec="minutes")}
        grenze = (heute - timedelta(days=TAU_PROTOKOLL_TAGE)).isoformat()
        db.einstellung_setzen(TAU_PROTOKOLL, {k: v for k, v in sorted(protokoll.items()) if k >= grenze})
        self.tau = tage

    def tau_anzeige(self, heute: date) -> dict:
        """Morgentau fuer heute und morgen (Oberflaeche)."""
        aus = {}
        for name, tag in (("heute", heute), ("morgen", heute + timedelta(days=1))):
            i = self.tau.get(tag)
            if i:
                aus[name] = {"klasse": i["klasse"], "faktor": i["faktor"], "bis": i["morgen_bis"],
                             "ohne_kwh": i["morgen_ohne_kwh"], "mit_kwh": i["morgen_mit_kwh"]}
        return aus

    # ── Anzeige ──────────────────────────────────────────────────────────────────────
    def status(self, heute: date) -> dict:
        m = self.modell
        mittel = m.sauberkeit_mittel
        return {
            "aktiv": self.aktiv, "zustand": self.zustand, "fehler": self.fehler,
            "training_laeuft": self.training_laeuft, "trainiert_am": m.trainiert_am,
            "wettermodell": pvdaten.WETTERMODELL_TEXT.get(m.wettermodell, m.wettermodell),
            "kennzahlen": m.kennzahlen, "flaechen": [f.__dict__ for f in self.flaechen],
            "sauberkeit": m.sauberkeit, "sauberkeit_stand": m.sauberkeit_stand,
            "sauberkeit_mittel": mittel, "verlust_prozent": m.verlust_prozent(),
            "zuschlag": round(m.zuschlag(heute), 3), "gereinigt_am": m.gereinigt_am,
            "reinigung_empfohlen": m.sauberkeit is not None and m.sauberkeit < mittel - 0.05,
            "sauberkeit_wochen": m.sauberkeit_wochen,
        }
