from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"
_SECRET_KEYS = {
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "access_token",
    "refresh_token",
}
_PATTERNS = [
    re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"(?i)(password\s*[=:]\s*)[^\s,;]+"),
]


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: (REDACTED if _is_secret_key(k) else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact(v) for v in value)
    if isinstance(value, str):
        text = value
        for pattern in _PATTERNS:
            text = pattern.sub(lambda m: m.group(1) + REDACTED, text)
        return text
    return value


def _is_secret_key(key: object) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return (
        normalized in _SECRET_KEYS
        or normalized.endswith("_token")
        or normalized.endswith("_secret")
    )
