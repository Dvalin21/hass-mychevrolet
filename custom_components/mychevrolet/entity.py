"""Base entity for myChevrolet."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MyChevroletDataUpdateCoordinator


class MyChevroletEntity(CoordinatorEntity):
    """Common behaviour for all myChevrolet entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MyChevroletDataUpdateCoordinator,
        unique_id: str,
        name: str,
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self._vin = coordinator.config_entry.data["vin"]
        self._attr_unique_id = f"{self._vin}_{unique_id}"
        self._attr_name = name

    @property
    def device_info(self) -> DeviceInfo:
        """Route every entity through the single vehicle device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._vin)},
            name=self.coordinator.config_entry.title,
            manufacturer="Chevrolet",
            model="OnStar",
        )
