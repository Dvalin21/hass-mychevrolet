"""Async OnStar client that uses the GM Auth API."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, cast

import httpx
from .api import OnStarAPIClient
from .auth import GMAuth, get_gm_api_jwt, DecodedPayload
from .commands import CommandFactory
from .types import (
    AlertRequestOptions,
    ChargeOverrideOptions,
    DiagnosticsRequestOptions,
    DoorRequestOptions,
    SetChargingProfileRequestOptions,
    TrunkRequestOptions,
)

__all__ = ["OnStar"]

TOKEN_REFRESH_WINDOW_SECONDS = 5 * 60
logger = logging.getLogger(__name__)


class OnStar:
    """Simple async OnStar client.

    Parameters
    ----------
    username
        GM / OnStar account email.
    password
        Account password.
    device_id
        UUID used by the official app (can be random UUID4).
    vin
        Vehicle VIN – will be upper-cased automatically.
    onstar_pin
        Numeral account PIN (currently *unused* but kept for future endpoints).
    totp_secret
        16-char secret used for MFA (Third-party authenticator).
    token_location
        Directory where ``microsoft_tokens.json`` / ``gm_tokens.json`` will be
        cached (default: current working directory).
    check_request_status
        When *True* follows up on command requests until they complete (default: True).
    request_polling_timeout_seconds
        Maximum time in seconds to poll for command status (default: 90).
    request_polling_interval_seconds
        Time in seconds to wait between status polling requests (default: 6).
    debug
        When *True* emits verbose debug output from both *GMAuth* and the high-
        level client.
    http_client
        Pre-configured httpx AsyncClient to use (if None, a new one will be created).
        This is useful for integrations that need to handle SSL certificate loading in
        a specific way, like Home Assistant.
    """

    def __init__(
        self,
        *,
        username: str,
        password: str,
        device_id: str,
        vin: str,
        onstar_pin: str,
        totp_secret: str,
        token_location: str | None = None,
        check_request_status: bool = True,
        request_polling_timeout_seconds: int = 90,
        request_polling_interval_seconds: int = 15,
        debug: bool = False,
        http_client: httpx.AsyncClient = None,
    ) -> None:
        """Initialize OnStar client."""
        self._vin = vin.upper()
        self._setup_logging(debug)
        
        # Store the HTTP client for reuse
        self._http_client = http_client
        
        self._auth = self._create_auth(
            username=username,
            password=password,
            device_id=device_id,
            totp_secret=totp_secret,
            token_location=token_location or "./",
            debug=debug,
        )
        
        # Set up API client
        self._api_client = OnStarAPIClient(
            request_polling_timeout_seconds=request_polling_timeout_seconds,
            request_polling_interval_seconds=request_polling_interval_seconds,
            debug=debug,
            http_client=http_client,
        )
        
        # Command status tracking
        self._check_request_status = check_request_status
        
        # Token information
        self._token_resp: Optional[Dict[str, Any]] = None
        self._decoded_payload: Optional[DecodedPayload] = None
        
        # Store available commands
        self._available_commands: Dict[str, Dict[str, Any]] = {}
        self._vehicle_data: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _setup_logging(self, debug: bool) -> None:
        """Initialize logging configuration."""
        if debug:
            # Initialize basic logging config if debug is enabled.
            # This will only have an effect the first time it's called.
            logging.basicConfig(
                level=logging.DEBUG, 
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )

    def _create_auth(
        self,
        *,
        username: str,
        password: str,
        device_id: str,
        totp_secret: str,
        token_location: str,
        debug: bool,
    ) -> GMAuth:
        """Create and configure GMAuth instance."""
        return GMAuth(
            {
                "username": username,
                "password": password,
                "device_id": device_id,
                "totp_key": totp_secret,
                "token_location": token_location,
            },
            debug=debug,
            http_client=getattr(self, '_http_client', None),
        )

    def _needs_token_refresh(self, token: Dict[str, Any] | None) -> bool:
        """Check if the token needs to be refreshed."""
        if not token:
            return True
        return token.get("expires_at", 0) < int(time.time()) + TOKEN_REFRESH_WINDOW_SECONDS

    async def _ensure_token(self, force: bool = False) -> None:
        """Ensure a valid token is available, refreshing if necessary.
        
        Parameters
        ----------
        force
            When True, forces a token refresh even if the current token is still valid.
        """
        if force or self._needs_token_refresh(self._token_resp):
            logger.debug("Retrieving new GM auth token…")
            # Use the async get_gm_api_jwt function
            res = await get_gm_api_jwt(
                self._auth.config,  # Pass GMAuth's config directly
                debug=self._auth.debug,  # Pass the debug flag from GMAuth instance
                http_client=self._http_client,  # Pass the HTTP client
                force_refresh=force  # Pass force parameter to ignore cached tokens
            )
            self._token_resp = cast(Dict[str, Any], res["token"])
            self._decoded_payload = cast(DecodedPayload, res["decoded_payload"])

    def _get_command_url(self, command_name: str) -> str:
        """Get the URL for a specific command from the available commands."""
        if command_name in self._available_commands:
            return self._available_commands[command_name]["url"]
        
        # Fallback to hardcoded paths if command not found
        logger.warning(f"Command '{command_name}' not found in available commands, using fallback URL")
        return f"/account/vehicles/{self._vin}/commands/{command_name}"

    async def _api_request(
        self, 
        method: str,
        path: str, 
        *, 
        json_body: Any | None = None,
        check_request_status: bool | None = None,
        max_polls: int | None = None,
        force_token_refresh: bool = False
    ) -> Dict[str, Any]:
        """Make an authenticated request to the OnStar API."""
        await self._ensure_token(force=force_token_refresh)
        
        should_check_status = check_request_status if check_request_status is not None else self._check_request_status
        
        return await self._api_client.api_request(
            self._token_resp["access_token"],
            method,
            path,
            json_body=json_body,
            check_request_status=should_check_status,
            max_polls=max_polls
        )

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    async def get_account_vehicles(self) -> Dict[str, Any]:
        """Get all vehicles associated with the account."""
        response = await self._api_request(
            "GET", 
            "/account/vehicles?includeCommands=true&includeEntitlements=true&includeModules=true"
        )
        
        # Parse and store available commands for the current VIN
        if response and "vehicles" in response and "vehicle" in response["vehicles"]:
            for vehicle in response["vehicles"]["vehicle"]:
                if vehicle.get("vin") == self._vin and "commands" in vehicle and "command" in vehicle["commands"]:
                    # Store the full vehicle data
                    self._vehicle_data = vehicle
                    
                    # Process commands
                    commands = {}
                    for cmd in vehicle["commands"]["command"]:
                        if "name" in cmd and "url" in cmd:
                            commands[cmd["name"]] = cmd
                    
                    self._available_commands = commands
                    logger.debug(f"Stored {len(commands)} available commands for VIN {self._vin}")
        
        return response

    def is_command_available(self, command_name: str) -> bool:
        """Check if a specific command is available for the vehicle."""
        return command_name in self._available_commands
    
    def get_command_data(self, command_name: str) -> Dict[str, Any]:
        """Get additional data for a specific command."""
        if command_name in self._available_commands:
            return self._available_commands[command_name]
        return {}
        
    def requires_privileged_session(self, command_name: str) -> bool:
        """Check if a command requires a privileged session."""
        if command_name in self._available_commands:
            return self._available_commands[command_name].get("isPrivSessionRequired", "false") == "true"
        return False

    async def execute_command(self, command_name: str, request_body: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute any available command discovered from the API.
        
        This generic method allows executing any command available for the vehicle,
        even if not explicitly implemented as a method in this client.
        
        Parameters
        ----------
        command_name
            The name of the command to execute (must be in the available commands)
        request_body
            Optional JSON body to send with the request
            
        Returns
        -------
        Dict[str, Any]
            The command response
            
        Raises
        ------
        ValueError
            If the command is not available for this vehicle
        """
        if not self.is_command_available(command_name):
            logger.error(f"Command '{command_name}' not available for this vehicle")
            raise ValueError(f"Command '{command_name}' not available for this vehicle")
        
        return await self._api_request(
            "POST",
            self._get_command_url(command_name),
            json_body=request_body
        )

    # ------------------------------------------------------------------
    # Vehicle Commands
    # ------------------------------------------------------------------

    async def start(self) -> Dict[str, Any]:
        """Start the vehicle."""
        return await self.execute_command("start")

    async def cancel_start(self) -> Dict[str, Any]:
        """Cancel the start command."""
        return await self.execute_command("cancelStart")

    async def lock_door(self, options: Optional[DoorRequestOptions] = None) -> Dict[str, Any]:
        """Lock the vehicle doors."""
        return await self.execute_command("lockDoor", CommandFactory.lock_door(options))

    async def unlock_door(self, options: Optional[DoorRequestOptions] = None) -> Dict[str, Any]:
        """Unlock the vehicle doors."""
        return await self.execute_command("unlockDoor", CommandFactory.unlock_door(options))

    async def lock_trunk(self, options: Optional[TrunkRequestOptions] = None) -> Dict[str, Any]:
        """Lock the vehicle trunk."""
        return await self.execute_command("lockTrunk", CommandFactory.lock_trunk(options))

    async def unlock_trunk(self, options: Optional[TrunkRequestOptions] = None) -> Dict[str, Any]:
        """Unlock the vehicle trunk."""
        return await self.execute_command("unlockTrunk", CommandFactory.unlock_trunk(options))

    async def alert(self, options: Optional[AlertRequestOptions] = None) -> Dict[str, Any]:
        """Trigger the vehicle alert (honk/flash)."""
        return await self.execute_command("alert", CommandFactory.alert(options))

    async def cancel_alert(self) -> Dict[str, Any]:
        """Cancel the alert command."""
        return await self.execute_command("cancelAlert")

    async def charge_override(self, options: Optional[ChargeOverrideOptions] = None) -> Dict[str, Any]:
        """Override vehicle charging settings."""
        return await self.execute_command("chargeOverride", CommandFactory.charge_override(options))

    async def get_charging_profile(self) -> Dict[str, Any]:
        """Get the vehicle charging profile."""
        return await self.execute_command("getChargingProfile")

    async def set_charging_profile(self, options: Optional[SetChargingProfileRequestOptions] = None) -> Dict[str, Any]:
        """Set the vehicle charging profile."""
        return await self.execute_command(
            "setChargingProfile", 
            CommandFactory.set_charging_profile(options)
        )

    async def get_charger_power_level(self) -> Dict[str, Any]:
        """Get the vehicle's charger power level."""
        return await self.execute_command("getChargerPowerLevel")
        
    def get_supported_diagnostics(self) -> List[str]:
        """Get the list of diagnostic items supported by the vehicle."""
        supported_diagnostics = []
        command_data = self.get_command_data("diagnostics")
        
        if (command_data and "commandData" in command_data and 
                "supportedDiagnostics" in command_data["commandData"] and 
                "supportedDiagnostic" in command_data["commandData"]["supportedDiagnostics"]):
            supported_diagnostics = command_data["commandData"]["supportedDiagnostics"]["supportedDiagnostic"]
            
        return supported_diagnostics

    async def diagnostics(
        self, 
        options: Optional[DiagnosticsRequestOptions] = None, 
        timeout_seconds: int = 180, 
        max_polls: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get diagnostic data from the vehicle."""
        if not self.is_command_available("diagnostics"):
            logger.error("Diagnostics command not available for this vehicle")
            raise ValueError("Diagnostics command not available for this vehicle")
            
        # Get supported diagnostics
        supported_diagnostics = self.get_supported_diagnostics()
        
        if not supported_diagnostics:
            logger.warning("No supported diagnostics found for this vehicle")
            
        # Process requested diagnostic items
        requested_items = None
        if options and "diagnostic_item" in options:
            requested_items = options["diagnostic_item"]
            
            # Validate that requested items are supported
            unsupported = [item for item in requested_items if item not in supported_diagnostics]
            if unsupported:
                logger.warning(f"Requested unsupported diagnostic items: {unsupported}")
                logger.warning(f"Supported items: {supported_diagnostics}")
                
            # Filter to only include supported items
            requested_items = [item for item in requested_items if item in supported_diagnostics]
            
            if not requested_items:
                logger.error("None of the requested diagnostic items are supported")
                raise ValueError("None of the requested diagnostic items are supported")
        
        # Build request body with CommandFactory
        diagnostic_items = requested_items if requested_items else supported_diagnostics
        body = CommandFactory.diagnostics(diagnostic_items)
        
        # Use extended timeout for diagnostics
        return await self._api_request(
            "POST",
            self._get_command_url("diagnostics"),
            json_body=body,
            check_request_status=True,
            max_polls=max_polls
        )
        
    async def location(self) -> Dict[str, Any]:
        """Get the vehicle's current location."""
        return await self.execute_command("location")

    def get_vehicle_data(self) -> Dict[str, Any]:
        """Get the full vehicle data that was retrieved during get_account_vehicles."""
        if not self._vehicle_data:
            logger.warning("Vehicle data not available. Call get_account_vehicles() first.")
            return {}
        return self._vehicle_data
    
    def get_entitlements(self) -> List[Dict[str, Any]]:
        """Get the list of entitlements for the vehicle."""
        if not self._vehicle_data or "entitlements" not in self._vehicle_data:
            logger.warning("Entitlements not available. Call get_account_vehicles() first.")
            return []
        
        if "entitlement" in self._vehicle_data["entitlements"]:
            return self._vehicle_data["entitlements"]["entitlement"]
        return []
    
    def is_entitled(self, entitlement_id: str) -> bool:
        """Check if the vehicle is entitled to a specific feature."""
        entitlements = self.get_entitlements()
        for entitlement in entitlements:
            if entitlement.get("id") == entitlement_id and entitlement.get("eligible") == "true":
                return True
        return False

    def get_supported_hvac_settings(self) -> Dict[str, Any]:
        """Get the supported HVAC settings for the vehicle."""
        if not self._available_commands or "setHvacSettings" not in self._available_commands:
            logger.warning("HVAC settings command not available. Call get_account_vehicles() first.")
            return {}
        
        hvac_command = self._available_commands["setHvacSettings"]
        if "commandData" in hvac_command and "supportedHvacData" in hvac_command["commandData"]:
            return hvac_command["commandData"]["supportedHvacData"]
        return {}
        
    async def set_hvac_settings(self, ac_mode: Optional[str] = None, heated_steering_wheel: Optional[bool] = None) -> Dict[str, Any]:
        """Set HVAC settings for the vehicle."""
        if not self.is_command_available("setHvacSettings"):
            logger.error("setHvacSettings command not available for this vehicle")
            raise ValueError("setHvacSettings command not available for this vehicle")
        
        # Get supported settings to validate inputs
        supported_settings = self.get_supported_hvac_settings()
        
        # Validate AC climate mode if provided
        if ac_mode is not None:
            supported_modes = []
            if "supportedAcClimateModeSettings" in supported_settings:
                supported_modes = supported_settings["supportedAcClimateModeSettings"].get("supportedAcClimateModeSetting", [])
            
            if supported_modes and ac_mode not in supported_modes:
                supported_str = ", ".join(supported_modes) if supported_modes else "none"
                logger.warning(f"Unsupported AC climate mode: {ac_mode}. Supported modes: {supported_str}")
        
        # Validate heated steering wheel if provided
        if heated_steering_wheel is not None:
            is_supported = supported_settings.get("heatedSteeringWheelSupported", "false") == "true"
            if not is_supported:
                logger.warning("Heated steering wheel not supported by this vehicle")
        
        # Create command payload and execute
        return await self.execute_command(
            "setHvacSettings", 
            CommandFactory.set_hvac_settings(ac_mode, heated_steering_wheel)
        )

    async def close(self):
        """Close the API client and release resources."""
        if hasattr(self, '_api_client'):
            await self._api_client.close()

    # ------------------------------------------------------------------
    # Authentication methods
    # ------------------------------------------------------------------

    async def force_token_refresh(self) -> bool:
        """Force a refresh of the access token regardless of expiration status.
        
        This can be useful when working with failed API requests or when you suspect
        the token might have been invalidated on the server side.
        
        Returns
        -------
        bool
            True if token was successfully refreshed, False otherwise
        """
        try:
            logger.debug("Forcing token refresh...")
            await self._ensure_token(force=True)
            return True
        except Exception as e:
            logger.error(f"Error forcing token refresh: {e}")
            return False 