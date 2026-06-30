import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from beliq import AsyncBeliq, Beliq, BeliqApiError

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def minimal_invoice() -> dict[str, Any]:
    return {
        "number": "IT-2026-001",
        "issueDate": "2026-01-15",
        "currencyCode": "EUR",
        "seller": {"name": "Seller GmbH", "address": {"city": "Berlin", "postalCode": "10115", "countryCode": "DE"}},
        "buyer": {"name": "Buyer GmbH", "address": {"city": "Munich", "postalCode": "80331", "countryCode": "DE"}},
        "lines": [
            {
                "description": "Consulting",
                "quantity": 10,
                "unitCode": "HUR",
                "unitPrice": 100,
                "lineTotal": 1000,
                "vatRate": 19,
                "vatCategoryCode": "S",
            }
        ],
        "totalNetAmount": 1000,
        "totalTaxAmount": 190,
        "totalGrossAmount": 1190,
    }


def test_requires_api_key():
    with pytest.raises(ValueError):
        Beliq("")


@respx.mock
def test_me_request_and_parse():
    route = respx.get("https://api.beliq.eu/v1/me").mock(return_value=httpx.Response(200, text=fixture("me.json")))
    with Beliq("blq_test") as beliq:
        acct = beliq.me()
    req = route.calls.last.request
    assert req.method == "GET"
    assert req.headers["x-api-key"] == "blq_test"
    assert "authorization" not in req.headers
    assert acct.org.name == "Acme GmbH"
    assert acct.quota.remaining == 9863


@respx.mock
def test_custom_base_url_strips_slash():
    route = respx.get("https://staging.beliq.eu/v1/me").mock(return_value=httpx.Response(200, text=fixture("me.json")))
    with Beliq("blq_test", base_url="https://staging.beliq.eu/") as beliq:
        beliq.me()
    assert str(route.calls.last.request.url) == "https://staging.beliq.eu/v1/me"


@respx.mock
def test_validate_request_and_parse():
    route = respx.post("https://api.beliq.eu/v1/validate").mock(
        return_value=httpx.Response(200, text=fixture("validate-invalid.json"))
    )
    with Beliq("blq_test") as beliq:
        result = beliq.validate("<rsm:CrossIndustryInvoice/>", format="cii")
    req = route.calls.last.request
    assert req.method == "POST"
    assert str(req.url) == "https://api.beliq.eu/v1/validate?format=cii"
    assert req.headers["content-type"] == "application/xml"
    assert req.headers["x-api-key"] == "blq_test"
    assert req.content == b"<rsm:CrossIndustryInvoice/>"
    assert result.valid is False
    assert result.errors[0].rule_id == "BR-DE-15"
    assert result.errors[0].severity == "error"
    assert result.schematron_version == "1.3.16"


@respx.mock
def test_bearer_auth_and_bool_query():
    route = respx.post("https://api.beliq.eu/v1/validate").mock(
        return_value=httpx.Response(200, text=fixture("validate-invalid.json"))
    )
    with Beliq("blq_test", auth="bearer") as beliq:
        beliq.validate("<x/>", format="auto", france_ctc=True)
    req = route.calls.last.request
    assert req.headers["authorization"] == "Bearer blq_test"
    assert "x-api-key" not in req.headers
    assert str(req.url) == "https://api.beliq.eu/v1/validate?format=auto&franceCtc=true"


@respx.mock
def test_sniffs_pdf_content_type():
    route = respx.post("https://api.beliq.eu/v1/validate").mock(
        return_value=httpx.Response(200, text=fixture("validate-invalid.json"))
    )
    with Beliq("blq_test") as beliq:
        beliq.validate(b"%PDF-1.7")
    assert route.calls.last.request.headers["content-type"] == "application/pdf"


@respx.mock
def test_parse():
    respx.post("https://api.beliq.eu/v1/parse").mock(return_value=httpx.Response(200, text=fixture("parse.json")))
    with Beliq("blq_test") as beliq:
        result = beliq.parse("<x/>", format="auto")
    assert result.format == "cii"
    assert result.invoice["number"] == "IT-2026-001"


