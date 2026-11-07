"""API functions for OnStar authentication."""

from typing import Optional
import httpx

from .types import GMAuthConfig, DecodedPayload
from .gm_auth import GMAuth


async def get_gm_api_jwt(config: GMAuthConfig, debug: bool = False, http_client: Optional[httpx.AsyncClient] = None, force_refresh: bool = False):
    """Convenience wrapper to get a GM API JWT token.
    
    Args:
        config: Configuration for authentication
        debug: Enable debug logging
        http_client: Optional pre-configured httpx client
        force_refresh: When True, forces a complete re-authentication ignoring cached tokens
        
    Returns:
        dict: Contains token, auth instance, and decoded payload
    
    Raises:
        ValueError: If required configuration keys are missing
    """
    required = ["username", "password", "device_id", "totp_key"]
    for key in required:
        if not config.get(key):
            raise ValueError(f"Missing required configuration key: {key}")

    auth = GMAuth(config, debug=debug, http_client=http_client)
    token_resp = await auth.authenticate(force_refresh=force_refresh)
    decoded: DecodedPayload = await auth.verify_jwt(
        token_resp["access_token"],
    )  # type: ignore[arg-type]
    return {
        "token": token_resp,
        "auth": auth,
        "decoded_payload": decoded,
    }