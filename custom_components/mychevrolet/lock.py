"""Lock platform for myChevrolet (door lock / unlock)."""

from __future__ import annotations

import logging

from homeassistant.components.lock import LockEntity, LockEntityFeature
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .entity import MyChevroletEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass, entry, async_add_entities
) -> None:  # type: ignore[no-untyped-def]
    """Set up the door lock entity."""
    coordinator: DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    vin = entry.data["vin"]
    async_add_entities([MyChevroletLock(coordinator, vin)])


class MyChevroletLock(MyChevroletEntity, LockEntity):
    """Lock and unlock the vehicle doors."""

    _attr_name = "Door Lock"
    _attr_supported_features = LockEntityFeature(0)

    def __init__(self, coordinator, vin):  # type: ignore[no-untyped-def]
        super().__init__(coordinator, "door_lock", "Door Lock")

    @property
    def is_locked(self) -> bool | None:
        """Return True if the doors report locked.

        pyonstar does not surface a live lock state, so we cannot confirm the
        current state; the entity reflects the last command result via a refresh.
        """
        return None

    async def async_lock(self, **kwargs) -> None:
        """Lock the doors."""
        try:
            await self.coordinator.async_lock_doors()
        except HomeAssistantError:
            raise
        except Exception as err:
            raise HomeAssistantError(f"Failed to lock doors: {err}") from err

    async def async_unlock(self, **kwargs) -> None:
        """Unlock the doors."""
        try:
            await self.coordinator.async_unlock_doors()
        except HomeAssistantError:
            raise
        except Exception as err:
            raise HomeAssistantError(f"Failed to unlock doors: {err}") from err
