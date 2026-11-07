"""
Python adaptation of GMAuth.ts from the OnStarJS project.
This module focuses exclusively on performing the Microsoft B2C + GM token
exchange so we can retrieve a valid GM API OAuth token.
"""

from .types import Vehicle, DecodedPayload, GMAuthConfig, TokenSet, GMAPITokenResponse
from .gm_auth import GMAuth
from .api import get_gm_api_jwt, sync_get_gm_api_jwt

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