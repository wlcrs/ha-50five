"""Shared helpers to censor sensitive values in debug logs and diagnostics."""

from __future__ import annotations

from typing import Any

# Keys (normalized: lowercased, underscores stripped) whose string values are
# masked, keeping the first/last 2 chars so distinct values remain
# distinguishable without exposing them fully.
MASKED_KEYS = {
    "email",
    "username",
    "id",
    "getcustomerbyidid",
    "getchargestationbyidid",
    "chargestationid",
    "customerid",
    "commid",
    "channelid",
    "evseid",
    "externalid",
    "internalid",
    "contractid",
    "card",
    "cardid",
    "transactioncustomerid",
    "tariffid",
    "channelvisibleid",
    "deviceid",
}
# Keys whose values are fully redacted since partial exposure has no diagnostic value.
REDACTED_KEYS = {
    "password",
    "accesstoken",
    "token",
    "authorization",
    "address",
    "city",
    "postalcode",
    "zipcode",
}


def _normalize_key(key: str) -> str:
    """Normalize a dict key for lookup, tolerating camelCase and snake_case."""
    return key.lower().replace("_", "")


def mask_value(value: str) -> str:
    """Mask a sensitive string, keeping first/last 2 chars so values stay distinguishable."""
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


def censor(data: Any) -> Any:
    """Recursively censor sensitive values in query variables/responses for safe logging."""
    if isinstance(data, dict):
        censored: dict[str, Any] = {}
        for key, value in data.items():
            key_norm = _normalize_key(str(key))
            if key_norm in REDACTED_KEYS:
                censored[key] = "<redacted>"
            elif key_norm in MASKED_KEYS and isinstance(value, str):
                censored[key] = mask_value(value)
            else:
                censored[key] = censor(value)
        return censored
    if isinstance(data, list):
        return [censor(item) for item in data]
    return data
