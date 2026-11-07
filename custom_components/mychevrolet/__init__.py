"""The myChevrolet integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.storage import STORAGE_DIR
from pyonstar import OnStar

from .const import (
    CONF_CHEATER_MODE,
    CONF_SCAN_INTERVAL,
    CONF_VIN,
    DEFAULT_CHEATER_MODE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import MyChevroletConfigEntry, MyChevroletDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: MyChevroletConfigEntry) -> bool:
    """Set up myChevrolet from a config entry."""
    token_dir = Path(hass.config.path(STORAGE_DIR)) / DOMAIN
    # pyonstar writes microsoft_tokens.json / gm_tokens.json here. If GM's bot
    # detection blocks the automated login, a manually captured token dropped
    # into this file is used directly (see README) instead of re-running the flow.
    token_dir.mkdir(parents=True, exist_ok=True)

    httpx_client = get_async_client(hass)

    onstar = OnStar(
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        device_id=entry.data.get("device_id", ""),
        vin=entry.data[CONF_VIN],
        totp_secret=entry.data.get("totp_secret", ""),
        onstar_pin=entry.data.get("onstar_pin", ""),
        token_location=str(token_dir),
        http_client=httpx_client,
    )

    coordinator = MyChevroletDataUpdateCoordinator(
        hass,
        onstar,
        entry,
        cheater_mode=entry.options.get(CONF_CHEATER_MODE, DEFAULT_CHEATER_MODE),
    )
    await coordinator.async_config_entry_first_refresh()

    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.data[CONF_VIN])},
        name=entry.title,
        manufacturer="Chevrolet",
        model="OnStar",
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "onstar": onstar,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_update_options))
    await async_setup_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MyChevroletConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        onstar: OnStar = hass.data[DOMAIN][entry.entry_id]["onstar"]
        await onstar.close()
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply a changed poll interval to the running coordinator."""
    coordinator: MyChevroletDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    coordinator.update_interval = timedelta(
        minutes=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )


def _coordinators(hass: HomeAssistant) -> list[MyChevroletDataUpdateCoordinator]:
    return [data["coordinator"] for data in hass.data.get(DOMAIN, {}).values()]


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register integration service actions once."""
    if hass.services.has_service(DOMAIN, "refresh_data"):
        return

    async def _handle_refresh(_call: ServiceCall) -> None:
        for coordinator in _coordinators(hass):
            await coordinator.async_refresh_data()

    hass.services.async_register(DOMAIN, "refresh_data", _handle_refresh)
