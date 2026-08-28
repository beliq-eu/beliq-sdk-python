"""The drift check answers one question: has the vendored spec fallen behind the
deployed API?

Its previous implementation answered a different one, "do the two documents
differ", and nothing here caught that because nothing here existed. These cases
are the contract, stated as behaviour in both directions.

The vendored copy stands in for both sides: a mutated deep copy plays the live
spec, so every case says exactly what changed. Mirrors
``beliq-sdk-node/test/spec-surface.test.mjs``; the two implementations are
expected to report the same paths for the same pair of documents.
"""

from __future__ import annotations

import copy
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from _spec_surface import surface_missing_from  # noqa: E402

VENDORED: dict[str, Any] = json.loads(
    (Path(__file__).resolve().parent.parent / "openapi.json").read_text(encoding="utf-8")
)


def live(mutate: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    clone = copy.deepcopy(VENDORED)
    mutate(clone)
    return clone


def me_data(spec: dict[str, Any]) -> dict[str, Any]:
    return spec["paths"]["/v1/me"]["get"]["responses"]["200"]["content"]["application/json"]["schema"][
        "properties"
    ]["data"]


def format_param(spec: dict[str, Any]) -> dict[str, Any]:
    return next(p for p in spec["paths"]["/v1/validate"]["post"]["parameters"] if p["name"] == "format")


def test_identical_documents_are_silent():
    assert surface_missing_from(copy.deepcopy(VENDORED), VENDORED) == []


# --- surface the vendored copy is missing -----------------------------------


def test_reports_a_new_path():
    def mutate(s):
        s["paths"]["/v1/brandnew"] = {"get": {"responses": {}}}

    assert surface_missing_from(live(mutate), VENDORED) == ["paths./v1/brandnew"]


def test_reports_a_new_operation():
    def mutate(s):
        s["paths"]["/v1/me"]["delete"] = {"responses": {}}

    assert surface_missing_from(live(mutate), VENDORED) == ["paths./v1/me.delete"]


def test_reports_a_new_response_status():
    def mutate(s):
        s["paths"]["/v1/me"]["get"]["responses"]["418"] = {"description": "x"}

    assert surface_missing_from(live(mutate), VENDORED) == ["paths./v1/me.get.responses.418"]


def test_reports_a_new_media_type():
    def mutate(s):
        s["paths"]["/v1/me"]["get"]["responses"]["200"]["content"]["application/xml"] = {
            "schema": {"type": "string"}
        }

    assert surface_missing_from(live(mutate), VENDORED) == [
        "paths./v1/me.get.responses.200.application/xml"
    ]


def test_reports_a_new_response_header():
    def mutate(s):
        res = s["paths"]["/v1/me"]["get"]["responses"]["200"]
        res["headers"] = {**res.get("headers", {}), "x-brand-new": {"schema": {"type": "string"}}}

    assert surface_missing_from(live(mutate), VENDORED) == [
        "paths./v1/me.get.responses.200.headers.x-brand-new"
    ]


def test_reports_a_new_response_property():
    def mutate(s):
        me_data(s)["properties"]["seats"] = {"type": "integer"}

    assert surface_missing_from(live(mutate), VENDORED) == [
        "paths./v1/me.get.responses.200.application/json.data.seats"
    ]


def test_reports_a_new_nested_property():
    def mutate(s):
        me_data(s)["properties"]["quota"]["properties"]["carriedOver"] = {"type": "integer"}

    assert surface_missing_from(live(mutate), VENDORED) == [
        "paths./v1/me.get.responses.200.application/json.data.quota.carriedOver"
    ]


def test_reports_a_new_query_parameter():
    def mutate(s):
        s["paths"]["/v1/validate"]["post"]["parameters"].append(
            {"name": "brandNew", "in": "query", "schema": {"type": "string"}}
        )

    assert surface_missing_from(live(mutate), VENDORED) == [
        "paths./v1/validate.post.parameters.query.brandNew"
    ]


def test_reports_a_newly_accepted_enum_value_arriving_as_a_union_arm():
    # A closed string set is an `anyOf` of single-value enums, so a newly
    # accepted format arrives as a new arm rather than a new `enum` member.
    def mutate(s):
        format_param(s)["schema"]["anyOf"].append({"type": "string", "enum": ["brandnew-format"]})

    assert surface_missing_from(live(mutate), VENDORED) == [
        'paths./v1/validate.post.parameters.format.enum "brandnew-format"'
    ]


# --- divergence that is not "behind" ----------------------------------------


def test_silent_on_a_type_the_vendored_copy_narrowed():
    # The case that turned main red: bq-api#262 narrowed plan.name and reworded
    # a description, and both read as "behind" until this rewrite.
    def mutate(s):
        me_data(s)["properties"]["plan"]["properties"]["name"] = {
            "anyOf": [{"type": "string"}, {"type": "null"}]
        }

    assert surface_missing_from(live(mutate), VENDORED) == []


def test_silent_on_a_reworded_description():
    def mutate(s):
        me_data(s)["properties"]["quota"]["properties"]["resetsAt"]["description"] = "something else"
        s["paths"]["/v1/me"]["get"]["summary"] = "a different summary"

    assert surface_missing_from(live(mutate), VENDORED) == []


def test_silent_on_a_field_added_ahead_of_the_deploy():
    def mutate(s):
        del me_data(s)["properties"]["livemode"]

    assert surface_missing_from(live(mutate), VENDORED) == []


def test_silent_on_a_path_added_ahead_of_the_deploy():
    def mutate(s):
        del s["paths"]["/v1/rulesets"]

    assert surface_missing_from(live(mutate), VENDORED) == []


def test_silent_on_a_version_bump_the_vendored_copy_is_ahead_of():
    # `info.version` is replaced on a bump, not added to, so a vendored copy
    # legitimately ahead of live used to read as behind. It needed a dedicated
    # exclusion under the old value-comparing walk; presence-only needs none,
    # because `info` carries no surface to be present.
    def mutate(s):
        s["info"]["version"] = "0.0.1-ancient"
        s["info"]["description"] = "old"

    assert surface_missing_from(live(mutate), VENDORED) == []


# --- silence must mean "covered", never "did not look" ----------------------


def test_reports_a_union_arm_it_cannot_compare():
    def mutate(s):
        format_param(s)["schema"]["anyOf"].append({"properties": {"nested": {"type": "string"}}})

    missing = surface_missing_from(live(mutate), VENDORED)
    assert len(missing) == 1
    assert "carries structure this check cannot compare" in missing[0]


def test_terminates_on_the_self_referential_schema():
    # InvoiceLine.subLines refs InvoiceLine. A `$ref` is compared by target and
    # not followed, which is what keeps this finite without a visited-set.
    assert surface_missing_from(copy.deepcopy(VENDORED), VENDORED) == []

    def mutate(s):
        s["components"]["schemas"]["InvoiceLine"]["properties"]["subLines"]["items"]["$ref"] = (
            "#/components/schemas/Other"
        )

    assert surface_missing_from(live(mutate), VENDORED) == [
        "components.schemas.InvoiceLine.subLines[].$ref -> #/components/schemas/Other"
    ]
