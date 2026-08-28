"""Does the vendored spec still cover everything the live API exposes?

Presence, never values. The question this answers is whether the vendored copy
has fallen BEHIND the deployed API, so it reports only surface the live spec has
and the vendored one lacks: a path, an operation, a parameter, a response, a
media type, a response header, a property, an enum value. A vendored copy that
is AHEAD of live, which is every moment between merging a spec change and
deploying it, yields nothing.

The previous implementation compared the documents value by value, so a narrowed
type (``plan.name`` going ``str | None`` to ``str``) and a reworded description
both counted as "behind". It honoured the directional contract only for pure
additions, and it turned ``main`` red in this repo and in beliq-sdk-node the
moment a merged-but-undeployed change landed, which is precisely the case the
check exists to tolerate. ``info`` had already been excluded wholesale for the
same reason, one field at a time instead of at the mechanism.

A changed type or a reworded description is a divergence rather than missing
surface, and divergence from beliq-api's own copy is what
``tests/test_spec_vendoring.py`` asserts.

Kept in step with ``beliq-sdk-node/scripts/lib/spec-surface.mjs``; the two are
expected to report the same paths for the same pair of documents.
"""

from __future__ import annotations

import json
from typing import Any


def _enum_values(schema: Any, into: set[str] | None = None) -> set[str]:
    """Every enum value a schema can produce, including through union arms.

    beliq-api models a closed string set as an ``anyOf`` of single-value enums,
    so a newly accepted format or standard reaches a client as a new arm rather
    than a new member of one ``enum``. Flattening both sides to a value set
    catches that addition, while a narrowing (dropping a ``null`` arm) is a
    subset and stays quiet.
    """
    values = set() if into is None else into
    if not isinstance(schema, dict):
        return values
    for value in schema.get("enum") or []:
        values.add(json.dumps(value, sort_keys=True))
    for arm in schema.get("anyOf") or []:
        _enum_values(arm, values)
    return values


def _unhandled_arms(schema: dict[str, Any], path: str, missing: list[str]) -> None:
    """Report a union arm carrying structure of its own rather than skipping it.

    Arm-to-arm matching is deliberately not attempted: every arm in the spec
    today is a single-value enum or a bare ``{"type": ...}``, so ``_enum_values``
    is complete. If that changes, the check would silently stop covering the new
    shape. Going quietly blind is the failure this rewrite exists to remove.
    """
    for i, arm in enumerate(schema.get("anyOf") or []):
        if isinstance(arm, dict) and ("properties" in arm or "$ref" in arm or "items" in arm):
            missing.append(f"{path}.anyOf[{i}] carries structure this check cannot compare")


def _compare_schema(live: Any, vend: Any, path: str, missing: list[str]) -> None:
    """Presence-only schema comparison.

    A ``$ref`` is compared by target and not followed. That keeps the walk finite
    over the spec's one self-referential schema (``InvoiceLine.subLines``)
    without a visited-set, and the referenced schemas are still walked once each
    through ``components.schemas``.
    """
    if not isinstance(live, dict):
        return
    if not isinstance(vend, dict):
        missing.append(path)
        return

    if "$ref" in live:
        if vend.get("$ref") != live["$ref"]:
            missing.append(f"{path}.$ref -> {live['$ref']}")
        return

    _unhandled_arms(live, path, missing)

    vend_enums = _enum_values(vend)
    for value in sorted(_enum_values(live) - vend_enums):
        missing.append(f"{path}.enum {value}")

    for name, sub in (live.get("properties") or {}).items():
        _compare_schema(sub, (vend.get("properties") or {}).get(name), f"{path}.{name}", missing)

    if live.get("items"):
        _compare_schema(live["items"], vend.get("items"), f"{path}[]", missing)

    if isinstance(live.get("additionalProperties"), dict):
        _compare_schema(
            live["additionalProperties"], vend.get("additionalProperties"), f"{path}{{*}}", missing
        )


def _compare_content(live: Any, vend: Any, path: str, missing: list[str]) -> None:
    for media_type, body in (live or {}).items():
        vend_body = (vend or {}).get(media_type)
        if not vend_body:
            missing.append(f"{path}.{media_type}")
            continue
        _compare_schema(body.get("schema"), vend_body.get("schema"), f"{path}.{media_type}", missing)


def _compare_operation(live: dict[str, Any], vend: dict[str, Any], path: str, missing: list[str]) -> None:
    for param in live.get("parameters") or []:
        match = next(
            (
                p
                for p in (vend.get("parameters") or [])
                if p.get("name") == param.get("name") and p.get("in") == param.get("in")
            ),
            None,
        )
        if match is None:
            missing.append(f"{path}.parameters.{param.get('in')}.{param.get('name')}")
        else:
            _compare_schema(
                param.get("schema"), match.get("schema"), f"{path}.parameters.{param.get('name')}", missing
            )

    if live.get("requestBody"):
        if not vend.get("requestBody"):
            missing.append(f"{path}.requestBody")
        else:
            _compare_content(
                live["requestBody"].get("content"),
                vend["requestBody"].get("content"),
                f"{path}.requestBody",
                missing,
            )

    for status, response in (live.get("responses") or {}).items():
        vend_response = (vend.get("responses") or {}).get(status)
        if not vend_response:
            missing.append(f"{path}.responses.{status}")
            continue
        _compare_content(
            response.get("content"), vend_response.get("content"), f"{path}.responses.{status}", missing
        )
        for header in (response.get("headers") or {}).keys():
            if header not in (vend_response.get("headers") or {}):
                missing.append(f"{path}.responses.{status}.headers.{header}")


def surface_missing_from(live: dict[str, Any], vend: dict[str, Any]) -> list[str]:
    """Surface the live spec exposes that the vendored copy does not."""
    missing: list[str] = []

    for route, item in (live.get("paths") or {}).items():
        vend_item = (vend.get("paths") or {}).get(route)
        if not vend_item:
            missing.append(f"paths.{route}")
            continue
        for method, operation in item.items():
            vend_operation = vend_item.get(method)
            if not vend_operation:
                missing.append(f"paths.{route}.{method}")
                continue
            _compare_operation(operation, vend_operation, f"paths.{route}.{method}", missing)

    live_components = live.get("components") or {}
    vend_components = vend.get("components") or {}

    for name, schema in (live_components.get("schemas") or {}).items():
        _compare_schema(
            schema,
            (vend_components.get("schemas") or {}).get(name),
            f"components.schemas.{name}",
            missing,
        )

    for name in (live_components.get("securitySchemes") or {}).keys():
        if name not in (vend_components.get("securitySchemes") or {}):
            missing.append(f"components.securitySchemes.{name}")

    return missing
