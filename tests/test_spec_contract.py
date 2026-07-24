"""Drift guard: assert the hand-written contracts still match the vendored spec.

The Python SDK does not codegen from the OpenAPI (the spec inlines its schemas,
which yields unusable model names), so this guards the parts that matter: the
closed error-code set, the core validate-response fields, and that our public
option lists are a real subset of what the API accepts.
"""

import json
from pathlib import Path

from beliq.constants import (
    API_ERROR_CODES,
    LIVE_CONVERT_TARGET_FORMATS,
    LIVE_GENERATE_PRESETS,
    LIVE_VALIDATE_FORMATS,
)

SPEC = json.loads((Path(__file__).parent.parent / "openapi.json").read_text())


def _enum_values(schema: dict) -> set[str]:
    # The spec models closed string sets as anyOf of single-value enums.
    return {item["enum"][0] for item in schema["anyOf"]}


def _generate_body_props() -> dict:
    return SPEC["paths"]["/v1/generate"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"]


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
