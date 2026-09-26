"""Official beliq SDK for Python.

Generate, validate, parse, and convert EN 16931 e-invoices against
authority-pinned, drift-checked rules. beliq produces and checks the compliant
document; transmission, archiving, and tax-authority reporting stay with your
access point.
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
    Org,
    ParseResult,
    Plan,
    Quota,
    RulesetArtifact,
    ValidationIssue,
    ValidationResult,
)

__version__ = "0.3.4"

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
    "Org",
    "ParseResult",
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
