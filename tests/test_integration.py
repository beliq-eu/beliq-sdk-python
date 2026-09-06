"""Live smoke test against the real beliq API.

Each call consumes one quota unit, so it is opt-in: set BELIQ_API_KEY (and
optionally BELIQ_BASE_URL) to run it, otherwise the module is skipped.
"""

import hashlib
import json
import os
from pathlib import Path

import pytest

from beliq import Beliq

pytestmark = pytest.mark.skipif(
    not os.environ.get("BELIQ_API_KEY"), reason="set BELIQ_API_KEY to run the live test"
)

INVOICE = json.loads((Path(__file__).resolve().parents[1] / "examples" / "invoice.json").read_text())


def test_live_roundtrip():
    with Beliq(os.environ["BELIQ_API_KEY"], base_url=os.environ.get("BELIQ_BASE_URL", "https://api.beliq.eu")) as beliq:
        account = beliq.me()
        assert account.org.id

        generated = beliq.generate(standard="xrechnung", verify=True, invoice=INVOICE)
        assert "xml" in generated.content_type
        assert generated.meta.schematron_version
        assert generated.xml and generated.xml.lstrip().startswith("<")

        sealed = beliq.generate(standard="xrechnung", verify=True, invoice=INVOICE, seal=True)
        assert sealed.sha256 and hashlib.sha256(sealed.content).hexdigest() == sealed.sha256
        assert sealed.validation_result is not None and sealed.validation_result.valid is True
        assert sealed.meta.livemode == beliq.livemode

        validation = beliq.validate(generated.xml, format="auto")
        assert isinstance(validation.valid, bool)
        assert validation.format

        parsed = beliq.parse(generated.xml, format="auto")
        assert parsed.format

        converted = beliq.convert(generated.xml, source_format="auto", target_format="ubl")
        assert converted.meta.target_format == "ubl"
        assert len(converted.content) > 0