@respx.mock
def test_generate_xml_with_header_metadata():
    route = respx.post("https://api.beliq.eu/v1/generate").mock(
        return_value=httpx.Response(
            200,
            text="<?xml version='1.0'?><rsm:CrossIndustryInvoice/>",
            headers={"content-type": "application/xml", "x-schematron-version": "1.3.16", "x-output-envelope": "cii"},
        )
    )
    with Beliq("blq_test") as beliq:
        result = beliq.generate(standard="xrechnung", invoice=minimal_invoice(), verify=True)
    req = route.calls.last.request
    assert req.headers["content-type"].startswith("application/json")
    sent = json.loads(req.content)
    assert sent["standard"] == "xrechnung"
    assert sent["output"] == "xml"
    assert sent["verify"] is True
    assert sent["invoice"]["number"] == "IT-2026-001"
    assert result.content_type.startswith("application/xml")
    assert result.xml is not None and result.xml.startswith("<?xml")
    assert result.meta.schematron_version == "1.3.16"
    assert result.meta.output_envelope == "cii"


@respx.mock
def test_generate_pdf_returns_bytes():
    respx.post("https://api.beliq.eu/v1/generate").mock(
        return_value=httpx.Response(
            200, content=b"%PDF-1.7\nbinary", headers={"content-type": "application/pdf", "x-pdf-kind": "PDF/A-3B"}
        )
    )
    with Beliq("blq_test") as beliq:
        result = beliq.generate(standard="zugferd", output="pdf", facturx_profile="en16931", invoice=minimal_invoice())
    assert result.xml is None
    assert result.content.startswith(b"%PDF-")
    assert result.meta.pdf_kind == "PDF/A-3B"


@respx.mock
def test_convert_maps_metadata_headers():
    route = respx.post("https://api.beliq.eu/v1/convert").mock(
        return_value=httpx.Response(
            200,
            content=b"<Invoice/>",
            headers={
                "content-type": "application/xml",
                "x-source-format": "cii",
                "x-target-format": "ubl",
                "x-profile-detected": "en16931",
                "x-lost-elements-count": "2",
                "x-lost-elements": '["BT-22","BT-23"]',
                "x-conversion-tools": "beliq-engine@1.0",
            },
        )
    )
    with Beliq("blq_test") as beliq:
        result = beliq.convert("<rsm:CrossIndustryInvoice/>", target_format="ubl", source_format="auto")
    req = route.calls.last.request
    assert str(req.url) == "https://api.beliq.eu/v1/convert?sourceFormat=auto&targetFormat=ubl"
    assert req.headers["content-type"] == "application/xml"
    assert result.meta.target_format == "ubl"
    assert result.meta.lost_elements_count == 2
    assert result.meta.lost_elements == ["BT-22", "BT-23"]
    assert result.meta.conversion_tools == "beliq-engine@1.0"
    assert result.content == b"<Invoice/>"


@respx.mock
def test_raises_typed_error_on_4xx():
    respx.post("https://api.beliq.eu/v1/validate").mock(
        return_value=httpx.Response(400, text=fixture("error-invalid-xml.json"))
    )
    with Beliq("blq_test") as beliq, pytest.raises(BeliqApiError) as ei:
        beliq.validate("not xml")
    assert ei.value.code == "INVALID_XML"
    assert ei.value.status == 400
    assert "not well-formed" in ei.value.message
    assert ei.value.details == {"line": 1}


@respx.mock
def test_parses_error_envelope_on_binary_endpoint():
    respx.post("https://api.beliq.eu/v1/convert").mock(
        return_value=httpx.Response(422, text=fixture("error-invalid-xml.json"))
    )
    with Beliq("blq_test") as beliq, pytest.raises(BeliqApiError) as ei:
        beliq.convert("<x/>", target_format="ubl")
    assert ei.value.code == "INVALID_XML"
    assert ei.value.status == 422


@respx.mock
def test_async_client_validate():
    respx.post("https://api.beliq.eu/v1/validate").mock(
        return_value=httpx.Response(200, text=fixture("validate-invalid.json"))
    )

    async def go():
        async with AsyncBeliq("blq_test") as beliq:
            return await beliq.validate("<x/>", format="auto")

    result = asyncio.run(go())
    assert result.valid is False
    assert result.errors[0].rule_id == "BR-DE-15"
