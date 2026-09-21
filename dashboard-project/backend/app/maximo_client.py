"""Live Ford Maximo asset API client, used for the "Maximo_Budget" count on
Team Wise. Credentials are optional — see backend/.env.example — and when
unset, callers fall back to an uploaded maximo_budget table instead."""

import os
import time
import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

# The 6-digit VCI (vehicle control identifier / department) codes this API
# recognizes, used as the "all VCIs" set when no VCI filter is selected.
VCI_OPTIONS = (
    "018309", "018092", "018434", "018118", "018253", "018276", "018312",
    "018117", "025411", "018285", "018114", "018342", "040223",
)

_REQUIRED_ENV_VARS = ("TOKEN_URL", "CLIENT_ID", "CLIENT_SECRET", "SCOPE", "API_URL")

_access_token: str | None = None
_access_token_expires_at = 0.0


def is_configured() -> bool:
    return all(os.getenv(name) for name in _REQUIRED_ENV_VARS)


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _get_access_token() -> str:
    global _access_token, _access_token_expires_at

    if _access_token and time.monotonic() < _access_token_expires_at:
        return _access_token

    response = requests.post(
        _require_env("TOKEN_URL"),
        data={
            "grant_type": "client_credentials",
            "client_id": _require_env("CLIENT_ID"),
            "client_secret": _require_env("CLIENT_SECRET"),
            "scope": _require_env("SCOPE"),
        },
        timeout=(5, 20),  # (connect, read) — fail fast when unreachable off-VPN
    )
    response.raise_for_status()

    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise RuntimeError("Token response did not contain access_token")

    expires_in = int(payload.get("expires_in", 300))
    _access_token = token
    _access_token_expires_at = time.monotonic() + max(expires_in - 30, 1)
    return token


def _oslc_value(value: str) -> str:
    return '"' + value.replace('"', '\\"') + '"'


def get_assets(vci: list[str], status: str = "LIVE") -> list[dict[str, Any]]:
    """Fetches live Maximo asset records for the given VCI(s) and status."""
    api_url = _require_env("API_URL")
    locations = ",".join(_oslc_value(v) for v in vci)

    response = requests.get(
        api_url,
        headers={
            "Authorization": f"Bearer {_get_access_token()}",
            "Accept": "application/json",
        },
        params={
            "oslc.select": "assetnum,siteid,status,location",
            "oslc.where": (
                f'siteid="FORDNA" and status="{status}" and location in [{locations}]'
            ),
            "oslc.paging": "true",
            "oslc.pageSize": "1000",
            "lean": "1",
        },
        timeout=(5, 20),  # (connect, read) — fail fast when unreachable off-VPN
    )
    response.raise_for_status()

    data = response.json()
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("member", "rdfs:member", "items", "records", "data"):
            records = data.get(key)
            if isinstance(records, list):
                return records
    return []
