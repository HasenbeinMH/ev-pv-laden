# -*- coding: utf-8 -*-
"""
HA-Entitaeten per MQTT-Discovery (echte, persistente Entitaeten mit unique_id).

Geraete-Discovery (ein Konfigurationstopic fuer alle Entitaeten, geprueft gegen
home-assistant.io/integrations/mqtt): homeassistant/device/ev_pv_laden/config mit
device, origin und components. Zustand als ein JSON auf ev_pv_laden/zustand, retained –
nach einem HA-Neustart sind die Zaehler sofort wieder da. Verfuegbarkeit ueber
ev_pv_laden/status mit Testament (Last Will) "offline".

Sendet HA "online" auf homeassistant/status (HA neu gestartet), wird Discovery und
Zustand erneut gesendet.

Bedienung (M8): select/number/text/switch mit command_topic ev_pv_laden/set/<schluessel>.
Der Zustand kommt wie bei den Sensoren aus dem einen JSON – HA zeigt also immer den Wert,
den das Add-on wirklich uebernommen hat (kein "optimistic").

Zugangsdaten:
  Add-on:      Supervisor GET /services/mqtt (config.yaml: hassio_api + services mqtt:need)
  Entwicklung: MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASSWORD
"""
import asyncio
import json
import logging
import os
from dataclasses import dataclass

import aiohttp
import aiomqtt

from strategie import MODI, TREIBER
from version import VERSION

log = logging.getLogger("mqtt")

KENNUNG = "ev_pv_laden"
DISCOVERY = f"homeassistant/device/{KENNUNG}/config"
ZUSTAND = f"{KENNUNG}/zustand"
STATUS = f"{KENNUNG}/status"
HA_STATUS = "homeassistant/status"
BEFEHL = f"{KENNUNG}/set"
EREIGNIS = f"{KENNUNG}/ereignis"
WARTEN_MAX_S = 60


@dataclass(frozen=True)
class MqttZugang:
    host: str
    port: int
    benutzer: str | None
    passwort: str | None


async def zugang_holen() -> MqttZugang | None:
    token = os.environ.get("SUPERVISOR_TOKEN")
    if token:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get("http://supervisor/services/mqtt",
                                 headers={"Authorization": f"Bearer {token}"},
                                 timeout=aiohttp.ClientTimeout(total=10)) as r:
                    d = (await r.json()).get("data") or {}
            if d.get("host"):
                return MqttZugang(d["host"], int(d.get("port") or 1883),
                                  d.get("username"), d.get("password"))
            log.error("Supervisor liefert keinen MQTT-Dienst – ist der Mosquitto-Broker installiert?")
        except Exception as e:
            log.error("MQTT-Zugangsdaten vom Supervisor nicht abrufbar: %s", e)
        return None
    if os.environ.get("MQTT_HOST"):
        return MqttZugang(os.environ["MQTT_HOST"], int(os.environ.get("MQTT_PORT", "1883")),
                          os.environ.get("MQTT_USER"), os.environ.get("MQTT_PASSWORD"))
    return None


def _energie(name, schluessel, icon, diagnose=False):
    d = {"platform": "sensor", "name": name, "unique_id": f"{KENNUNG}_{schluessel}",
         "default_entity_id": f"sensor.{KENNUNG}_{schluessel}",
         "device_class": "energy", "state_class": "total_increasing",
         "unit_of_measurement": "kWh", "suggested_display_precision": 3,
         "value_template": f"{{{{ value_json.{schluessel} }}}}", "icon": icon}
    if diagnose:
        d["entity_category"] = "diagnostic"
    return d


def _leistung(name, schluessel, icon):
    return {"platform": "sensor", "name": name, "unique_id": f"{KENNUNG}_{schluessel}",
            "default_entity_id": f"sensor.{KENNUNG}_{schluessel}",
            "device_class": "power", "state_class": "measurement", "unit_of_measurement": "W",
            "suggested_display_precision": 0,
            "value_template": f"{{{{ value_json.{schluessel} }}}}", "icon": icon}


def _text(name, schluessel, icon, diagnose=False):
    d = {"platform": "sensor", "name": name, "unique_id": f"{KENNUNG}_{schluessel}",
         "default_entity_id": f"sensor.{KENNUNG}_{schluessel}",
         "value_template": f"{{{{ value_json.{schluessel} }}}}", "icon": icon}
    if diagnose:
        d["entity_category"] = "diagnostic"
    return d


