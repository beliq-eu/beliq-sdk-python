"""Pure request builder: maps operation params to a normalized descriptor.

The five operations are heterogeneous:
    me        GET,  no body,        JSON envelope out
    generate  POST, JSON body,      document bytes out (xml or pdf)
    validate  POST, raw bytes body, JSON envelope out
    parse     POST, raw bytes body, JSON envelope out
    convert   POST, raw bytes body, document bytes out
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ._internal import compact_query, merge_deep

# 'json' => parse the { success, data } envelope; 'binary' => return raw bytes.
OutputKind = str


@dataclass
class BuiltRequest:
    method: str
    path: str
    output_kind: OutputKind
    query: dict[str, Any] = field(default_factory=dict)
    json_body: dict[str, Any] | None = None
    raw_body: bytes | None = None
    content_type: str | None = None


def _is_facturx_family(value: str | None) -> bool:
    return value in ("facturx", "zugferd")


def _with_advanced(query: dict[str, Any], advanced: dict[str, Any] | None) -> dict[str, Any]:
    base = compact_query(query)
    return merge_deep(base, advanced) if advanced else base


def build_me() -> BuiltRequest:
    return BuiltRequest(method="GET", path="/v1/me", output_kind="json")


def build_generate(
    *,
    standard: str,
    invoice: dict[str, Any],
    output: str = "xml",
    profile: str | None = None,
    facturx_profile: str | None = None,
    verify: bool | None = None,
    template: str | None = None,
    pdf_template_id: str | None = None,
    advanced: dict[str, Any] | None = None,
) -> BuiltRequest:
    body: dict[str, Any] = {"standard": standard, "output": output, "invoice": invoice}
    if profile:
        body["profile"] = profile
    if facturx_profile and _is_facturx_family(standard):
        body["facturxProfile"] = facturx_profile
    if verify is not None:
        body["verify"] = verify
    if template:
        body["template"] = template
    if pdf_template_id:
        body["pdfTemplateId"] = pdf_template_id
    if advanced:
        body = merge_deep(body, advanced)
    return BuiltRequest(
        method="POST",
        path="/v1/generate",
        json_body=body,
        content_type="application/json",
        output_kind="binary",
    )


def build_validate(
    *,
    raw_body: bytes,
    content_type: str,
    format: str | None = None,
    france_ctc: bool | None = None,
    advanced: dict[str, Any] | None = None,
) -> BuiltRequest:
    query: dict[str, Any] = {"format": format}
    if france_ctc is not None:
        query["franceCtc"] = france_ctc
    return BuiltRequest(
        method="POST",
        path="/v1/validate",
        query=_with_advanced(query, advanced),
        raw_body=raw_body,
        content_type=content_type,
        output_kind="json",
    )


def build_parse(
    *,
    raw_body: bytes,
    content_type: str,
    format: str | None = None,
    advanced: dict[str, Any] | None = None,
) -> BuiltRequest:
    return BuiltRequest(
        method="POST",
        path="/v1/parse",
        query=_with_advanced({"format": format}, advanced),
        raw_body=raw_body,
        content_type=content_type,
        output_kind="json",
    )


def build_convert(
    *,
    raw_body: bytes,
    content_type: str,
    target_format: str,
    source_format: str | None = None,
    target_profile: str | None = None,
    drop_france_ctc_overlay: bool | None = None,
    advanced: dict[str, Any] | None = None,
) -> BuiltRequest:
    query: dict[str, Any] = {"sourceFormat": source_format, "targetFormat": target_format}
    if target_profile and _is_facturx_family(target_format):
        query["targetProfile"] = target_profile
    if drop_france_ctc_overlay is not None:
        query["dropFranceCtcOverlay"] = drop_france_ctc_overlay
    return BuiltRequest(
        method="POST",
        path="/v1/convert",
        query=_with_advanced(query, advanced),
        raw_body=raw_body,
        content_type=content_type,
        output_kind="binary",
    )
