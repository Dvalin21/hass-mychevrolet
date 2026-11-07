"""Config flow for the myChevrolet integration."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.httpx_client import get_async_client
from .onyonstar import OnStar

from .const import (
    CONF_CHEATER_MODE,
    CONF_SCAN_INTERVAL,
    CONF_TOTP_SECRET,
    CONF_VIN,
    DEFAULT_CHEATER_MODE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_VIN): str,
        vol.Optional(CONF_TOTP_SECRET): str,
        vol.Optional("device_id", default=""): str,
        vol.Optional("onstar_pin", default=""): str,
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=1440)
        ),
        vol.Required(CONF_CHEATER_MODE, default=DEFAULT_CHEATER_MODE): bool,
    }
)


async def _validate(hass: HomeAssistant, user_input: dict[str, Any]) -> str:
    """Authenticate and confirm the vehicle belongs to the account.

    Returns the display title. Raises InvalidAuth / CannotConnect.
    """
    device_id = (user_input.get("device_id") or "").strip() or str(uuid.uuid4())
    httpx_client = get_async_client(hass)
    onstar = OnStar(
        username=user_input[CONF_USERNAME],
        password=user_input[CONF_PASSWORD],
        device_id=device_id,
        vin=user_input[CONF_VIN].strip().upper(),
        totp_secret=user_input.get(CONF_TOTP_SECRET, ""),
        onstar_pin=user_input.get("onstar_pin", ""),
        http_client=httpx_client,
    )
    try:
        await onstar.get_account_vehicles()
        vehicle = onstar.get_vehicle_data()
    except httpx.HTTPStatusError as err:
        if err.response.status_code in (401, 403):
            raise InvalidAuth(str(err)) from err
        raise CannotConnect(str(err)) from err
    except (httpx.RequestError, RuntimeError, ValueError, KeyError) as err:
        text = str(err).lower()
        if any(kw in text for kw in ("unauthorized", "access denied", "auth", "token", "login")):
            raise InvalidAuth(str(err)) from err
        raise CannotConnect(str(err)) from err
    except HomeAssistantError:
        raise
    finally:
        # httpx_client is HA's shared session; do not close it.
        pass

    name = (vehicle or {}).get("name") or user_input[CONF_VIN].strip().upper()
    return f"{name} ({user_input[CONF_VIN].strip().upper()})"


class MyChevroletConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial config flow for myChevrolet."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect credentials and validate against the OnStar cloud."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                title = await _validate(self.hass, user_input)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error in myChevrolet config flow")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_input[CONF_VIN].strip().upper())
                self._abort_if_unique_id_configured()
                device_id = (user_input.get("device_id") or "").strip() or str(
                    uuid.uuid4()
                )
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_VIN: user_input[CONF_VIN].strip().upper(),
                        CONF_TOTP_SECRET: user_input.get(CONF_TOTP_SECRET, ""),
                        "device_id": device_id,
                        "onstar_pin": user_input.get("onstar_pin", ""),
                    },
                )

        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Kick off a reauth when the cloud rejects stored credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Prompt the user to re-enter credentials for an existing entry."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        entry_data = entry.data
        if user_input is not None:
            try:
                await _validate(self.hass, {**entry_data, **user_input})
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during myChevrolet reauth")
                errors["base"] = "unknown"
            else:
                device_id = (user_input.get("device_id") or "").strip() or entry.data.get(
                    "device_id", str(uuid.uuid4())
                )
                self.async_update_reload_and_abort(
                    entry,
                    data={
                        **entry.data,
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_TOTP_SECRET: user_input.get(CONF_TOTP_SECRET, entry.data.get(CONF_TOTP_SECRET, "")),
                        "device_id": device_id,
                    },
                )
                # async_update_reload_and_abort returns None; never reached.
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=entry_data.get(CONF_USERNAME)): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional(CONF_TOTP_SECRET, default=entry_data.get(CONF_TOTP_SECRET, "")): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow."""
        return MyChevroletOptionsFlow()


class MyChevroletOptionsFlow(config_entries.OptionsFlow):
    """Handle myChevrolet options (poll interval, cheater mode)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Persist options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=OPTIONS_SCHEMA,
        )


class InvalidAuth(HomeAssistantError):
    """Credentials were rejected by the OnStar cloud."""


class CannotConnect(HomeAssistantError):
    """The OnStar cloud could not be reached."""
