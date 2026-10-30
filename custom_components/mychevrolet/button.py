"""Button platform for myChevrolet remote commands."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .entity import MyChevroletEntity

_LOGGER = logging.getLogger(__name__)

# Maps a button key to the coordinator coroutine that runs it.
_BUTTON_COMMANDS = {
    "refresh_data": "async_refresh_data",
    "honk_flash": "async_honk_flash",
    "remote_start": "async_remote_start",
    "remote_stop": "async_remote_stop",
}


async def async_setup_entry(
    hass, entry, async_add_entities
) -> None:  # type: ignore[no-untyped-def]
    """Set up a button for each remote command the vehicle supports."""
    coordinator: DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    vin = entry.data["vin"]

    buttons: list[ButtonEntity] = [
        MyChevroletButton(coordinator, vin, "refresh_data", "Update Data", "refresh"),
    ]
    if coordinator.command_available("alert"):
        buttons.append(
            MyChevroletButton(coordinator, vin, "honk_flash", "Honk & Flash", "flash")
        )
    if coordinator.command_available("start"):
        buttons.append(
            MyChevroletButton(coordinator, vin, "remote_start", "Remote Start", "play")
        )
    if coordinator.command_available("cancelStart"):
        buttons.append(
            MyChevroletButton(coordinator, vin, "remote_stop", "Remote Stop", "stop")
        )

    async_add_entities(buttons)


class MyChevroletButton(MyChevroletEntity, ButtonEntity):
    """Trigger a single remote command."""

    def __init__(self, coordinator, vin, key, name, icon):  # type: ignore[no-untyped-def]
        super().__init__(coordinator, key, name)
        self._attr_icon = icon
        self._coro_name = _BUTTON_COMMANDS[key]

    async def async_press(self) -> None:
        """Run the mapped coordinator command."""
        coro = getattr(self.coordinator, self._coro_name)()
        try:
            await coro
        except HomeAssistantError:
            raise
        except Exception as err:
            raise HomeAssistantError(f"{self._attr_name} failed: {err}") from err
