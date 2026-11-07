"""Defaults, the closed error-code set, and curated public option lists.

Each LIVE_* list carries every value the API accepts for its operation. A list
narrower than the API's own enum states its reason beside it.
``GET /v1/rulesets`` carries each format's badge, which says how deep its check
goes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

DEFAULT_BASE_URL = "https://api.beliq.eu"

# Per-attempt deadline. Sits above the API's own worst case so the server is
# always the one to answer. The former 30s default sat *below* beliq's measured
# p95 for a document request, so the client aborted work the server went on to
# finish, leaving the caller unable to tell whether the document was produced.
DEFAULT_TIMEOUT_SECONDS = 90.0

# Extra attempts after the first for the failures retried by count: a 429 other
# than QUOTA_EXCEEDED, and a 502 or 503 carrying any beliq error code but a 503
# DATABASE_UNAVAILABLE.
DEFAULT_MAX_RETRIES = 3

# How long the client keeps retrying, in seconds from the start of the first
# attempt: 15 minutes. A 503 DATABASE_UNAVAILABLE, a 502 or 503 with no beliq error
# code, and a connection that could not be opened are retried until it is spent.
# No standard sets the value: it is beliq's own, sized to outlast two of the three
# database outages beliq has measured, of about 9 and 12 minutes. The third lasted
# 33 minutes.
DEFAULT_RETRY_BUDGET_SECONDS = 900.0

# The statuses that can be retried. Which of their answers are, and how often,
# is decided per error code in the client.
#
# 504 is excluded on purpose: it means the work may still be running server-side,
# and a retry would run the same document again from the start, likely into the
# same deadline.
RETRYABLE_STATUSES = frozenset({429, 502, 503})

# The one 429 waiting cannot clear. RATE_LIMITED frees up in seconds and
# ACCOUNT_THROTTLED in minutes, but a spent monthly allowance only returns when the
# billing window turns, and beliq's Retry-After states it honestly: the seconds left
# in the window, which can be weeks. Retrying it waits against a refusal that is
# already final, so the caller is told the request hung rather than that the
# allowance is gone.
QUOTA_EXHAUSTED_CODE = "QUOTA_EXCEEDED"

# The API's answer while its database is out; the outage it reports outlasts a few
# quick retries.
DATABASE_UNAVAILABLE_CODE = "DATABASE_UNAVAILABLE"

# Base for exponential backoff when no Retry-After is given.
BACKOFF_BASE_SECONDS = 0.5

# No backoff wait reaches this, however many attempts came before.
BACKOFF_CEILING_SECONDS = 30.0

# Spread added to a server-supplied Retry-After.
RETRY_AFTER_JITTER_SECONDS = 0.25

# The closed set of error codes beliq returns in the { error: { code } } envelope.
# Mirrored from openapi.json; tests/test_spec_contract.py fails if they drift.
API_ERROR_CODES: tuple[str, ...] = (
    "VALIDATION_ERROR",
    "INVALID_INVOICE",
    "PROFILE_STANDARD_MISMATCH",
    "DOCUMENT_TYPE_STANDARD_MISMATCH",
    "PARSE_FAILED",
    "AUTHENTICATION_REQUIRED",
    "INVALID_API_KEY",
    # 403: the credential is valid, but the member behind it holds a role
    # without the capability the route needs. Distinct from INVALID_API_KEY
    # because the remedy is an owner or admin changing a role, not a new key.
    "INSUFFICIENT_ROLE",
    "QUOTA_EXCEEDED",
    "RATE_LIMITED",
    # Distinct from RATE_LIMITED: the burst limiter clears in seconds, this one
    # blocks every /v1 route for minutes, so back off differently.
    "ACCOUNT_THROTTLED",
    "ENGINE_UNAVAILABLE",
    "DATABASE_UNAVAILABLE",
    "INTERNAL_ERROR",
    "NOT_FOUND",
    "CONVERSION_UNSUPPORTED_PAIR",
    "CONVERSION_LOSSY_FAILCLOSED",
    "CONVERSION_TOOL_UNAVAILABLE",
    "CONVERSION_TOOL_ERROR",
    # 422 on convert: the converted document failed validation and is not
    # returned. The verdict is in `details["validationResult"]`.
    "CONVERSION_OUTPUT_INVALID",
    # 422 on generate: veraPDF reported a violation of its PDF/A-3b profile in
    # the hybrid PDF that was built, so the PDF is not returned. The failed
    # rules are in `details["failedRules"]`.
    "PDFA_VIOLATION",
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
    # POST /v1/participants. ENROLLMENT_MODE_UNSUPPORTED (409): the network's
    # authorization model is not self-service yet, so support registers the
    # participant. ENROLLMENT_REFUSED (422): beliq's checks passed and the
    # provider refused anyway, often because the identifier is already
    # registered through another provider.
    "ENROLLMENT_MODE_UNSUPPORTED",
    "ENROLLMENT_REFUSED",
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
    # The France CTC pre-flight on a plateforme-agréée lane, both 422. A PA
    # refuses a document carrying any BR-FR-CTC Flux 2 finding at any severity
    # and its refusal burns the invoice number, so Beliq refuses first.
    # FRANCE_CTC_NOT_JUDGED means no France verdict exists for the document at
    # all, usually a missing BT-23.
    "FRANCE_CTC_BLOCKING_FINDINGS",
    "FRANCE_CTC_NOT_JUDGED",
    # 409: a PA already rejected these exact bytes, and a French invoice number
    # must be reissued under a new one rather than sent again.
    "FRANCE_INVOICE_NUMBER_BURNED",
    "UNSUPPORTED_SYNTAX",
    "MALFORMED_DOCUMENT",
    "EMPTY_DOCUMENT",
    "MISSING_CUSTOMIZATION_ID",
    "MISSING_PROCESS_ID",
)

# Every ``standard`` POST /v1/generate accepts, in the order its enum lists
# them. The four national formats are Schema-checked: their authority publishes
# a schema and no machine-readable business rules, so beliq checks structure and
# says so. GET /v1/rulesets carries each one's badge.
LIVE_GENERATE_STANDARDS: tuple[str, ...] = (
    "xrechnung",
    "zugferd",
    "facturx",
    "peppol-bis",
    "fatturapa",
    "facturae",
    "eslog",
    "ksef",
)


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

# The Factur-X granularity values offered publicly. Kept as the flat list the
# hybrid-PDF family shares; anything choosing a profile for a specific standard
# wants LIVE_PROFILES_BY_STANDARD instead, which is what the API enforces.
LIVE_PROFILES: tuple[str, ...] = ("basicwl", "en16931", "extended", "extended-ctc-fr")

# Which profiles each standard accepts, publicly-offered values only.
#
# ``profile`` is not a free enum: the engine pins it per standard and answers a
# pair outside the table with ``422 PROFILE_STANDARD_MISMATCH``
# (the engine's ALLOWED_PROFILES_FOR_STANDARD table). A
# surface that offers one flat profile list therefore offers values that cannot
# succeed: none of the Factur-X granularity values is legal for ``xrechnung`` or
# ``peppol-bis``, and ``extended-ctc-fr`` is the AFNOR XP Z12-012 France CTC
# overlay with no ZUGFeRD-branded counterpart.
#
# It carries every standard the API accepts. It stays narrower than the
# engine's table in one place: the ``minimum`` and ``basic`` Factur-X profiles
# are engine-supported but not offered here (FNFE-MPE source gating).
#
# Mirrors ``LIVE_PROFILES_BY_STANDARD`` in the Node SDK.
# ``scripts/check_profile_drift.py`` compares it against the engine's table.
LIVE_PROFILES_BY_STANDARD: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "xrechnung": ("xrechnung",),
        "peppol-bis": ("peppol", "romania-ro-cius", "netherlands-nlcius"),
        "zugferd": ("basicwl", "en16931", "extended"),
        "facturx": ("basicwl", "en16931", "extended", "extended-ctc-fr"),
        "fatturapa": ("ordinaria",),
        "facturae": ("ordinaria",),
        "eslog": ("eracun",),
        "ksef": ("fa3",),
    }
)


def profiles_for_standard(standard: str) -> tuple[str, ...]:
    """The profiles a caller may choose for ``standard``; empty for an unknown standard."""
    return LIVE_PROFILES_BY_STANDARD.get(standard, ())


def is_profile_allowed_for_standard(standard: str, profile: str) -> bool:
    """Whether ``profile`` is legal for ``standard``.

    An unknown standard passes: the API is the authority on values this table
    does not carry, and a client-side guess would refuse a request the server
    would have accepted.
    """
    allowed = profiles_for_standard(standard)
    return not allowed or profile in allowed


# The ``format`` values POST /v1/validate accepts that are offered. A named
# syntax makes the API validate the document as that syntax; "auto" reads it
# from the document.
LIVE_VALIDATE_FORMATS: tuple[str, ...] = (
    "auto",
    "cii",
    "ubl",
    "fatturapa",
    "facturae",
    "eslog",
    "poland_ksef_fa3",
)

# The validate ``format`` values left out of LIVE_VALIDATE_FORMATS. "auto" still
# recognises both.
VALIDATE_FORMATS_LEFT_OUT: Mapping[str, str] = MappingProxyType(
    {
        "sdi_messaggio": "An SdI file message, not an invoice. GET /v1/rulesets has no entry for it.",
        "poland_ksef_fa2": (
            "The API answers every FA(2) document `valid: false`, led by a `POLAND_KSEF_FA2_SUPERSEDED` error. "
            "GET /v1/rulesets has no entry for it."
        ),
    }
)

LIVE_PARSE_FORMATS: tuple[str, ...] = ("auto", "cii", "ubl")

_PARSE_READS_CII_AND_UBL = (
    "POST /v1/parse ignores `format` and reads CII and UBL documents only: "
    "the `format` its response states is one of the two."
)

# The parse ``format`` values left out of LIVE_PARSE_FORMATS.
PARSE_FORMATS_LEFT_OUT: Mapping[str, str] = MappingProxyType(
    {
        "fatturapa": _PARSE_READS_CII_AND_UBL,
        "facturae": _PARSE_READS_CII_AND_UBL,
        "eslog": _PARSE_READS_CII_AND_UBL,
        "sdi_messaggio": _PARSE_READS_CII_AND_UBL,
        "poland_ksef_fa2": _PARSE_READS_CII_AND_UBL,
        "poland_ksef_fa3": _PARSE_READS_CII_AND_UBL,
    }
)
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
