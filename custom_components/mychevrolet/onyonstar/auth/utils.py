"""Utility functions for the OnStar authentication process."""

import base64
import time
from typing import Dict, Optional, Any
import re


def urlsafe_b64encode(data: bytes) -> str:
    """Return base64url-encoded string **without** padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def is_token_valid(token: Dict[str, Any], buffer_seconds: int = 300) -> bool:
    """Check if a token is valid with a time buffer."""
    return token.get("expires_at", 0) > int(time.time()) + buffer_seconds


def regex_extract(text: str, pattern: str) -> Optional[str]:
    """Extract text using regex pattern."""
    match = re.search(pattern, text)
    return match.group(1) if match else None


def build_custlogin_url(path: str, params: Optional[Dict[str, str]] = None) -> str:
    """Build a URL for the custlogin.gm.com domain with optional query parameters."""
    base_url = f"https://custlogin.gm.com/gmb2cprod.onmicrosoft.com/{path}"
    if not params:
        return base_url
    
    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{base_url}?{query_string}" 