"""Type definitions for the OnStar authentication module."""

from typing import Dict, List, Optional, TypedDict, Union

class Vehicle(TypedDict):
    vin: str
    per: str


class DecodedPayload(TypedDict, total=False):
    vehs: List[Vehicle]
    uid: str  # user identifier (email)


class GMAuthConfig(TypedDict, total=False):
    username: str
    password: str
    device_id: str
    totp_key: str
    token_location: str


class TokenSet(TypedDict, total=False):
    access_token: str
    id_token: str
    refresh_token: str
    expires_at: int
    expires_in: int


class GMAPITokenResponse(TypedDict, total=False):
    access_token: str
    expires_in: int
    expires_at: int
    token_type: str
    scope: str
    id_token: str
    expiration: int
    upgraded: bool
    onstar_account_info: dict
    user_info: dict 