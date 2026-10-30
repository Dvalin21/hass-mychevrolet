"""Device tracker platform for myChevrolet (vehicle GPS location)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import ScannerEntity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .entity import MyChevroletEntity
from .helpers import get_location

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass, entry, async_add_entities
) -> None:  # type: ignore[no-untyped-def]
    """Set up the vehicle location tracker."""
    coordinator: DataUpdateCoordinator = hass.data["mychevrolet"][entry.entry_id][
        "coordinator"
    ]
    vin = entry.data["vin"]
    async_add_entities([MyChevroletTracker(coordinator, vin)])


class MyChevroletTracker(MyChevroletEntity, ScannerEntity):
    """Report the vehicle's last known GPS position."""

    _attr_name = "Location"
    _attr_source_type = SourceType.GPS

    def __init__(self, coordinator, vin):  # type: ignore[no-untyped-def]
        super().__init__(coordinator, "location", "Location")

    @property
    def is_connected(self) -> bool:
        """True when the vehicle has reported a GPS position."""
        location = get_location(self.coordinator.data)
        return bool(location and location.get("latitude") is not None)

    @property
    def latitude(self) -> float | None:
        """Return latitude."""
        location = get_location(self.coordinator.data)
        return location.get("latitude") if location else None

    @property
    def longitude(self) -> float | None:
        """Return longitude."""
        location = get_location(self.coordinator.data)
        return location.get("longitude") if location else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Pass through heading and speed when the vehicle reports them."""
        location = get_location(self.coordinator.data)
        if not location:
            return {}
        return {
            key: location[key]
            for key in ("heading", "speed", "altitude")
            if key in location
        }
