"""Official beliq SDK for Python.

beliq is the platform for European e-invoicing: one API to generate, validate,
convert and parse e-invoices, with the rule pack, version and check depth on
its verdicts. beliq produces and checks the document; transmission, archiving,
and tax-authority reporting stay with your access point.
"""

from __future__ import annotations

from .client import AsyncBeliq, Beliq
from .constants import (
    API_ERROR_CODES,
    DEFAULT_BASE_URL,
    LIVE_CONVERT_SOURCE_FORMATS,
    LIVE_CONVERT_TARGET_FORMATS,
    LIVE_GENERATE_PRESETS,
    LIVE_GENERATE_STANDARDS,
    LIVE_PARSE_FORMATS,
    LIVE_PROFILES,
    LIVE_PROFILES_BY_STANDARD,
    LIVE_VALIDATE_FORMATS,
    GeneratePreset,
    is_profile_allowed_for_standard,
    profiles_for_standard,
)
from .errors import BeliqApiError
from .types import (
    AccountInfo,
    ConvertMeta,
    ConvertResult,
    DocumentAllowanceCharge,
    GenerateMeta,
    GenerateResult,
    Invoice,
    LineAllowanceCharge,
    LostElement,
    LostElementsTruncated,
    Org,
    ParseElementCount,
    ParseResult,
    ParseWarning,
    PdfInput,
    Plan,
    Quota,
    RulesetArtifact,
    ValidationIssue,
    ValidationResult,
)

__version__ = "0.7.1"

__all__ = [
    "AsyncBeliq",
    "Beliq",
    "BeliqApiError",
    "AccountInfo",
    "ConvertMeta",
    "ConvertResult",
    "DocumentAllowanceCharge",
    "GenerateMeta",
    "GeneratePreset",
    "GenerateResult",
    "Invoice",
    "LineAllowanceCharge",
    "LostElement",
    "LostElementsTruncated",
    "Org",
    "ParseElementCount",
    "ParseResult",
    "ParseWarning",
    "PdfInput",
    "Plan",
    "Quota",
    "RulesetArtifact",
    "ValidationIssue",
    "ValidationResult",
    "API_ERROR_CODES",
    "DEFAULT_BASE_URL",
    "LIVE_CONVERT_SOURCE_FORMATS",
    "LIVE_CONVERT_TARGET_FORMATS",
    "LIVE_GENERATE_PRESETS",
    "LIVE_GENERATE_STANDARDS",
    "LIVE_PARSE_FORMATS",
    "LIVE_PROFILES",
    "LIVE_PROFILES_BY_STANDARD",
    "LIVE_VALIDATE_FORMATS",
    "is_profile_allowed_for_standard",
    "profiles_for_standard",
]
