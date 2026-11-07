"""Unit tests for the vendored onyonstar library.

Tests JWT signature verification, JWKS fetching/caching, and token file
permissions — the security-critical parts of the OnStar client.
"""

from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from custom_components.mychevrolet.onyonstar.auth.gm_auth import GMAuth
from custom_components.mychevrolet.onyonstar.auth.constants import OIDC_ISSUER


def _make_rsa_keypair() -> tuple:
    """Generate an RSA key pair and return (private_key_pem, public_key_jwk_dict)."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    # Build a JWKS entry from the public key
    from jwt.algorithms import RSAAlgorithm

    jwk = RSAAlgorithm.to_jwk(public_key)
    jwk_dict = json.loads(jwk)
    jwk_dict["kid"] = "test-kid-1"
    jwk_dict["use"] = "sig"

    return private_pem, jwk_dict


def _make_signed_jwt(private_pem: bytes, payload: dict, kid: str = "test-kid-1") -> str:
    """Sign a JWT payload with the given private key."""
    return jwt.encode(
        payload,
        private_pem,
        algorithm="RS256",
        headers={"kid": kid},
    )


class TestJWKSCaching:
    """Test JWKS fetch and cache behavior."""

    @pytest.fixture
    def auth(self, tmp_path: Path) -> GMAuth:
        config = {
            "username": "test@example.com",
            "password": "secret",
            "device_id": "test-device",
            "totp_key": "JBSWY3DPEHPK3PXP",
            "token_location": str(tmp_path),
        }
        return GMAuth(config, debug=False)

    @pytest.mark.asyncio
    async def test_fetch_jwks_caches_result(self, auth: GMAuth) -> None:
        """Second call to _fetch_jwks returns cached data without re-fetching."""
        jwks_data = {"keys": [{"kid": "test-kid-1", "kty": "RSA"}]}

        mock_resp = MagicMock()
        mock_resp.json.return_value = jwks_data
        mock_resp.raise_for_status = MagicMock()

        auth._make_request = AsyncMock(return_value=mock_resp)
        auth._jwks_uri = "https://example.com/.well-known/jwks.json"

        # First call fetches
        result1 = await auth._fetch_jwks()
        assert result1 == jwks_data
        assert auth._make_request.await_count == 1

        # Second call returns from cache
        result2 = await auth._fetch_jwks()
        assert result2 == jwks_data
        assert auth._make_request.await_count == 1  # still 1, cached

    @pytest.mark.asyncio
    async def test_fetch_jwks_expires_after_ttl(self, auth: GMAuth) -> None:
        """JWKS cache expires after _jwks_ttl seconds."""
        jwks_data = {"keys": [{"kid": "test-kid-1", "kty": "RSA"}]}

        mock_resp = MagicMock()
        mock_resp.json.return_value = jwks_data
        mock_resp.raise_for_status = MagicMock()

        auth._make_request = AsyncMock(return_value=mock_resp)
        auth._jwks_uri = "https://example.com/.well-known/jwks.json"

        await auth._fetch_jwks()
        assert auth._make_request.await_count == 1

        # Simulate TTL expiry
        auth._jwks_fetched_at = time.time() - auth._jwks_ttl - 1

        await auth._fetch_jwks()
        assert auth._make_request.await_count == 2  # refetched

    @pytest.mark.asyncio
    async def test_fetch_jwks_no_uri_returns_none(self, auth: GMAuth) -> None:
        """_fetch_jwks returns None when no JWKS URI is configured."""
        auth._jwks_uri = None
        result = await auth._fetch_jwks()
        assert result is None


class TestVerifyJWT:
    """Test JWT signature verification."""

    @pytest.fixture
    def auth(self, tmp_path: Path) -> GMAuth:
        config = {
            "username": "test@example.com",
            "password": "secret",
            "device_id": "test-device",
            "totp_key": "JBSWY3DPEHPK3PXP",
            "token_location": str(tmp_path),
        }
        return GMAuth(config, debug=False)

    @pytest.mark.asyncio
    async def test_verify_jwt_valid_token(self, auth: GMAuth) -> None:
        """A properly signed JWT with matching kid verifies successfully."""
        private_pem, jwk_dict = _make_rsa_keypair()
        payload = {
            "vehs": [{"vin": "1HGABC1234567890X"}],
            "uid": "test@example.com",
            "iss": OIDC_ISSUER,
        }
        token = _make_signed_jwt(private_pem, payload)

        # Mock JWKS fetch to return our public key
        auth._fetch_jwks = AsyncMock(return_value={"keys": [jwk_dict]})

        decoded = await auth.verify_jwt(token, issuer=OIDC_ISSUER)
        assert decoded["vehs"][0]["vin"] == "1HGABC1234567890X"
        assert decoded["uid"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_verify_jwt_wrong_kid_raises(self, auth: GMAuth) -> None:
        """JWT with a kid not in JWKS raises ValueError."""
        private_pem, jwk_dict = _make_rsa_keypair()
        # Remove the kid we set, so it won't match
        jwk_dict.pop("kid", None)
        payload = {
            "vehs": [],
            "uid": "test@example.com",
            "iss": OIDC_ISSUER,
        }
        token = _make_signed_jwt(private_pem, payload, kid="missing-kid")

        auth._fetch_jwks = AsyncMock(return_value={"keys": [jwk_dict]})

        with pytest.raises(ValueError, match="No matching JWKS key found"):
            await auth.verify_jwt(token, issuer=OIDC_ISSUER)

    @pytest.mark.asyncio
    async def test_verify_jwt_no_kid_raises(self, auth: GMAuth) -> None:
        """JWT without a kid header raises ValueError."""
        private_pem, _ = _make_rsa_keypair()
        payload = {
            "vehs": [],
            "uid": "test@example.com",
            "iss": OIDC_ISSUER,
        }
        token = jwt.encode(payload, private_pem, algorithm="RS256")  # no kid header

        auth._fetch_jwks = AsyncMock(return_value={"keys": []})

        with pytest.raises(ValueError, match="missing 'kid' header"):
            await auth.verify_jwt(token, issuer=OIDC_ISSUER)

    @pytest.mark.asyncio
    async def test_verify_jwt_bad_signature_raises(self, auth: GMAuth) -> None:
        """JWT signed with a different key raises ValueError."""
        private_pem_a, jwk_dict_a = _make_rsa_keypair()
        private_pem_b, jwk_dict_b = _make_rsa_keypair()

        payload = {
            "vehs": [],
            "uid": "test@example.com",
            "iss": OIDC_ISSUER,
        }
        # Sign with key A but present JWKS with key B's public key
        token = _make_signed_jwt(private_pem_a, payload)

        auth._fetch_jwks = AsyncMock(return_value={"keys": [jwk_dict_b]})

        with pytest.raises(
            (jwt.InvalidSignatureError, ValueError),
        ):
            await auth.verify_jwt(token, issuer=OIDC_ISSUER)

    @pytest.mark.asyncio
    async def test_verify_jwt_no_jwks_raises(self, auth: GMAuth) -> None:
        """When JWKS is unavailable, verify_jwt raises ValueError."""
        private_pem, _ = _make_rsa_keypair()
        payload = {
            "vehs": [],
            "uid": "test@example.com",
            "iss": OIDC_ISSUER,
        }
        token = _make_signed_jwt(private_pem, payload)

        auth._fetch_jwks = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="JWKS unavailable"):
            await auth.verify_jwt(token, issuer=OIDC_ISSUER)


class TestTokenFilePermissions:
    """Test that token files are created with 0o600 permissions."""

    @pytest.fixture
    def auth(self, tmp_path: Path) -> GMAuth:
        config = {
            "username": "test@example.com",
            "password": "secret",
            "device_id": "test-device",
            "totp_key": "JBSWY3DPEHPK3PXP",
            "token_location": str(tmp_path),
        }
        return GMAuth(config, debug=False)

    @pytest.mark.asyncio
    async def test_save_tokens_sets_0600_permissions(self, auth: GMAuth) -> None:
        """_save_tokens writes token files with owner-only read/write."""
        token_set = {
            "access_token": "test-access-token",
            "expires_in": 3600,
            "expires_at": int(time.time()) + 3600,
        }
        auth._current_gm_token = {
            "access_token": "test-gm-token",
            "expires_in": 3600,
            "expires_at": int(time.time()) + 3600,
        }

        await auth._save_tokens(token_set)

        ms_stat = os.stat(auth._ms_token_path)
        gm_stat = os.stat(auth._gm_token_path)

        ms_mode = stat.S_IMODE(ms_stat.st_mode)
        gm_mode = stat.S_IMODE(gm_stat.st_mode)

        assert ms_mode == 0o600, f"Expected 0o600, got {oct(ms_mode)}"
        assert gm_mode == 0o600, f"Expected 0o600, got {oct(gm_mode)}"
