"""Live smoke test against the real beliq API.

Each call consumes one quota unit, so it is opt-in: set BELIQ_API_KEY (and
optionally BELIQ_BASE_URL) to run it, otherwise the module is skipped.
"""

import os

import pytest

from beliq import Beliq

pytestmark = pytest.mark.skipif(
    not os.environ.get("BELIQ_API_KEY"), reason="set BELIQ_API_KEY to run the live test"
)

INVOICE = {
    "number": "IT-2026-001",
    "issueDate": "2026-01-15",
    "dueDate": "2026-02-14",
    "currencyCode": "EUR",
    "buyerReference": "LEITWEG-01",
    "seller": {
        "name": "Seller GmbH",
        "vatId": "DE123456789",
        "address": {"street": "Hauptstrasse 1", "city": "Berlin", "postalCode": "10115", "countryCode": "DE"},
    },
    "buyer": {
        "name": "Buyer GmbH",
        "vatId": "DE987654321",
        "address": {"street": "Marktplatz 2", "city": "Munich", "postalCode": "80331", "countryCode": "DE"},
    },
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
    "taxSummary": [{"vatCategoryCode": "S", "vatRate": 19, "taxableAmount": 1000, "taxAmount": 190}],
    "totalNetAmount": 1000,
    "totalTaxAmount": 190,
    "totalGrossAmount": 1190,
}


def test_live_roundtrip():
    with Beliq(os.environ["BELIQ_API_KEY"], base_url=os.environ.get("BELIQ_BASE_URL", "https://api.beliq.eu")) as beliq:
        account = beliq.me()
        assert account.org.id

        generated = beliq.generate(standard="xrechnung", verify=True, invoice=INVOICE)
        assert "xml" in generated.content_type
        assert generated.meta.schematron_version
        assert generated.xml and generated.xml.lstrip().startswith("<")

        validation = beliq.validate(generated.xml, format="auto")
        assert isinstance(validation.valid, bool)
        assert validation.format

        parsed = beliq.parse(generated.xml, format="auto")
        assert parsed.format

        converted = beliq.convert(generated.xml, source_format="auto", target_format="ubl")
        assert converted.meta.target_format == "ubl"
        assert len(converted.content) > 0