def _prognose(name, schluessel):
    # Prognosewerte sind keine Zaehler: device_class energy ohne state_class
    return {"platform": "sensor", "name": name, "unique_id": f"{KENNUNG}_{schluessel}",
            "default_entity_id": f"sensor.{KENNUNG}_{schluessel}", "device_class": "energy",
            "unit_of_measurement": "kWh", "suggested_display_precision": 1,
            "value_template": f"{{{{ value_json.{schluessel} }}}}", "icon": "mdi:solar-power-variant"}


def _basis(plattform, name, schluessel, icon, konfig=False):
    d = {"platform": plattform, "name": name, "unique_id": f"{KENNUNG}_{schluessel}",
         "default_entity_id": f"{plattform}.{KENNUNG}_{schluessel}",
         "command_topic": f"{BEFEHL}/{schluessel}", "icon": icon}
    if konfig:
        d["entity_category"] = "config"
    return d


def _select(name, schluessel, optionen, icon, konfig=False):
    return {**_basis("select", name, schluessel, icon, konfig), "options": list(optionen),
            "value_template": f"{{{{ value_json.{schluessel} }}}}"}


def _number(name, schluessel, minimum, maximum, schritt, einheit, icon, konfig=False, **extra):
    return {**_basis("number", name, schluessel, icon, konfig), "min": minimum, "max": maximum,
            "step": schritt, "unit_of_measurement": einheit, "mode": "box",
            "value_template": f"{{{{ value_json.{schluessel} }}}}", **extra}


def discovery_nutzlast() -> dict:
    return {
        "device": {"identifiers": [KENNUNG], "name": "EV PV-Laden", "manufacturer": "HasenbeinMH",
                   "model": "PV-Ueberschussladen", "sw_version": VERSION},
        "origin": {"name": "EV PV-Laden", "sw_version": VERSION,
                   "support_url": "https://github.com/HasenbeinMH/ev-pv-laden"},
        "availability_topic": STATUS,
        "state_topic": ZUSTAND,
        "components": {
            "kwh_pv": _energie("Ladung PV", "kwh_pv", "mdi:solar-power"),
            "kwh_akku": _energie("Ladung Hausakku", "kwh_akku", "mdi:home-battery"),
            "kwh_netz": _energie("Ladung Netz", "kwh_netz", "mdi:transmission-tower"),
            "kwh_ohne_aufteilung": _energie("Ladung ohne Aufteilung", "kwh_ohne_aufteilung",
                                            "mdi:help-circle-outline", diagnose=True),
            "leistung_pv": _leistung("Ladeleistung PV", "leistung_pv", "mdi:solar-power"),
            "leistung_akku": _leistung("Ladeleistung Hausakku", "leistung_akku", "mdi:home-battery"),
            "leistung_netz": _leistung("Ladeleistung Netz", "leistung_netz", "mdi:transmission-tower"),
            # Regelung (Strategie): was das Auto bekommen darf und warum
            "p_erlaubt": _leistung("Erlaubte Ladeleistung", "p_erlaubt", "mdi:car-electric"),
            "pgrid_virtuell": _leistung("Virtueller Netzwert (ids)", "pgrid_virtuell",
                                        "mdi:transmission-tower-export"),
            "grund": _text("Grund", "grund", "mdi:information-outline"),
            "regelzustand": _text("Regelzustand", "regelzustand", "mdi:state-machine"),
            # Ersetzt durch das Auswahlfeld "lademodus" (M8): nur "platform" entfernt die Entitaet
            "modus": {"platform": "sensor"},
            "treiber": _text("Aktiver Treiber", "treiber", "mdi:cog-transfer", diagnose=True),
            # Bedienung (M8)
            "lademodus": _select("Lademodus", "lademodus", MODI.values(), "mdi:ev-station"),
            "treiber_wahl": _select("Treiber", "treiber_wahl", TREIBER_NAMEN.values(),
                                    "mdi:cog-transfer", konfig=True),
            "trockenlauf": {**_basis("switch", "Trockenlauf (schreibt nicht)", "trockenlauf",
                                     "mdi:shield-check", konfig=True),
                            "value_template": "{{ value_json.trockenlauf }}",
                            "state_on": "ON", "state_off": "OFF"},
            "akku_soc_schwelle": _number("Hausakku zuerst bis SoC", "akku_soc_schwelle", 0, 100, 1, "%",
                                         "mdi:home-battery"),
            # Zielzeit: SoC des Autos (eingeben = neuer Stand; Anzeige = hochgerechnet), Ziel, Abfahrt
            "auto_soc": _number("SoC Auto", "auto_soc", 0, 100, 1, "%", "mdi:car-battery",
                                device_class="battery"),
            "ziel_soc": _number("Ziel-SoC", "ziel_soc", 10, 100, 5, "%", "mdi:battery-arrow-up"),
            "abfahrt": {**_basis("text", "Abfahrt", "abfahrt", "mdi:clock-end"),
                        "pattern": "^([01][0-9]|2[0-3]):[0-5][0-9]$", "min": 5, "max": 5,
                        "value_template": "{{ value_json.abfahrt }}"},
            "puffer_min": _number("Zielzeit-Puffer", "puffer_min", 0, 600, 5, "min", "mdi:timer-sand",
                                  konfig=True),
            "zielzeit_start": {
                "platform": "sensor", "name": "Zielzeit: spätester Netzstart",
                "unique_id": f"{KENNUNG}_zielzeit_start", "default_entity_id": f"sensor.{KENNUNG}_zielzeit_start",
                "device_class": "timestamp", "value_template": "{{ value_json.zielzeit_start }}",
                "icon": "mdi:clock-start"},
            # Meldungen fuer Benachrichtigungen (Telegram-Automation): einmal je Ansteckvorgang
            "ladung": {"platform": "event", "name": "Ladung", "unique_id": f"{KENNUNG}_ladung",
                       "default_entity_id": f"event.{KENNUNG}_ladung", "state_topic": EREIGNIS,
                       "event_types": ["fertig", "ziel_erreicht"], "icon": "mdi:car-electric"},
            # PV-Prognose (eigenes Modell) und Sauberkeit der Anlage
            "pv_prognose_heute": _prognose("PV-Prognose heute", "pv_prognose_heute"),
            "pv_prognose_rest_heute": _prognose("PV-Prognose Rest heute", "pv_prognose_rest_heute"),
            "pv_prognose_morgen": _prognose("PV-Prognose morgen", "pv_prognose_morgen"),
            "pv_sauberkeit": {
                "platform": "sensor", "name": "PV-Sauberkeit", "unique_id": f"{KENNUNG}_pv_sauberkeit",
                "default_entity_id": f"sensor.{KENNUNG}_pv_sauberkeit", "unit_of_measurement": "%",
                "state_class": "measurement", "suggested_display_precision": 0,
                "value_template": "{{ value_json.pv_sauberkeit }}", "icon": "mdi:spray-bottle"},
            # Fuer die externe Watchdog-Automation (M8): aendert sich in jedem Sendezyklus
            "lebenszeichen": {
                "platform": "sensor", "name": "Lebenszeichen", "unique_id": f"{KENNUNG}_lebenszeichen",
                "default_entity_id": f"sensor.{KENNUNG}_lebenszeichen",
                "device_class": "timestamp", "entity_category": "diagnostic",
                "value_template": "{{ value_json.lebenszeichen }}", "icon": "mdi:heart-pulse"},
        },
    }


