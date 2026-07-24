"""Defaults, the closed error-code set, and curated public option lists.

The LIVE_* lists are the authority-pinned public subset, intentionally narrower
than what the API can technically accept: provisional formats (fatturapa,
sdi_messaggio, facturae, eslog) are withheld from public option lists per LPD-1.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    "TRANSMISSION_DISABLED",
    "IDEMPOTENCY_KEY_REUSED",
    "INVALID_IDEMPOTENCY_KEY",
    "INBOX_UNKNOWN_PROVIDER",
    "INBOX_VERIFICATION_FAILED",
)

LIVE_GENERATE_STANDARDS: tuple[str, ...] = ("xrechnung", "zugferd", "facturx", "peppol-bis")


@dataclass(frozen=True)
class GeneratePreset:
    """A named generate target: the API ``standard`` plus the ``profile`` /
    ``facturx_profile`` / ``output`` it needs."""

    id: str
    label: str
    standard: str
    output: str
    # API ``profile``; None lets the engine pick the standard's default.
    profile: str | None = None
    # API ``facturx_profile``; Factur-X / ZUGFeRD only.
    facturx_profile: str | None = None


# Named generate targets surfaced to end users (connector dropdowns), mirroring
# the public set on beliq.eu's own generator. NLCIUS is a Peppol BIS profile,
# not a standalone standard, so it is reachable here rather than through
# LIVE_GENERATE_STANDARDS or the Factur-X-only LIVE_PROFILES.
LIVE_GENERATE_PRESETS: tuple[GeneratePreset, ...] = (
    GeneratePreset(id="xrechnung", label="XRechnung", standard="xrechnung", output="xml"),
    GeneratePreset(id="factur-x", label="Factur-X", standard="facturx", output="pdf", facturx_profile="en16931"),
    GeneratePreset(id="zugferd", label="ZUGFeRD", standard="zugferd", output="pdf"),
    GeneratePreset(id="peppol-bis", label="Peppol BIS 3.0", standard="peppol-bis", output="xml"),
    GeneratePreset(id="nlcius", label="NLCIUS", standard="peppol-bis", output="xml", profile="netherlands-nlcius"),
)

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
