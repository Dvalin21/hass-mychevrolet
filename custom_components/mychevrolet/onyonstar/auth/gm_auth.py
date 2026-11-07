"""GMAuth class implementation for OnStar authentication."""

import hashlib
import json
import logging
import secrets
import time
from pathlib import Path
from typing import Dict, Optional, Tuple, Union, Any

import httpx
import pyotp
import jwt  # PyJWT
import aiofiles

from .constants import (
    CLIENT_ID,
    AUTH_REDIRECT_URI,
    REDIRECT_URI,
    SCOPE_STRING,
    DISCOVERY_URL,
    FALLBACK_AUTHORIZATION_ENDPOINT,
    FALLBACK_TOKEN_ENDPOINT,
    GM_TOKEN_ENDPOINT,
    COMMON_HEADERS,
    SELF_ASSERTED_PATH,
    SELF_ASSERTED_CONFIRMED_PATH,
    COMBINED_SIGNIN_CONFIRMED_PATH,
    ACCEPT_HTML_HEADER,
    ACCEPT_JSON_HEADER,
    FORM_URLENCODED_HEADER,
    JSON_HEADER,
    ORIGIN_HEADER,
    XML_REQUEST_HEADER,
    TOKEN_REFRESH_BUFFER,
    GM_TOKEN_SCOPE,
)
from .types import GMAuthConfig, TokenSet, GMAPITokenResponse, DecodedPayload
from .utils import urlsafe_b64encode, is_token_valid, regex_extract, build_custlogin_url

logger = logging.getLogger(__name__)