# Anzeigenamen der Auswahlfelder (HA zeigt und sendet den Namen, das Add-on kennt den Schluessel)
TREIBER_NAMEN = {"ids": "ids (go-e regelt)", "a": "A (Add-on stellt Strom)"}
assert set(TREIBER_NAMEN) == set(TREIBER)


def befehl_uebersetzen(schluessel: str, text: str) -> tuple[str, object]:
    """MQTT-Befehl -> (Ziel, Wert). Ziel: Parametername, "auto_soc" oder "trockenlauf".
    Wirft ValueError bei unbekanntem Schluessel oder Wert."""
    text = text.strip()
    if schluessel == "lademodus":
        return "modus", _rueckwaerts(MODI, text)
    if schluessel == "treiber_wahl":
        return "treiber", _rueckwaerts(TREIBER_NAMEN, text)
    if schluessel == "trockenlauf":
        if text not in ("ON", "OFF"):
            raise ValueError(f"ON/OFF erwartet, nicht '{text}'")
        return "trockenlauf", text == "ON"
    if schluessel in ("akku_soc_schwelle", "ziel_soc", "puffer_min", "auto_soc"):
        return schluessel, float(text)
    if schluessel == "abfahrt":
        return "abfahrt", text
    raise ValueError(f"unbekannter Befehl '{schluessel}'")


def _rueckwaerts(namen: dict, text: str) -> str:
    for k, n in namen.items():
        if text in (n, k):
            return k
    raise ValueError(f"unbekannte Auswahl '{text}'")


