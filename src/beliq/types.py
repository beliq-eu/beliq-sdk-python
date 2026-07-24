"""Public result types.

JSON responses are lenient Pydantic models (extra fields, like the per-country
authority versions, are preserved via ``extra='allow'`` so a new field never
breaks parsing). Binary responses (generate/convert) are dataclasses carrying
the document bytes plus the response-header metadata the spec does not model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

# An EN 16931 invoice for generate(): a plain mapping matching the documented
# shape (see the OpenAPI spec / README). The API validates it server-side.
Invoice = dict[str, Any]


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="allow")


class Org(_Model):
    id: str
    name: str


class Plan(_Model):
    id: int | None = None
    name: str | None = None


class Quota(_Model):
    limit: int
    used: int
    remaining: int


class AccountInfo(_Model):
    key_id: str | None = None
    key_prefix: str | None = None
    org: Org
    plan: Plan
    rate_limit_per_minute: int
    quota: Quota


class ValidationIssue(_Model):
    rule_id: str
    severity: str
    location: str | None = None
    message: str


class RulesetArtifact(_Model):
    """One row of the ruleset fingerprint behind a validation result."""

    key: str
    version: str
    file_sha256: str


class ValidationResult(_Model):
    valid: bool
    format: str
    profile_detected: str | None = None
    schematron_version: str | None = None
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    # The combined ruleset fingerprint the document was checked against, and the
    # per-artifact rows behind it (the "check it yourself" seal).
    ruleset_sha256: str | None = None
    ruleset_artifacts: list[RulesetArtifact] | None = None


class ParseResult(_Model):
    format: str
    profile_detected: str | None = None
    invoice: dict[str, Any] = Field(default_factory=dict)


@dataclass
class GenerateMeta:
    schematron_version: str | None = None
    pdf_kind: str | None = None
    output_envelope: str | None = None
    # Combined ruleset fingerprint the document was checked against, and its rows.
    ruleset_sha256: str | None = None
    ruleset_artifacts: list[RulesetArtifact] | None = None
    # True for a live key, False for a blq_test_ sandbox key.
    livemode: bool | None = None


@dataclass
class GenerateResult:
    content_type: str
    content: bytes
    meta: GenerateMeta
    xml: str | None = None
    # SHA-256 of the returned bytes; present only when seal was requested.
    sha256: str | None = None
    # Validation verdict for the document; present only when seal was requested.
    validation_result: ValidationResult | None = None


@dataclass
class ConvertMeta:
    source_format: str | None = None
    target_format: str | None = None
    profile_detected: str | None = None
    lost_elements_count: int | None = None
    lost_elements: list[str] | None = None
    conversion_tools: str | None = None
    # True for a live key, False for a blq_test_ sandbox key.
    livemode: bool | None = None


@dataclass
class ConvertResult:
    content_type: str
    content: bytes
    meta: ConvertMeta
