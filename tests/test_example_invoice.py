"""examples/invoice.json is the shape the README quickstart shows and the live
smoke generates from, so it has to be a document the API actually accepts.

`verify` defaults to true, and an invoice that satisfies plain EN 16931 still
fails the XRechnung CIUS on rules no generic example carries. This shape was
proven live on all four standards beliq offers (2026-09-06); the assertions
below name the rule each field answers, so a future edit that drops one fails
here instead of on the PyPI project page.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVOICE = json.loads((ROOT / "examples" / "invoice.json").read_text())
README = (ROOT / "README.md").read_text()


def test_seller_contact_group_bg6():
    """BR-DE-2."""
    assert INVOICE["seller"]["contactName"]
    assert INVOICE["seller"]["phone"]


def test_payment_instructions_bg16():
    """BR-DE-1."""
    assert INVOICE["paymentMeans"]["typeCode"]


def test_vat_breakdown_bg23_matches_every_line():
    """BR-CO-18, BR-S-01."""
    breakdown = INVOICE["taxSummary"]
    assert breakdown
    for line in INVOICE["lines"]:
        assert any(
            t["vatCategoryCode"] == line["vatCategoryCode"] and t["vatRate"] == line["vatRate"]
            for t in breakdown
        )


def test_both_parties_carry_a_peppol_electronic_address():
    """BT-34, BT-49.

    `email` resolves as EAS `EM` on xrechnung but not on peppol-bis, where a
    mailbox is not an SML-resolvable participant. An explicit endpoint is the
    one rung every standard accepts.
    """
    for party in ("seller", "buyer"):
        assert INVOICE[party]["peppol"]["schemeId"]
        assert INVOICE[party]["peppol"]["id"]


def test_buyer_reference():
    """BR-DE-15."""
    assert INVOICE["buyerReference"]


def test_totals_match_the_lines():
    """BR-CO-13, BR-CO-15."""
    net = sum(line["lineTotal"] for line in INVOICE["lines"])
    tax = sum(t["taxAmount"] for t in INVOICE["taxSummary"])
    assert INVOICE["totalNetAmount"] == net
    assert INVOICE["totalTaxAmount"] == tax
    assert INVOICE["totalGrossAmount"] == net + tax


def test_readme_quickstart_shows_the_required_fields():
    """PyPI renders this README as the project page, so its invoice is the first
    thing most people copy. It is written out rather than imported, so nothing
    but this test keeps it in step with the fixture above.
    """
    quickstart = README[README.index("## Quick start") : README.index("## Authentication")]
    for field in ("buyerReference", "contactName", "phone", "taxSummary", "paymentMeans", "peppol"):
        assert field in quickstart
