"""Sensoren: PV-Prognose heute / Rest / morgen / aktuelle Stunde / naechste Stunde /
naechste 3 Stunden (kWh). Die Stundenwerte stehen als Attribut am Sensor „heute“."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import PrognoseCoordinator
from .rechnen import einlesen, kennzahlen


@dataclass(frozen=True, kw_only=True)
class PrognoseBeschreibung(SensorEntityDescription):
    schluessel: str


BESCHREIBUNGEN = (
    PrognoseBeschreibung(key="heute", schluessel="heute", name="Heute"),
    PrognoseBeschreibung(key="rest_heute", schluessel="rest_heute", name="Rest heute"),
    PrognoseBeschreibung(key="morgen", schluessel="morgen", name="Morgen"),
    PrognoseBeschreibung(key="aktuelle_stunde", schluessel="aktuelle_stunde", name="Aktuelle Stunde"),
    PrognoseBeschreibung(key="naechste_stunde", schluessel="naechste_stunde", name="Nächste Stunde"),
    PrognoseBeschreibung(key="naechste_3h", schluessel="naechste_3h", name="Nächste 3 Stunden"),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator: PrognoseCoordinator = entry.runtime_data
    async_add_entities(PrognoseSensor(coordinator, entry, b) for b in BESCHREIBUNGEN)


class PrognoseSensor(CoordinatorEntity[PrognoseCoordinator], SensorEntity):
    """Prognosewerte sind keine Zaehler: Energie ohne state_class (wie forecast_solar)."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:solar-power-variant"
    _attr_has_entity_name = True

    def __init__(self, coordinator: PrognoseCoordinator, entry: ConfigEntry,
                 beschreibung: PrognoseBeschreibung) -> None:
        super().__init__(coordinator)
        self.entity_description = beschreibung
        self._attr_unique_id = f"{entry.entry_id}_{beschreibung.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)}, name="EV PV-Laden Prognose",
            manufacturer="HasenbeinMH", model="PV-Prognose (eigenes Modell)",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://github.com/HasenbeinMH/ev-pv-laden")

    @property
    def native_value(self) -> float | None:
        werte = einlesen((self.coordinator.data or {}).get("wh_hours"))
        return kennzahlen(werte, dt_util.now())[self.entity_description.schluessel]

    @property
    def extra_state_attributes(self) -> dict | None:
        if self.entity_description.key != "heute":
            return None
        daten = self.coordinator.data or {}
        return {"wh_hours": daten.get("wh_hours") or {}, "stand": daten.get("stand"),
                "quelle": daten.get("quelle")}
