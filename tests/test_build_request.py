from beliq._build_request import (
    build_convert,
    build_generate,
    build_me,
    build_parse,
    build_validate,
)
from beliq._internal import merge_deep, sniff_content_type


def test_me():
    r = build_me()
    assert r.method == "GET"
    assert r.path == "/v1/me"
    assert r.output_kind == "json"


def test_generate_basic():
    r = build_generate(standard="xrechnung", invoice={"number": "INV-1"}, verify=True)
    assert r.method == "POST"
    assert r.path == "/v1/generate"
    assert r.content_type == "application/json"
    assert r.output_kind == "binary"
    assert r.json_body == {
        "standard": "xrechnung",
        "output": "xml",
        "invoice": {"number": "INV-1"},
        "verify": True,
    }


def test_generate_output_defaults_to_xml():
    assert build_generate(standard="xrechnung", invoice={}).json_body["output"] == "xml"


def test_facturx_profile_for_family_only():
    body = build_generate(standard="zugferd", output="pdf", invoice={}, facturx_profile="en16931").json_body
    assert body["facturxProfile"] == "en16931"
    other = build_generate(standard="xrechnung", invoice={}, facturx_profile="en16931").json_body
    assert "facturxProfile" not in other


def test_generate_extra_fields():
    body = build_generate(
        standard="xrechnung", invoice={}, profile="en16931", template="standard", pdf_template_id="tpl-9"
    ).json_body
    assert body["profile"] == "en16931"
    assert body["template"] == "standard"
    assert body["pdfTemplateId"] == "tpl-9"


def test_generate_advanced_merge():
    r = build_generate(
        standard="xrechnung",
        invoice={"number": "INV-1"},
        advanced={"pdfTemplateId": "tpl-1", "invoice": {"note": "x"}},
    )
    assert r.json_body["pdfTemplateId"] == "tpl-1"
    assert r.json_body["invoice"] == {"number": "INV-1", "note": "x"}


def test_validate():
    r = build_validate(raw_body=b"<x/>", content_type="application/pdf", format="auto", france_ctc=True)
    assert r.path == "/v1/validate"
    assert r.output_kind == "json"
    assert r.content_type == "application/pdf"
    assert r.query == {"format": "auto", "franceCtc": True}


def test_validate_omits_france_ctc():
    assert build_validate(raw_body=b"<x/>", content_type="application/xml", format="cii").query == {"format": "cii"}


def test_validate_advanced_query():
    r = build_validate(raw_body=b"<x/>", content_type="application/xml", format="auto", advanced={"strict": True})
    assert r.query == {"format": "auto", "strict": True}


def test_parse():
    r = build_parse(raw_body=b"<x/>", content_type="application/xml", format="ubl")
    assert r.path == "/v1/parse"
    assert r.query == {"format": "ubl"}
    assert r.output_kind == "json"


def test_convert():
    r = build_convert(raw_body=b"<x/>", content_type="application/xml", target_format="ubl", source_format="auto")
    assert r.path == "/v1/convert"
    assert r.output_kind == "binary"
    assert r.query == {"sourceFormat": "auto", "targetFormat": "ubl"}


def test_convert_target_profile_for_family_only():
    fam = build_convert(
        raw_body=b"<x/>",
        content_type="application/xml",
        target_format="zugferd",
        source_format="auto",
        target_profile="en16931",
    )
    assert fam.query["targetProfile"] == "en16931"
    other = build_convert(
        raw_body=b"<x/>",
        content_type="application/xml",
        target_format="ubl",
        source_format="auto",
        target_profile="en16931",
    )
    assert "targetProfile" not in other.query


def test_convert_drop_overlay():
    r = build_convert(
        raw_body=b"<x/>",
        content_type="application/xml",
        target_format="ubl",
        source_format="cii",
        drop_france_ctc_overlay=True,
    )
    assert r.query["dropFranceCtcOverlay"] is True


def test_sniff_content_type():
    assert sniff_content_type(b"%PDF-1.7") == "application/pdf"
    assert sniff_content_type(b"<?xml version='1.0'?>") == "application/xml"


def test_merge_deep_nested():
    assert merge_deep({"a": {"x": 1}, "b": 2}, {"a": {"y": 2}}) == {"a": {"x": 1, "y": 2}, "b": 2}


def test_merge_deep_overwrites_scalars_and_lists():
    assert merge_deep({"a": 1, "list": [1, 2]}, {"a": 9, "list": [3]}) == {"a": 9, "list": [3]}


def test_merge_deep_skips_pollution_keys():
    malicious = {"__proto__": {"polluted": "yes"}, "constructor": {"x": 1}, "safe": "kept"}
    merged = merge_deep({"existing": 1}, malicious)
    assert merged == {"existing": 1, "safe": "kept"}
    assert "__proto__" not in merged
    assert "constructor" not in merged
