"""API utilities for OnStar client."""
import asyncio
import logging
import time
from typing import Any, Dict, Literal, Optional

import httpx

from .types import CommandResponseStatus

API_BASE = "https://na-mobile-api.gm.com/api/v1"
logger = logging.getLogger(__name__)


class OnStarAPIClient:
    """Client for making API requests to the OnStar API."""

    def __init__(
        self,
        *,
        request_polling_timeout_seconds: int = 90,
        request_polling_interval_seconds: int = 15,
        debug: bool = False,
        http_client: httpx.AsyncClient = None
    ) -> None:
        """Initialize OnStar API client.

        Parameters
        ----------
        request_polling_timeout_seconds
            Maximum time in seconds to poll for command status (default: 90)
        request_polling_interval_seconds
            Time in seconds to wait between status polling requests (default: 6)
        debug
            When *True* emits verbose debug output
        http_client
            Pre-configured httpx AsyncClient to use (if None, a new one will be created)
        """
        self._request_polling_timeout_seconds = request_polling_timeout_seconds
        self._request_polling_interval_seconds = request_polling_interval_seconds
        self._debug = debug
        
        # Store whether we created the client or if it was provided
        self._client_provided = http_client is not None
        # Create a shared client that will be reused across requests
        # This avoids the blocking SSL verification on each request
        self._client = http_client if http_client is not None else httpx.AsyncClient(verify=True)
        
    async def close(self):
        """Close the HTTP client session."""
        # Only close the client if we created it
        if not self._client_provided:
            await self._client.aclose()

    async def _check_request_pause(self) -> None:
        """Pause between status check requests."""
        await asyncio.sleep(self._request_polling_interval_seconds)

    async def api_request(
        self, 
        access_token: str,
        method: Literal["GET", "POST", "PUT", "DELETE"],
        path: str, 
        *, 
        json_body: Any | None = None,
        check_request_status: bool = True,
        poll_count: int = 0,
        max_polls: int | None = None
    ) -> Dict[str, Any]:
        """Make an authenticated request to the OnStar API.
        
        Parameters
        ----------
        access_token
            Valid access token for API authentication
        method
            HTTP method to use
        path
            API endpoint path (will be appended to API_BASE) or full URL
        json_body
            Optional JSON payload to send with the request
        check_request_status
            Whether to check and poll for command status completion
        poll_count
            Current poll attempt count (used internally)
        max_polls
            Maximum number of poll attempts (None = unlimited)
            
        Returns
        -------
        Dict[str, Any]
            JSON response from the API
        """
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
        }
        
        # Determine if path is a full URL or just a path
        if path.startswith("http"):
            url = path
        else:
            url = f"{API_BASE}{path}"
            
        logger.debug("%s %s", method, url)
        
        # Debug body
        if json_body and self._debug:
            logger.debug("Request body: %s", json_body)
        
        try:
            # Use the stored HTTP client instead of creating a new one
            response = await self._client.request(method, url, headers=headers, json=json_body)
            logger.debug("→ status=%s", response.status_code)
            
            # Log response body on error
            if response.status_code >= 400:
                logger.error("Response body: %s", response.text)
            
            response.raise_for_status()
            response_data = response.json()
            
            if self._debug:
                logger.debug("Response data: %s", response_data)

            # Handle command status polling if enabled and not already a status check
            if check_request_status and isinstance(response_data, dict):
                command_response = response_data.get("commandResponse")
                
                if command_response:
                    request_time = command_response.get("requestTime")
                    status = command_response.get("status")
                    status_url = command_response.get("url")
                    command_type = command_response.get("type")
                    
                    # Check for command failure
                    if status == CommandResponseStatus.FAILURE.value:
                        logger.error("Command failed: %s", response_data)
                        raise RuntimeError(f"Command failed: {response_data}")
                    
                    # If we have a success status with body data, return it
                    if status == CommandResponseStatus.SUCCESS.value and "body" in command_response:
                        return response_data
                    
                    # Check for maximum polls if specified
                    if max_polls is not None and poll_count >= max_polls:
                        logger.warning(f"Reached maximum poll count ({max_polls}), returning current response")
                        return response_data
                    
                    # Check for command timeout based on request timestamp if available
                    if request_time:
                        request_timestamp = time.mktime(time.strptime(request_time, "%Y-%m-%dT%H:%M:%S.%fZ"))
                        current_time = time.time()
                        if current_time >= request_timestamp + self._request_polling_timeout_seconds:
                            logger.error("Command timed out after %s seconds", self._request_polling_timeout_seconds)
                            raise RuntimeError(f"Command timed out after {self._request_polling_timeout_seconds} seconds")
                    
                    # For "connect" command, we don't continue polling
                    if command_type == "connect":
                        return response_data
                    
                    # For all other commands in non-success states with status URL, continue polling
                    if status_url and status != CommandResponseStatus.SUCCESS.value:
                        logger.debug(f"Command {command_type} in {status} state. Polling status from: {status_url}")
                        await self._check_request_pause()
                        
                        # Continue polling with incremented poll count
                        return await self.api_request(
                            access_token,
                            "GET", 
                            status_url,
                            check_request_status=check_request_status,
                            poll_count=poll_count + 1,
                            max_polls=max_polls
                        )
            
            return response_data
        except httpx.HTTPStatusError as e:
            logger.error("HTTP error: %s", e)
            # Try to parse the response JSON if possible
            try:
                error_body = e.response.json()
                logger.error("Error details: %s", error_body)
            except Exception:
                logger.error("Error response text: %s", e.response.text)
            raise
        except Exception as e:
            logger.error("Request failed: %s", e)
            raise 