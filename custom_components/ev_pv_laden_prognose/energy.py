"""Energie-Dashboard: Prognose der Solarproduktion (wie forecast_solar/energy.py)."""
from __future__ import annotations

from homeassistant.core import HomeAssistant

from .coordinator import PrognoseCoordinator


async def async_get_solar_forecast(
    hass: HomeAssistant, config_entry_id: str
) -> dict[str, dict[str, float | int]] | None:
    """Stundenwerte in Wh; Zeitstempel = Ende der Stunde."""
    entry = hass.config_entries.async_get_entry(config_entry_id)
    if entry is None or not isinstance(getattr(entry, "runtime_data", None), PrognoseCoordinator):
        return None
    daten = entry.runtime_data.data or {}
    return {"wh_hours": dict(daten.get("wh_hours") or {})}
