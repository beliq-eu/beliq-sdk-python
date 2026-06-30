"""Error type and envelope parsing for beliq responses."""

from __future__ import annotations

import json
from typing import Any


class BeliqApiError(Exception):
    """Raised for any non-2xx beliq response (and a 2xx body with success=false).

    Carries the typed error ``code``, HTTP ``status``, and any structured
    ``details`` from beliq's ``{ "success": false, "error": {...} }`` envelope.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.details = details

    def __str__(self) -> str:
        return f"{self.message} ({self.code})" if self.code else self.message


def parse_envelope(body: bytes) -> dict[str, Any] | None:
    """Parse a beliq JSON envelope from raw response bytes; None if not JSON."""
    if not body.strip():
        return None
    try:
        parsed = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def error_from_response(status: int, body: bytes) -> BeliqApiError:
    envelope = parse_envelope(body) or {}
    raw_err = envelope.get("error")
    err: dict[str, Any] = raw_err if isinstance(raw_err, dict) else {}
    message = err.get("message") or envelope.get("message") or f"beliq request failed with status {status}"
    return BeliqApiError(message, code=err.get("code"), status=status, details=err.get("details"))
