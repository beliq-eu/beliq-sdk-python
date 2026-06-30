# beliq

Official Python SDK for the [beliq](https://beliq.eu) e-invoicing compliance API. Generate, validate, parse, and convert EN 16931 invoices (XRechnung, ZUGFeRD, Factur-X, Peppol BIS) against authority-pinned, nightly-drift-checked rules.

beliq produces and checks the compliant document. Transmission (Peppol, PDP, KSeF, SDI), archiving, and tax-authority reporting stay with your access point.

## Install

```bash
pip install beliq
```

Requires Python >= 3.10.

## Quick start

```python
from beliq import Beliq

beliq = Beliq(api_key="blq_...")

# Account, plan, and quota context (no quota cost).
account = beliq.me()

# Generate an XRechnung document from an EN 16931 invoice.
generated = beliq.generate(
    standard="xrechnung",
    verify=True,
    invoice={
        "number": "INV-2026-001",
        "issueDate": "2026-01-15",
        "currencyCode": "EUR",
        "seller": {"name": "Seller GmbH", "address": {"city": "Berlin", "postalCode": "10115", "countryCode": "DE"}},
        "buyer": {"name": "Buyer GmbH", "address": {"city": "Munich", "postalCode": "80331", "countryCode": "DE"}},
        "lines": [
            {"description": "Consulting", "quantity": 10, "unitCode": "HUR", "unitPrice": 100, "lineTotal": 1000, "vatRate": 19, "vatCategoryCode": "S"}
        ],
        "totalNetAmount": 1000,
        "totalTaxAmount": 190,
        "totalGrossAmount": 1190,
    },
)
print(generated.xml, generated.meta.schematron_version)

# Validate any document against authority-pinned rules.
result = beliq.validate(generated.xml, format="auto")
if not result.valid:
    for issue in result.errors:
        print(issue.rule_id, issue.message)
```

## Authentication

Create an API key in the beliq dashboard under API Keys:

```python
Beliq(api_key="blq_...")                    # sends X-API-Key (default)
Beliq(api_key="blq_...", auth="bearer")      # sends Authorization: Bearer
Beliq(api_key="blq_...", base_url="https://staging.beliq.eu")
```

## Async

`AsyncBeliq` mirrors the sync client with `await`:

```python
import asyncio
from beliq import AsyncBeliq

async def main():
    async with AsyncBeliq(api_key="blq_...") as beliq:
        result = await beliq.validate(open("invoice.xml", "rb").read(), format="auto")
        print(result.valid)

asyncio.run(main())
```

## API

| Method | Endpoint | Input | Returns |
|---|---|---|---|
| `me()` | GET /v1/me | none | `AccountInfo` (no quota cost) |
| `generate(...)` | POST /v1/generate | EN 16931 invoice dict | `GenerateResult` |
| `validate(document, ...)` | POST /v1/validate | XML or PDF | `ValidationResult` |
| `parse(document, ...)` | POST /v1/parse | XML or PDF | `ParseResult` |
| `convert(document, ...)` | POST /v1/convert | XML or PDF | `ConvertResult` |

`document` accepts a `str`, `bytes`, or `bytearray`. The content type is sniffed from the bytes (PDF vs XML) unless you pass `content_type=`. `generate` and `convert` return the raw document `content` (bytes) plus the response-header metadata (`schematron_version`, `pdf_kind`, `source_format`/`target_format`, `lost_elements`, `conversion_tools`); for an XML output, `generate` also decodes `xml`.

JSON responses are Pydantic models. Any field not explicitly typed (such as the per-country authority versions on a validation result) is preserved and accessible. Errors raise `BeliqApiError` with a typed `.code`, HTTP `.status`, and any `.details`:

```python
from beliq import BeliqApiError

try:
    beliq.validate("not xml")
except BeliqApiError as err:
    print(err.code, err.status, err.message)
```

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
ruff check src tests
mypy
pytest                                   # unit tests (no network)
BELIQ_API_KEY=blq_xxx pytest tests/test_integration.py   # hits the live API; draws quota
```

`tests/test_spec_contract.py` reads the vendored `openapi.json` and fails if the error-code set or the core validate fields drift from the spec. Refresh the vendored spec with `python scripts/sync_spec.py`.

## Publishing

Released to PyPI as [`beliq`](https://pypi.org/project/beliq/). Releases run from `.github/workflows/release.yml` via PyPI Trusted Publishing (OIDC, with attestations): push a `v*.*.*` tag to publish. No token is stored in the repo.

## License

MIT
