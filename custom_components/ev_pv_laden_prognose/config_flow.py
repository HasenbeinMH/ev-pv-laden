"""Einrichtung über die Oberfläche: Adresse des Add-ons eingeben und prüfen."""
from __future__ import annotations

import asyncio

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import CONF_URL, DEFAULT_URL, DOMAIN
from .coordinator import prognose_holen


class PrognoseConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        fehler: dict[str, str] = {}
        if user_input is not None:
            url = user_input[CONF_URL].strip().rstrip("/")
            await self.async_set_unique_id(url)
            self._abort_if_unique_id_configured()
            try:
                await prognose_holen(self.hass, url)
            except aiohttp.ClientResponseError as err:
                # 404: Add-on erreichbar, aber zu alt (Schnittstelle gibt es ab 0.12.0)
                fehler["base"] = "addon_zu_alt" if err.status == 404 else "cannot_connect"
            except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError, ValueError):
                fehler["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title="EV PV-Laden Prognose", data={CONF_URL: url})
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_URL, default=DEFAULT_URL): str}),
            errors=fehler)
