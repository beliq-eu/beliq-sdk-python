"""Defaults, the closed error-code set, and curated public option lists.

The LIVE_* lists are the authority-pinned public subset, intentionally narrower
than what the API can technically accept: provisional formats (fatturapa,
sdi_messaggio, facturae, eslog) are withheld from public option lists per LPD-1.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_BASE_URL = "https://api.beliq.eu"

# Per-attempt deadline. Sits above the API's own worst case so the server is
# always the one to answer. The former 30s default sat *below* beliq's measured
# p95 for a document request, so the client aborted work the server went on to
# finish, leaving the caller unable to tell whether the document was produced.
DEFAULT_TIMEOUT_SECONDS = 90.0

# Extra attempts after the first, for 429 / 502 / 503 only.
DEFAULT_MAX_RETRIES = 3

# Statuses worth another attempt. All three arrive with Retry-After, and beliq
# refunds the document's quota unit on a 503, so a retry costs nothing.
#
# 504 is excluded on purpose: it means the work may still be running server-side,
# so retrying risks producing a second document rather than recovering one.
RETRYABLE_STATUSES = frozenset({429, 502, 503})

# Ceiling on a server-supplied Retry-After, so one header cannot hang a call.
MAX_RETRY_AFTER_SECONDS = 30.0

# Base for exponential backoff when no Retry-After is given.
BACKOFF_BASE_SECONDS = 0.5

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
    # Distinct from RATE_LIMITED: the burst limiter clears in seconds, this one
    # blocks every /v1 route for minutes, so back off differently.
    "ACCOUNT_THROTTLED",
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
    "TRANSMISSION_NO_PROVIDER",
    "IDEMPOTENCY_KEY_REUSED",
    "INVALID_IDEMPOTENCY_KEY",
    "SENDER_NOT_REGISTERED",
    "CONTENT_ALREADY_SENT",
    "INBOX_UNKNOWN_PROVIDER",
    "INBOX_VERIFICATION_FAILED",
    "INBOX_SIGNATURE_EXPIRED",
    # Peppol routing derivation at emit. A document travels inside an envelope
    # the receiving Access Point routes on, and these are the ways one cannot be
    # built: the recipient has no canonical Peppol form, the sending
    # participant's registration records no country, the document names a
    # different party than the envelope would carry, or the document itself
    # withholds a value the envelope needs.
    "RECIPIENT_NOT_ROUTABLE",
    "SENDER_COUNTRY_MISSING",
    "DOCUMENT_PARTY_MISMATCH",
    # Not a routing failure but a regulatory one: a French sender to a French
    # recipient is a domestic flow under the French B2B reform and must go
    # through a plateforme agréée rather than over Peppol.
    "FRENCH_DOMESTIC_FLOW",
    "UNSUPPORTED_SYNTAX",
    "MALFORMED_DOCUMENT",
    "EMPTY_DOCUMENT",
    "MISSING_CUSTOMIZATION_ID",
    "MISSING_PROCESS_ID",
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
