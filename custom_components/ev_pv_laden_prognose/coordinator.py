"""Holt die Stundenprognose vom Add-on EV PV-Laden (alle 15 min)."""
from __future__ import annotations

import asyncio
import logging

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_URL, DOMAIN, INTERVALL, PFAD

_LOGGER = logging.getLogger(__name__)


async def prognose_holen(hass: HomeAssistant, url: str) -> dict:
    """GET <url>/api/prognose/stunden -> {"verfuegbar", "stand", "wh_hours"}."""
    sitzung = async_get_clientsession(hass)
    async with asyncio.timeout(15):
        async with sitzung.get(url.rstrip("/") + PFAD) as antwort:
            antwort.raise_for_status()
            return await antwort.json()


class PrognoseCoordinator(DataUpdateCoordinator[dict]):
    """data = Antwort des Add-ons; wh_hours bleibt im Format des Energie-Dashboards."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=INTERVALL)
        self.url = entry.data[CONF_URL]

    async def _async_update_data(self) -> dict:
        try:
            daten = await prognose_holen(self.hass, self.url)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise UpdateFailed(f"Add-on EV PV-Laden nicht erreichbar ({self.url}): {err}") from err
        if not daten.get("verfuegbar"):
            # Add-on laeuft, Modell rechnet noch (z. B. direkt nach dem Start): alte Werte behalten
            if self.data:
                return self.data
            raise UpdateFailed("Add-on liefert noch keine Prognose (Modell wird berechnet)")
        return daten
