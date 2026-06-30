"""Pure, dependency-free helpers shared by the client and request builder."""

from __future__ import annotations

from typing import Any

DocumentInput = str | bytes | bytearray

_POLLUTION_KEYS = {"__proto__", "constructor", "prototype"}


def merge_deep(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge ``source`` into ``target`` (source wins). Lists and scalars overwrite."""
    out = dict(target)
    for key, value in source.items():
        if key in _POLLUTION_KEYS:
            continue
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge_deep(out[key], value)
        else:
            out[key] = value
    return out


def compact_query(query: dict[str, Any]) -> dict[str, Any]:
    """Drop None/empty entries so optional params are omitted, not sent blank."""
    return {k: v for k, v in query.items() if v is not None and v != ""}


def to_bytes(document: DocumentInput) -> bytes:
    if isinstance(document, str):
        return document.encode("utf-8")
    if isinstance(document, (bytes, bytearray)):
        return bytes(document)
    raise TypeError("beliq: document must be a str, bytes, or bytearray")


def sniff_content_type(data: bytes) -> str:
    """Sniff application/pdf vs application/xml from the leading bytes."""
    return "application/pdf" if data[:5] == b"%PDF-" else "application/xml"