class GMAuth:
    """Re-implementation of the TypeScript *GMAuth* class in Python using async httpx."""

    def __init__(self, config: GMAuthConfig, debug: bool = False, http_client: httpx.AsyncClient = None):
        self.config: GMAuthConfig = config
        # Ensure token_location is set and paths exist
        token_location = Path(self.config.get("token_location", "./"))
        token_location.mkdir(parents=True, exist_ok=True)
        self._ms_token_path = token_location / "microsoft_tokens.json"
        self._gm_token_path = token_location / "gm_tokens.json"

        # Storage for current GM token
        self._current_gm_token: Optional[GMAPITokenResponse] = None

        self.debug = debug

        # Default token endpoint (may be updated after discovery)
        self._token_endpoint: str = FALLBACK_TOKEN_ENDPOINT

        # Skip token loading in constructor since it's now async
        # We'll load tokens on-demand during authenticate()

        # OIDC metadata (fetched dynamically)
        self._oidc_metadata: Optional[Dict] = None
        
        # Cookie jar for session persistence
        self._cookies = httpx.Cookies()
        
        # Custom HTTP client (if provided)
        self._http_client = http_client
        self._client_provided = http_client is not None

    # ------------------------------------------------------------------
    # HTTP request helper methods
    # ------------------------------------------------------------------
    
    async def _make_request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Make an HTTP request using either the provided client or a new one.
        
        Args:
            method: HTTP method ('GET', 'POST', etc.)
            url: Request URL
            **kwargs: Additional arguments to pass to the request method
            
        Returns:
            httpx.Response: The response object
        """
        # Extract client kwargs from request kwargs
        client_kwargs = {}
        request_kwargs = kwargs.copy()
        
        # Extract the common client parameters if present
        for param in ['cookies', 'follow_redirects']:
            if param in request_kwargs:
                client_kwargs[param] = request_kwargs.pop(param)
        
        if self._http_client:
            # Use the provided client with all kwargs
            return await getattr(self._http_client, method.lower())(url, **kwargs)
        else:
            # Create a new client with extracted kwargs, then make the request
            async with httpx.AsyncClient(**client_kwargs) as client:
                return await getattr(client, method.lower())(url, **request_kwargs)

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    async def authenticate(self, force_refresh: bool = False) -> GMAPITokenResponse:
        """Return a *valid* GM API OAuth token, performing auth flow when required.
        
        Parameters
        ----------
        force_refresh
            When True, forces a new GM token exchange even if current token is valid
        """

        if self.debug:
            logger.debug("[GMAuth] Starting authentication flow…")
            
        # Ensure GM token is loaded if available and not forcing refresh
        if self._current_gm_token is None and not force_refresh:
            await self._load_current_gm_api_token()
            
        # Check if current GM token is valid (unless we're forcing a refresh)
        if not force_refresh and self._current_gm_token and is_token_valid(self._current_gm_token, TOKEN_REFRESH_BUFFER):
            if self.debug:
                logger.debug("[GMAuth] Using cached GM API token")
            return self._current_gm_token

        # Try to use existing MS token (even when forcing refresh)
        token_set = await self._load_ms_token()
        if token_set is not False:
            if self.debug:
                if force_refresh:
                    logger.debug("[GMAuth] Force refresh requested, exchanging MS tokens for new GM token...")
                else:
                    logger.debug("[GMAuth] Successfully loaded cached MS tokens → exchanging for GM token…")
            return await self._get_gm_api_token(token_set)

        # Full authentication required
        if self.debug:
            logger.debug("[GMAuth] Performing full MS B2C authentication…")

        token_set = await self._do_full_auth_sequence()
        return await self._get_gm_api_token(token_set)

    # ---------------------------------------------------------------------
    # Internal helpers – Microsoft identity platform
    # ---------------------------------------------------------------------

    async def _do_full_auth_sequence(self) -> TokenSet:
        auth_url, code_verifier = await self._start_ms_authorization_flow()

        # ── GET authorization page – extract CSRF + transaction IDs ──
        resp = await self._get_request(auth_url)
        csrf = regex_extract(resp, r'\"csrf\":\"(.*?)\"')
        trans_id = regex_extract(resp, r'\"transId\":\"(.*?)\"')
        if not csrf or not trans_id:
            raise RuntimeError("Failed to locate csrf or transId in authorization page")

        if self.debug:
            logger.debug(f"[GMAuth] csrf={csrf}  trans_id={trans_id}")

        # ── Submit user credentials ──
        await self._submit_credentials(csrf, trans_id)

        # ── Handle MFA (TOTP only) ──
        csrf, trans_id = await self._handle_mfa(csrf, trans_id)

        # ── Retrieve authorization *code* from redirect ──
        auth_code = await self._get_authorization_code(csrf, trans_id)
        if not auth_code:
            raise RuntimeError("Failed to get authorization code after login/MFA")

        if self.debug:
            logger.debug(f"[GMAuth] Received authorization code: {auth_code[:6]}…")

        # ── Exchange *code* + *code_verifier* for *tokens* ──
        token_set = await self._fetch_ms_token(auth_code, code_verifier)

        # ── Persist ──
        await self._save_tokens(token_set)
        return token_set

    # ------------------------------------------------------------------
    # Microsoft OIDC helpers
    # ------------------------------------------------------------------

    async def _start_ms_authorization_flow(self) -> Tuple[str, str]:
        """Return (authorization_url, code_verifier) using discovery when possible."""

        # Discover
        auth_ep, token_ep = await self._get_oidc_endpoints()
        self._token_endpoint = token_ep  # store for later token/refresh calls

        code_verifier = urlsafe_b64encode(secrets.token_bytes(32))
        code_challenge = urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        state = urlsafe_b64encode(secrets.token_bytes(16))

        params = {
            "client_id": CLIENT_ID,
            "response_type": "code",
            "redirect_uri": AUTH_REDIRECT_URI,
            "scope": SCOPE_STRING,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            # Mobile app specific params (mimic myChevrolet)
            "bundleID": "com.gm.myChevrolet",
            "mode": "dark",
            "evar25": "mobile_mychevrolet_chevrolet_us_app_launcher_sign_in_or_create_account",
            "channel": "lightreg",
            "ui_locales": "en-US",
            "brand": "chevrolet",
            "state": state,
        }

        # Use httpx's standard URL parameter encoding
        query_params = httpx.QueryParams(params)
        authorization_url = f"{auth_ep}?{query_params}"
        
        if self.debug:
            logger.debug(f"[GMAuth] Authorization endpoint: {auth_ep}")
            logger.debug(f"[GMAuth] Token endpoint: {token_ep}")
            logger.debug(f"[GMAuth] Generated authorization URL: {authorization_url}")
        return authorization_url, code_verifier

    # ------------------------------------------------------------------
    # OpenID configuration discovery
    # ------------------------------------------------------------------

    async def _get_oidc_endpoints(self) -> Tuple[str, str]:
        """Return (authorization_endpoint, token_endpoint) using run-time discovery when possible."""

        try:
            if self.debug:
                logger.debug(f"[GMAuth] Fetching OIDC discovery metadata → {DISCOVERY_URL}")
            
            # Make a request using the helper
            headers = {**COMMON_HEADERS, **JSON_HEADER}
            resp = await self._make_request('GET', DISCOVERY_URL, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            auth_ep = data.get("authorization_endpoint", FALLBACK_AUTHORIZATION_ENDPOINT)
            token_ep = data.get("token_endpoint", FALLBACK_TOKEN_ENDPOINT)
            return auth_ep, token_ep
        except Exception as exc:
            if self.debug:
                logger.debug(f"[GMAuth] Discovery failed – falling back to hard-coded endpoints ({exc})")
            return FALLBACK_AUTHORIZATION_ENDPOINT, FALLBACK_TOKEN_ENDPOINT

    # ------------------------------------------------------------------
    # HTTP flow helper methods (GET/POST with debug + cookie mgmt)
    # ------------------------------------------------------------------

    async def _get_request(self, url: str) -> str:
        """Make a GET request and return the response text."""
        if self.debug:
            logger.debug(f"[GMAuth][GET ] {url}")
        
        headers = {**COMMON_HEADERS, **ACCEPT_HTML_HEADER}
        
        # Use the helper method
        resp = await self._make_request(
            'GET', 
            url, 
            headers=headers, 
            cookies=self._cookies, 
            follow_redirects=False
        )
        resp.raise_for_status()
        
        # Update cookies from response
        self._update_cookies_from_response(resp)
        
        return resp.text

    async def _post_request(self, url: str, data: Union[Dict[str, str], str], csrf_token: str, 
                           extra_headers: Optional[Dict[str, str]] = None) -> httpx.Response:
        """Make a POST request and return the full response."""
        if self.debug:
            logger.debug(f"[GMAuth][POST] {url}  data={data}")

        # Combine headers
        request_specific_headers = {
            **COMMON_HEADERS,
            **FORM_URLENCODED_HEADER,
            **ACCEPT_JSON_HEADER,
            **ORIGIN_HEADER,
            **XML_REQUEST_HEADER,
            "x-csrf-token": csrf_token,
            **(extra_headers if extra_headers else {}),
        }
        
        # Use the helper method
        resp = await self._make_request(
            'POST', 
            url, 
            data=data, 
            headers=request_specific_headers, 
            cookies=self._cookies, 
            follow_redirects=False
        )
        resp.raise_for_status()
        
        # Update cookies from response
        self._update_cookies_from_response(resp)
        
        return resp

    async def _post_oauth_token_request(self, url: str, data: Dict[str, str]) -> Dict[str, Any]:
        """Helper for POST requests to OAuth token endpoints."""
        if self.debug:
            logger.debug(f"[GMAuth][POST-OAuthToken] {url} data={data}")

        request_specific_headers = {
            **COMMON_HEADERS,
            **FORM_URLENCODED_HEADER,
            **JSON_HEADER,
        }
        
        # Use the helper method
        resp = await self._make_request(
            'POST', 
            url, 
            data=data, 
            headers=request_specific_headers, 
            cookies=self._cookies
        )
        
        if self.debug:
            logger.debug(f"[GMAuth] OAuth Token Endpoint Response Status ({url}): {resp.status_code}")
        resp.raise_for_status()
        
        # Update cookies from response
        self._update_cookies_from_response(resp)
        
        return resp.json()
    
    def _update_cookies_from_response(self, response: httpx.Response) -> None:
        """Update the cookie jar with cookies from a response."""
        for cookie in response.cookies.jar:
            self._cookies.set(cookie.name, cookie.value, domain=cookie.domain)

    # ------------------------------------------------------------------
    # Steps: credentials, MFA, authorization code
    # ------------------------------------------------------------------

    async def _submit_credentials(self, csrf: str, trans_id: str) -> None:
        url = build_custlogin_url(SELF_ASSERTED_PATH, {
            "tx": trans_id,
            "p": "B2C_1A_SEAMLESS_MOBILE_SignUpOrSignIn"
        })
        
        data = {
            "request_type": "RESPONSE",
            "logonIdentifier": self.config["username"],
            "password": self.config["password"],
        }
        await self._post_request(url, data, csrf)

    async def _handle_mfa(self, csrf: str, trans_id: str) -> Tuple[str, str]:
        # csrf and trans_id are from the step prior to loading the MFA page.
        # Step 1: load MFA page to grab new csrf / transId for OTP submission
        url = build_custlogin_url(COMBINED_SIGNIN_CONFIRMED_PATH, {
            "rememberMe": "true",
            "csrf_token": csrf,
            "tx": trans_id,
            "p": "B2C_1A_SEAMLESS_MOBILE_SignUpOrSignIn"
        })
        
        resp_text = await self._get_request(url)
        
        # These are the new CSRF and TransID to be used for submitting the OTP
        csrf_for_otp = regex_extract(resp_text, r"\"csrf\":\"(.*?)\"")
        trans_id_for_otp = regex_extract(resp_text, r"\"transId\":\"(.*?)\"")
        if not csrf_for_otp or not trans_id_for_otp:
            raise RuntimeError("Failed to extract csrf/transId during MFA GET step for OTP submission")

        if self.debug:
            logger.debug(f"[GMAuth] csrf_for_otp={csrf_for_otp}, trans_id_for_otp={trans_id_for_otp}")

        # Step 2: Generate TOTP code
        try:
            otp = pyotp.TOTP(self.config["totp_key"].strip()).now()
            if self.debug:
                logger.debug(f"[GMAuth] Generated OTP: {otp}")
        except Exception as e:
            raise RuntimeError(f"Failed to generate OTP: {e}") from e

        # Step 3: Submit OTP code
        post_url = build_custlogin_url(SELF_ASSERTED_PATH, {
            "tx": trans_id_for_otp, 
            "p": "B2C_1A_SEAMLESS_MOBILE_SignUpOrSignIn"
        })
        
        post_data = {
            "otpCode": otp,
            "request_type": "RESPONSE",
        }
        await self._post_request(post_url, post_data, csrf_for_otp)

        # Return the CSRF token and TransID that were obtained from the MFA page GET,
        # as these are the ones relevant for the subsequent authorization code retrieval step.
        return csrf_for_otp, trans_id_for_otp

    async def _get_authorization_code(self, csrf: str, trans_id: str) -> Optional[str]:
        """Fetch the final authorization code after successful login/MFA.
        Uses the /api/SelfAsserted/confirmed endpoint pattern observed in working TS code.
        """
        # URL based on TypeScript implementation:
        url = build_custlogin_url(SELF_ASSERTED_CONFIRMED_PATH, {
            "csrf_token": csrf,
            "tx": trans_id,
            "p": "B2C_1A_SEAMLESS_MOBILE_SignUpOrSignIn"
        })

        headers = {**COMMON_HEADERS, **ACCEPT_HTML_HEADER}
        
        # Use the helper method
        resp = await self._make_request(
            'GET', 
            url, 
            headers=headers, 
            cookies=self._cookies, 
            follow_redirects=False
        )
        
        self._update_cookies_from_response(resp)
        
        if self.debug:
            logger.debug(f"[GMAuth] Auth Code GET Response Status: {resp.status_code}")
            logger.debug(f"[GMAuth] Auth Code GET Response Headers: {resp.headers}")
            if resp.status_code != 302:
                logger.debug(f"[GMAuth] Auth Code GET Response Body (first 500):\\n{resp.text[:500]}")

        if resp.status_code != 302:
            if self.debug:
                logger.debug(f"[GMAuth] Unexpected status {resp.status_code} fetching auth code.")
                logger.debug(f"[GMAuth] Response body:\\n{resp.text[:500]}...") # Log first 500 chars
            raise RuntimeError(f"Expected redirect when fetching auth code, got {resp.status_code}")
        
        location = resp.headers.get("Location") or resp.headers.get("location")
        if not location:
            raise RuntimeError("Auth code redirect Location header missing")

        code = regex_extract(location, r"code=(.*?)(&|$)")
        return code

    # ------------------------------------------------------------------
    # MS tokens
    # ------------------------------------------------------------------

    async def _fetch_ms_token(self, code: str, code_verifier: str) -> TokenSet:
        data = {
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": code_verifier,
        }
        token_resp = await self._post_oauth_token_request(self._token_endpoint, data)
        if "access_token" not in token_resp:
            raise RuntimeError("token_endpoint did not return access_token")

        token_set: TokenSet = {
            "access_token": token_resp["access_token"],
            "id_token": token_resp.get("id_token"),
            "refresh_token": token_resp.get("refresh_token"),
            "expires_in": token_resp.get("expires_in"),
        }
        if token_set.get("expires_in"):
            token_set["expires_at"] = int(time.time()) + int(token_set["expires_in"])
        return token_set

    async def _refresh_ms_token(self, refresh_token: str) -> TokenSet:
        data = {
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "refresh_token": refresh_token,
        }
        token_resp = await self._post_oauth_token_request(self._token_endpoint, data)
        if "access_token" not in token_resp:
            raise RuntimeError("Refresh failed – no access_token")
        token_set: TokenSet = {
            "access_token": token_resp["access_token"],
            "id_token": token_resp.get("id_token"),
            "refresh_token": token_resp.get("refresh_token", refresh_token),
            "expires_in": token_resp.get("expires_in"),
        }
        if token_set.get("expires_in"):
            token_set["expires_at"] = int(time.time()) + int(token_set["expires_in"])
        return token_set

    # ------------------------------------------------------------------
    # GM API token exchange
    # ------------------------------------------------------------------

    async def _get_gm_api_token(self, token_set: TokenSet) -> GMAPITokenResponse:
        # Cached & valid?
        if self._current_gm_token and is_token_valid(self._current_gm_token, TOKEN_REFRESH_BUFFER):
            if self.debug:
                logger.debug("[GMAuth] Using cached GM API token")
            return self._current_gm_token

        if self.debug:
            logger.debug("[GMAuth] Requesting GM API token via token exchange…")

        data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token": token_set["access_token"],
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "scope": GM_TOKEN_SCOPE,
            "device_id": self.config["device_id"],
        }
        gm_token: GMAPITokenResponse = await self._post_oauth_token_request(GM_TOKEN_ENDPOINT, data)  # type: ignore[assignment]
        # Add expires_at for convenience
        gm_token["expires_at"] = int(time.time()) + int(gm_token["expires_in"])

        # Sanity check – ensure vehs are present
        decoded: DecodedPayload = jwt.decode(
            gm_token["access_token"],
            options={"verify_signature": False, "verify_aud": False},
        )  # type: ignore[arg-type]
        if not decoded.get("vehs"):
            # Wipe tokens for reauth
            if self.debug:
                logger.debug("[GMAuth] GM token missing vehicle info – forcing re-auth")
            if self._ms_token_path.exists():
                self._ms_token_path.rename(self._ms_token_path.with_suffix(".old"))
            if self._gm_token_path.exists():
                self._gm_token_path.rename(self._gm_token_path.with_suffix(".old"))
            self._current_gm_token = None
            return await self.authenticate()  # recursive call

        self._current_gm_token = gm_token
        # Persist both sets
        await self._save_tokens(token_set)
        return gm_token

    # ------------------------------------------------------------------
    # Token persistence helpers
    # ------------------------------------------------------------------

    async def _save_tokens(self, token_set: TokenSet):
        # MS tokens
        async with aiofiles.open(self._ms_token_path, "w", encoding="utf-8") as fp:
            await fp.write(json.dumps(token_set))
        # GM tokens
        if self._current_gm_token:
            async with aiofiles.open(self._gm_token_path, "w", encoding="utf-8") as fp:
                await fp.write(json.dumps(self._current_gm_token))
        if self.debug:
            logger.debug(f"[GMAuth] Tokens persisted to → {self._ms_token_path.parent}")

    async def _load_current_gm_api_token(self):
        if not self._gm_token_path.exists():
            return
        try:
            async with aiofiles.open(self._gm_token_path, "r", encoding="utf-8") as fp:
                content = await fp.read()
                gm_token: GMAPITokenResponse = json.loads(content)  # type: ignore[arg-type]
            decoded: DecodedPayload = jwt.decode(
                gm_token["access_token"], options={"verify_signature": False, "verify_aud": False}
            )  # type: ignore[arg-type]
            if decoded.get("uid", "").upper() != self.config["username"].upper():
                if self.debug:
                    logger.debug("[GMAuth] Stored GM token belongs to another user – ignoring")
                return
            if is_token_valid(gm_token, TOKEN_REFRESH_BUFFER):
                self._current_gm_token = gm_token
                if self.debug:
                    logger.debug("[GMAuth] Loaded valid GM token from disk")
        except Exception as exc:
            if self.debug:
                logger.debug(f"[GMAuth] Failed to load GM token – {exc}")

    async def _load_ms_token(self) -> TokenSet | bool:
        if not self._ms_token_path.exists():
            return False
        try:
            async with aiofiles.open(self._ms_token_path, "r", encoding="utf-8") as fp:
                content = await fp.read()
                stored: TokenSet = json.loads(content)  # type: ignore[arg-type]
            # Validate expiry & ownership
            decoded = jwt.decode(
                stored["access_token"], options={"verify_signature": False, "verify_aud": False}
            )
            email_or_name = decoded.get("name", "").upper() or decoded.get("email", "").upper()
            if email_or_name != self.config["username"].upper():
                if self.debug:
                    logger.debug("[GMAuth] Cached MS token belongs to different user – ignoring")
                return False
            if is_token_valid(stored, TOKEN_REFRESH_BUFFER):
                return stored
            # else attempt refresh
            if stored.get("refresh_token"):
                if self.debug:
                    logger.debug("[GMAuth] MS access_token expired → attempting refresh…")
                try:
                    refreshed = await self._refresh_ms_token(stored["refresh_token"])
                    await self._save_tokens(refreshed)
                    return refreshed
                except Exception as exc:
                    if self.debug:
                        logger.debug(f"[GMAuth] Failed to refresh MS token – {exc}")
        except Exception as exc:
            if self.debug:
                logger.debug(f"[GMAuth] Error loading MS token: {exc}")
        return False 