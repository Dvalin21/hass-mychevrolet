"""
Python adaptation of GMAuth.ts from the OnStarJS project.
This module focuses exclusively on performing the Microsoft B2C + GM token
exchange so we can retrieve a valid GM API OAuth token.

This is a compatibility wrapper for the refactored auth module.

Dependencies:
    pip install httpx pyotp pyjwt
Optionally ``cryptography`` is required by ``pyjwt`` for some algorithms.

NOTE: This module now uses httpx for asynchronous HTTP requests.
The synchronous API is still available via sync_get_gm_api_jwt for backward compatibility.
"""

from .auth.types import Vehicle, DecodedPayload, GMAuthConfig, TokenSet, GMAPITokenResponse
from .auth.gm_auth import GMAuth
from .auth.api import get_gm_api_jwt, sync_get_gm_api_jwt

__all__ = [
    "GMAuth", 
    "get_gm_api_jwt",
    "sync_get_gm_api_jwt",
    "GMAPITokenResponse",
    "Vehicle",
    "DecodedPayload",
    "GMAuthConfig",
    "TokenSet"
] 