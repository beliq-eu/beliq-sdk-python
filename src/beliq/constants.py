"""Defaults, the closed error-code set, and curated public option lists.

The LIVE_* lists are the authority-pinned public subset, intentionally narrower
than what the API can technically accept: provisional formats (fatturapa,
sdi_messaggio, facturae, eslog) are withheld from public option lists per LPD-1.
"""

from __future__ import annotations

DEFAULT_BASE_URL = "https://api.beliq.eu"

# The closed set of error codes beliq returns in the { error: { code } } envelope.
# Mirrored from openapi.json; tests/test_spec_contract.py fails if they drift.
API_ERROR_CODES: tuple[str, ...] = (
    "VALIDATION_ERROR",
    "INVALID_INVOICE",
    "UNSUPPORTED_FORMAT",
    "PROFILE_STANDARD_MISMATCH",
    "DOCUMENT_TYPE_STANDARD_MISMATCH",
    "PARSE_FAILED",
    "INVALID_XML",
    "AUTHENTICATION_REQUIRED",
    "INVALID_API_KEY",
    "QUOTA_EXCEEDED",
    "RATE_LIMITED",
    "ENGINE_UNAVAILABLE",
    "INTERNAL_ERROR",
    "NOT_FOUND",
    "CONVERSION_UNSUPPORTED_PAIR",
    "CONVERSION_LOSSY_FAILCLOSED",
    "CONVERSION_TOOL_UNAVAILABLE",
    "CONVERSION_TOOL_ERROR",
    "PDF_TEMPLATE_AUTH_REQUIRED",
    "PDF_TEMPLATE_NOT_FOUND",
    "PDF_TEMPLATE_INVALID",
)

LIVE_GENERATE_STANDARDS: tuple[str, ...] = ("xrechnung", "zugferd", "facturx", "peppol-bis")
LIVE_PROFILES: tuple[str, ...] = ("basicwl", "en16931", "extended", "extended-ctc-fr")
LIVE_VALIDATE_FORMATS: tuple[str, ...] = ("auto", "cii", "ubl")
LIVE_PARSE_FORMATS: tuple[str, ...] = ("auto", "cii", "ubl")
LIVE_CONVERT_SOURCE_FORMATS: tuple[str, ...] = (
    "auto",
    "cii",
    "ubl",
    "zugferd",
    "facturx",
    "xrechnung",
    "peppol-bis",
)
LIVE_CONVERT_TARGET_FORMATS: tuple[str, ...] = (
    "cii",
    "ubl",
    "zugferd",
    "facturx",
    "xrechnung",
    "peppol-bis",
)
