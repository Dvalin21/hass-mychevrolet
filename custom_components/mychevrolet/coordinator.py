"""Data update coordinator for the myChevrolet integration.

Wraps the ``pyonstar`` client (a Python port of OnStarJS). Each refresh:
enumerate the account's vehicles, then request live diagnostics + location.
Diagnostics is the expensive, rate-limited call, so GM's cloud is polled on a
~30-minute cadence; tight polling just buys 500/429 errors.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import httpx
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_CHEATER_MODE,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    RATE_LIMIT_BACKOFF,
    RATE_LIMIT_STATUS_CODE,
    UPDATE_TIMEOUT_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

type MyChevroletConfigEntry = ConfigEntry


def _looks_like_auth_failure(err: BaseException) -> bool:
    """Best-effort guess that an error is an authentication failure.

    pyonstar raises plain ``RuntimeError`` / ``httpx.HTTPStatusError`` with no
    dedicated auth type, so we key on HTTP status and message substrings. This
    heuristic is unverified against a live account (no credentials available in
    development) — refine once real error strings are observed.
    """
    if isinstance(err, httpx.HTTPStatusError):
        return err.response.status_code in (401, 403)
    text = str(err).lower()
    return any(
        kw in text
        for kw in ("unauthorized", "access denied", "auth", "token", "login")
    )


class MyChevroletDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate fetching vehicle data from the OnStar cloud."""

    config_entry: MyChevroletConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        onstar: Any,
        config_entry: MyChevroletConfigEntry,
        *,
        cheater_mode: bool = False,
    ) -> None:
        """Initialise the coordinator."""
        scan_minutes = config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=scan_minutes),
        )
        self.onstar = onstar
        self.config_entry = config_entry
        self.cheater_mode = config_entry.data.get(CONF_CHEATER_MODE, cheater_mode)
        self._last_diagnostics = 0.0
        self._last_location = 0.0
        self._diagnostics_backoff_until = 0.0
        self._location_backoff_until = 0.0

    @property
    def vehicle_data(self) -> dict[str, Any] | None:
        """Return the enumerated vehicle record (commands/entitlements)."""
        return self.onstar.get_vehicle_data() if self.data else None

    def command_available(self, name: str) -> bool:
        """Whether a remote command is offered for this vehicle."""
        return bool(self.data) and self.onstar.is_command_available(name)

    async def _fetch(self, endpoint: str, fetch: Callable[[], Any]) -> Any:
        """Run an endpoint fetch with rate-limit backoff and error mapping."""
        now = time.time()
        if not self.cheater_mode:
            backoff = (
                self._diagnostics_backoff_until
                if endpoint == "diagnostics"
                else self._location_backoff_until
            )
            if now < backoff:
                _LOGGER.debug("Skipping %s: rate-limit backoff until %s", endpoint, backoff)
                return self.data.get(endpoint) if self.data else None

        try:
            return await asyncio.wait_for(fetch(), timeout=UPDATE_TIMEOUT_SECONDS)
        except TimeoutError as err:
            msg = f"Timeout fetching {endpoint} from OnStar"
            _LOGGER.warning(msg)
            raise UpdateFailed(msg) from err
        except httpx.HTTPStatusError as err:
            if err.response.status_code == RATE_LIMIT_STATUS_CODE:
                return await self._handle_rate_limit(endpoint)
            msg = f"HTTP {err.response.status_code} fetching {endpoint}: {err}"
            _LOGGER.warning(msg)
            raise UpdateFailed(msg) from err
        except (RuntimeError, ValueError, KeyError) as err:
            if _looks_like_auth_failure(err):
                # Surface auth failures so the entry can trigger re-auth.
                raise ConfigEntryAuthFailed(f"OnStar authentication failed: {err}") from err
            msg = f"Invalid or failed {endpoint} response: {err}"
            _LOGGER.warning(msg)
            raise UpdateFailed(msg) from err

    async def _handle_rate_limit(self, endpoint: str) -> Any:
        """React to a 429: recreate the client in cheater mode, else back off."""
        if self.cheater_mode:
            _LOGGER.warning("Rate limited on %s; recreating client (cheater mode)", endpoint)
            await self._recreate_client()
            return self.data.get(endpoint) if self.data else None
        self._diagnostics_backoff_until = time.time() + RATE_LIMIT_BACKOFF.total_seconds()
        self._location_backoff_until = self._diagnostics_backoff_until
        _LOGGER.warning(
            "Rate limited on %s; backing off %s", endpoint, RATE_LIMIT_BACKOFF
        )
        return self.data.get(endpoint) if self.data else None

    async def _recreate_client(self) -> None:
        """Recreate the OnStar client with a fresh device id to escape a 429 bucket."""
        from homeassistant.helpers.httpx_client import get_async_client

        new_device_id = str(uuid.uuid4())
        _LOGGER.warning("Recreating OnStar client with new device id: %s", new_device_id)
        try:
            await self.onstar.close()
        except Exception:
            _LOGGER.debug("Error closing OnStar client before recreate", exc_info=True)

        self.onstar = type(self.onstar)(
            username=self.config_entry.data[CONF_USERNAME],
            password=self.config_entry.data[CONF_PASSWORD],
            device_id=new_device_id,
            vin=self.config_entry.data["vin"],
            totp_secret=self.config_entry.data.get("totp_secret", ""),
            onstar_pin="",
            http_client=get_async_client(self.hass),
        )
        self.hass.data.setdefault(DOMAIN, {})[self.config_entry.entry_id]["onstar"] = (
            self.onstar
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch vehicles, then live diagnostics + location in parallel."""
        try:
            await asyncio.wait_for(
                self.onstar.get_account_vehicles(), timeout=UPDATE_TIMEOUT_SECONDS
            )
        except httpx.HTTPStatusError as err:
            if err.response.status_code in (401, 403):
                raise ConfigEntryAuthFailed(
                    f"OnStar authentication failed: {err}"
                ) from err
            msg = f"Failed to enumerate vehicles: {err}"
            raise UpdateFailed(msg) from err
        except (RuntimeError, ValueError, KeyError) as err:
            if _looks_like_auth_failure(err):
                raise ConfigEntryAuthFailed(
                    f"OnStar authentication failed: {err}"
                ) from err
            msg = f"Failed to enumerate vehicles: {err}"
            raise UpdateFailed(msg) from err

        location, diagnostics = await asyncio.gather(
            self._fetch("location", self.onstar.location),
            self._fetch("diagnostics", self.onstar.diagnostics),
            return_exceptions=True,
        )
        if isinstance(location, Exception) or isinstance(diagnostics, Exception):
            # One leg failing must not wipe the whole update; keep what we have.
            location = self.data.get("location") if self.data else None
            diagnostics = self.data.get("diagnostics") if self.data else None

        return {"location": location, "diagnostics": diagnostics}

    # -- Remote commands ---------------------------------------------------

    async def _run_command(self, coro: Any, what: str) -> None:
        """Await a pyonstar command, mapping its failures to HA errors."""
        try:
            result = await asyncio.wait_for(coro, timeout=UPDATE_TIMEOUT_SECONDS)
        except TimeoutError as err:
            raise HomeAssistantError(f"{what}: timed out waiting for OnStar") from err
        except httpx.HTTPStatusError as err:
            if err.response.status_code == RATE_LIMIT_STATUS_CODE:
                await self._handle_rate_limit("command")
                raise HomeAssistantError(
                    f"{what}: rate limited by OnStar"
                ) from err
            raise HomeAssistantError(f"{what}: HTTP {err.response.status_code}") from err
        except RuntimeError as err:
            raise HomeAssistantError(f"{what}: {err}") from err
        else:
            # Command accepted; pull fresh data so entities reflect the change.
            await self.async_refresh()
            return result

    async def async_lock_doors(self) -> None:
        """Lock the vehicle doors."""
        await self._run_command(self.onstar.lock_door(), "Lock doors")

    async def async_unlock_doors(self) -> None:
        """Unlock the vehicle doors."""
        await self._run_command(self.onstar.unlock_door(), "Unlock doors")

    async def async_remote_start(self) -> None:
        """Remotely start the engine."""
        await self._run_command(self.onstar.start(), "Remote start")

    async def async_remote_stop(self) -> None:
        """Remotely stop the engine."""
        await self._run_command(self.onstar.cancel_start(), "Remote stop")

    async def async_honk_flash(self) -> None:
        """Honk and flash (alert)."""
        await self._run_command(self.onstar.alert(), "Honk and flash")

    async def async_refresh_data(self) -> None:
        """Force an immediate data refresh now."""
        await self.async_refresh()
