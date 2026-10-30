"""Binary sensor platform for myChevrolet."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .entity import MyChevroletEntity
from .helpers import get_diagnostic_value, get_diagnostics

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass, entry, async_add_entities
) -> None:  # type: ignore[no-untyped-def]
    """Set up binary sensors (currently: plugged in, EV only)."""
    coordinator: DataUpdateCoordinator = hass.data["mychevrolet"][entry.entry_id][
        "coordinator"
    ]
    vin = entry.data["vin"]

    sensors: list[BinarySensorEntity] = [MyChevroletPluggedIn(coordinator, vin)]
    async_add_entities(sensors)


class MyChevroletPluggedIn(MyChevroletEntity, BinarySensorEntity):
    """True while the vehicle reports it is plugged in and charging."""

    _attr_name = "Plugged In"
    _attr_device_class = BinarySensorDeviceClass.PLUG

    def __init__(self, coordinator, vin):  # type: ignore[no-untyped-def]
        super().__init__(coordinator, "plug_state", "Plugged In")

    @property
    def is_on(self) -> bool | None:
        """Return True when EV PLUG STATE is plugged."""
        value = get_diagnostic_value(
            get_diagnostics(self.coordinator.data), "EV PLUG STATE"
        )
        if value is None:
            return None
        return str(value).lower() == "plugged"