def bedien_zustand(param, trockenlauf: bool, auto_soc: float | None) -> dict:
    """Zustandsfelder der Bedien-Entitaeten (im selben JSON wie die Sensoren)."""
    return {"lademodus": MODI.get(param.modus), "treiber_wahl": TREIBER_NAMEN.get(param.treiber),
            "trockenlauf": "ON" if trockenlauf else "OFF",
            "akku_soc_schwelle": param.akku_soc_schwelle, "ziel_soc": param.ziel_soc,
            "abfahrt": param.abfahrt, "puffer_min": param.puffer_min,
            "auto_soc": None if auto_soc is None else round(auto_soc)}


class MqttHA:
    def __init__(self, zugang: MqttZugang, befehl=None):
        """befehl: async (schluessel, text) -> None, fuer Befehle aus HA."""
        self.zugang = zugang
        self.befehl = befehl
        self.verbunden = False
        self.letzter_fehler: str | None = None
        self._zustand: dict | None = None
        self._client: aiomqtt.Client | None = None
        self._neu = asyncio.Event()

    def zustand_setzen(self, zustand: dict) -> None:
        """Neuer Zustand – wird beim naechsten Durchlauf gesendet (nicht blockierend)."""
        self._zustand = zustand
        self._neu.set()

    def ereignis_senden(self, art: str, daten: dict) -> None:
        """Einmaliges Ereignis (nicht retained): event_type + Attribute."""
        if self._client and self.verbunden:
            asyncio.create_task(self._client.publish(
                EREIGNIS, json.dumps({"event_type": art, **daten}), qos=1, retain=False))
        else:
            log.warning("Ereignis %s nicht gesendet – MQTT nicht verbunden", art)

    async def laufen(self) -> None:
        warten = 1
        while True:
            try:
                async with aiomqtt.Client(
                        self.zugang.host, self.zugang.port, username=self.zugang.benutzer,
                        password=self.zugang.passwort, identifier=f"{KENNUNG}_addon",
                        will=aiomqtt.Will(STATUS, "offline", qos=1, retain=True)) as c:
                    self._client, self.verbunden, self.letzter_fehler, warten = c, True, None, 1
                    log.info("MQTT verbunden mit %s:%d", self.zugang.host, self.zugang.port)
                    await c.subscribe(HA_STATUS)
                    await c.subscribe(f"{BEFEHL}/+", qos=1)
                    await self._alles_senden(c)
                    empfang = asyncio.create_task(self._empfangen(c))
                    try:
                        while True:
                            await self._neu.wait()
                            self._neu.clear()
                            await self._zustand_senden(c)
                    finally:
                        empfang.cancel()
            except asyncio.CancelledError:
                if self._client and self.verbunden:
                    try:
                        await self._client.publish(STATUS, "offline", qos=1, retain=True)
                    except Exception:
                        pass
                raise
            except Exception as e:
                self.letzter_fehler = f"{type(e).__name__}: {e}"
                log.warning("MQTT: %s – neuer Versuch in %d s", self.letzter_fehler, warten)
            finally:
                self.verbunden, self._client = False, None
            await asyncio.sleep(warten)
            warten = min(warten * 2, WARTEN_MAX_S)

    async def _empfangen(self, c: aiomqtt.Client) -> None:
        async for nachricht in c.messages:
            if nachricht.topic.matches(HA_STATUS) and nachricht.payload == b"online":
                log.info("Home Assistant neu gestartet – Discovery erneut senden")
                await asyncio.sleep(2)   # HA braucht einen Moment fuer die MQTT-Integration
                await self._alles_senden(c)
            elif nachricht.topic.matches(f"{BEFEHL}/+") and self.befehl:
                schluessel = str(nachricht.topic).rsplit("/", 1)[-1]
                try:
                    await self.befehl(schluessel, nachricht.payload.decode("utf-8", "replace"))
                except Exception:
                    log.exception("Befehl %s nicht ausgefuehrt", schluessel)

    async def _alles_senden(self, c: aiomqtt.Client) -> None:
        await c.publish(DISCOVERY, json.dumps(discovery_nutzlast()), qos=1, retain=True)
        await c.publish(STATUS, "online", qos=1, retain=True)
        await self._zustand_senden(c)

    async def _zustand_senden(self, c: aiomqtt.Client) -> None:
        if self._zustand is not None:
            await c.publish(ZUSTAND, json.dumps(self._zustand), qos=1, retain=True)
