"""Drift guard: assert the hand-written contracts still match the vendored spec.

The Python SDK does not codegen from the OpenAPI (the spec inlines its schemas,
which yields unusable model names), so this guards the parts that matter: the
closed error-code set, the core validate-response fields, and that our public
option lists are a real subset of what the API accepts.
"""

import json
from pathlib import Path
from typing import get_type_hints

from beliq.constants import (
    API_ERROR_CODES,
    LIVE_CONVERT_TARGET_FORMATS,
    LIVE_GENERATE_PRESETS,
    LIVE_PROFILES_BY_STANDARD,
    LIVE_VALIDATE_FORMATS,
)
from beliq.types import AccountInfo, DocumentAllowanceCharge, LineAllowanceCharge

SPEC = json.loads((Path(__file__).parent.parent / "openapi.json").read_text())


def _enum_values(schema: dict) -> set[str]:
    # The spec models closed string sets as anyOf of single-value enums.
    return {item["enum"][0] for item in schema["anyOf"]}


def _generate_body_props() -> dict:
    return SPEC["paths"]["/v1/generate"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"]


def _generate_invoice_schema() -> dict:
    return _generate_body_props()["invoice"]


def _parse_invoice_schema() -> dict:
    return SPEC["paths"]["/v1/parse"]["post"]["responses"]["200"]["content"]["application/json"]["schema"][
        "properties"
    ]["data"]["properties"]["invoice"]


def _allowance_and_charge_items(level: dict) -> dict:
    """The item schema behind ``allowances`` and ``charges`` on one level."""
    return {key: level["properties"][key]["items"] for key in ("allowances", "charges")}


def _line_schema(invoice: dict) -> dict:
    return invoice["properties"]["lines"]["items"]


# The spec types these two as JSON numbers and strings; mypy accepts an int
# where a float is declared, so `float` is the honest annotation for `number`.
_JSON_TO_PYTHON = {"number": float, "string": str}


def test_error_codes_match_spec():
    code = SPEC["paths"]["/v1/validate"]["post"]["responses"]["400"]["content"]["application/json"]["schema"][
        "properties"
    ]["error"]["properties"]["code"]
    assert _enum_values(code) == set(API_ERROR_CODES)


def test_validate_data_has_core_fields():
    data = SPEC["paths"]["/v1/validate"]["post"]["responses"]["200"]["content"]["application/json"]["schema"][
        "properties"
    ]["data"]["properties"]
    for field in ("valid", "format", "errors", "warnings", "profileDetected", "schematronVersion"):
        assert field in data


def test_live_validate_formats_are_subset_of_spec():
    param = next(
        p for p in SPEC["paths"]["/v1/validate"]["post"]["parameters"] if p["name"] == "format"
    )
    assert set(LIVE_VALIDATE_FORMATS) <= _enum_values(param["schema"])


def test_live_convert_targets_are_subset_of_spec():
    param = next(
        p for p in SPEC["paths"]["/v1/convert"]["post"]["parameters"] if p["name"] == "targetFormat"
    )
    assert set(LIVE_CONVERT_TARGET_FORMATS) <= _enum_values(param["schema"])


def test_validate_data_has_ruleset_seal_fields():
    data = SPEC["paths"]["/v1/validate"]["post"]["responses"]["200"]["content"]["application/json"]["schema"][
        "properties"
    ]["data"]["properties"]
    assert "rulesetSha256" in data
    artifact = data["rulesetArtifacts"]["items"]["properties"]
    assert set(artifact) >= {"key", "version", "fileSha256"}


def test_generate_json_response_has_seal_fields():
    data = SPEC["paths"]["/v1/generate"]["post"]["responses"]["200"]["content"]["application/json"]["schema"][
        "properties"
    ]["data"]["properties"]
    for field in ("output", "sha256", "validationResult", "contentType"):
        assert field in data


def test_generate_presets_are_subset_of_spec():
    props = _generate_body_props()
    standards = _enum_values(props["standard"])
    profiles = _enum_values(props["profile"])
    outputs = _enum_values(props["output"])
    for preset in LIVE_GENERATE_PRESETS:
        assert preset.standard in standards
        assert preset.output in outputs
        if preset.profile is not None:
            assert preset.profile in profiles
        if preset.facturx_profile is not None:
            assert preset.facturx_profile in _enum_values(props["facturxProfile"])



def test_profile_table_offers_only_profiles_the_spec_declares():
    # The spec enum is flat (it carries no per-standard rule), so this catches a
    # typo or a retired profile; the pairing itself is checked against the
    # engine's table by scripts/check_profile_drift.py.
    declared = _enum_values(_generate_body_props()["profile"])
    for standard, profiles in LIVE_PROFILES_BY_STANDARD.items():
        for profile in profiles:
            assert profile in declared, f"{standard} -> {profile}"

def test_account_info_declares_every_field_me_returns():
    """`AccountInfo` is hand-written, so nothing made it follow the API.

    It had fallen three fields behind (`livemode`, `org.rulesetChannel`,
    `quota.resetsAt`) with a green suite, because `extra="allow"` keeps an
    undeclared field on the object while hiding it from every type checker,
    every IDE and every reader of the class. A user cannot reach what the model
    does not name.

    Membership, not equality: the model may legitimately declare a field the
    spec does not require. Top-level keys of `data` only, matching the line the
    Node SDK's gate and the beliq-docs one draw.
    """
    required = SPEC["paths"]["/v1/me"]["get"]["responses"]["200"]["content"]["application/json"]["schema"][
        "properties"
    ]["data"]["required"]
    assert required, "the spec no longer marks any /v1/me field required"

    declared = {field.alias or name for name, field in AccountInfo.model_fields.items()}
    assert set(required) - declared == set()


def _assert_model_matches(model: type, item: dict, label: str) -> None:
    declared = get_type_hints(model)
    assert set(declared) == set(item["properties"]), label
    assert model.__required_keys__ == frozenset(item["required"]), label
    for field, schema in item["properties"].items():
        assert declared[field] is _JSON_TO_PYTHON[schema["type"]], f"{label}.{field}"


def test_allowance_and_charge_models_declare_every_field_the_spec_accepts():
    """The two models are hand-written, so nothing made them follow the API.

    Same defect as `test_account_info_declares_every_field_me_returns`: an
    undeclared field is invisible to mypy, to every IDE and to anyone reading
    the class, so a user cannot reach it. `Invoice` is a bare `dict[str, Any]`,
    which is why these two shapes are declared on their own rather than as
    fields of an invoice model.

    Equality, not membership, and in both directions. The spec sets
    `additionalProperties: false` on both item schemas, so a field this SDK
    declares but the API does not accept is a 400 waiting for the first caller
    who believes the annotation. That is the opposite risk from `/v1/me`, where
    a surplus declaration is harmless.
    """
    invoice = _generate_invoice_schema()
    for key, item in _allowance_and_charge_items(invoice).items():
        _assert_model_matches(DocumentAllowanceCharge, item, f"invoice.{key}")
    for key, item in _allowance_and_charge_items(_line_schema(invoice)).items():
        _assert_model_matches(LineAllowanceCharge, item, f"invoice.lines[].{key}")


def test_line_allowances_carry_no_vat_of_their_own():
    """Why there are two models and not one shared shape.

    A document-level entry states its own VAT and a line-level one inherits the
    line's. Collapsing them would put `vatRate` and `vatCategoryCode` within
    reach on a line, where `additionalProperties: false` means the API rejects
    the request rather than ignoring the key.
    """
    invoice = _generate_invoice_schema()
    document = _allowance_and_charge_items(invoice)["allowances"]["properties"]
    line = _allowance_and_charge_items(_line_schema(invoice))["allowances"]["properties"]
    assert {"vatRate", "vatCategoryCode"} <= set(document)
    assert {"vatRate", "vatCategoryCode"}.isdisjoint(line)


def test_parsed_invoice_allowances_match_the_generated_shape():
    """`parse()` hands back what `generate()` takes, so one pair of models covers both.

    `ParseResult.invoice` is a plain dict, so the models are what a caller
    annotates a parsed allowance with; if the two ends of the API ever diverge,
    that annotation quietly becomes a lie.
    """
    sent = _generate_invoice_schema()
    received = _parse_invoice_schema()
    assert _allowance_and_charge_items(sent) == _allowance_and_charge_items(received)
    assert _allowance_and_charge_items(_line_schema(sent)) == _allowance_and_charge_items(_line_schema(received))
