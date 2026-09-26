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
        # The XRechnung CIUS asks for more than plain EN 16931: a seller contact
        # (BR-DE-2), payment instructions (BR-DE-1), a VAT breakdown (BR-CO-18)
        # and an electronic address per party. examples/invoice.json is this
        # same shape.
        "buyerReference": "04011000-12345-06",
        "seller": {
            "name": "Seller GmbH",
            "vatId": "DE123456789",
            "contactName": "Anna Muster",
            "email": "billing@seller.example",
            "phone": "+49 30 1234567",
            "address": {"street": "Hauptstr. 1", "city": "Berlin", "postalCode": "10115", "countryCode": "DE"},
            "peppol": {"schemeId": "9930", "id": "DE123456789"},
        },
        "buyer": {
            "name": "Buyer GmbH",
            "vatId": "DE987654321",
            "email": "ap@buyer.example",
            "address": {"street": "Marktweg 2", "city": "Munich", "postalCode": "80331", "countryCode": "DE"},
            "peppol": {"schemeId": "9930", "id": "DE987654321"},
        },
        "lines": [
            {"description": "Consulting", "quantity": 10, "unitCode": "HUR", "unitPrice": 100, "lineTotal": 1000, "vatRate": 19, "vatCategoryCode": "S"}
        ],
        "taxSummary": [{"vatCategoryCode": "S", "vatRate": 19, "taxableAmount": 1000, "taxAmount": 190}],
        "paymentMeans": {"typeCode": "58", "iban": "DE89370400440532013000"},
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

## Timeouts and retries

The client retries transient failures for you, so you do not have to reimplement
backoff around it.

```python
Beliq(
    api_key="blq_...",
    timeout=90.0,     # per-attempt deadline in seconds (default)
    max_retries=3,    # extra attempts after the first (default)
)
```

Only `429`, `502` and `503` are retried, honouring the server's `Retry-After`
with jitter. beliq refunds the document's quota unit on a `503`, so a retry never
costs you a second document.

`504` and a client-side timeout are deliberately **not** retried: both mean the
work may still be running on beliq's side, so retrying risks producing a second
document rather than recovering the first.

A `429` carrying `QUOTA_EXCEEDED` is not retried either. `RATE_LIMITED` and
`ACCOUNT_THROTTLED` clear on their own, but a spent monthly allowance only returns
when your billing window turns, so the error is raised straight away and names the
cause instead of sleeping against it.

The default deadline is generous because beliq runs the full Schematron rule set
over each document, and a generate or validate can legitimately take tens of
seconds. If you lower it, keep it above the latency you actually see: a deadline
shorter than the server's own turns completed work into an unknown outcome. Pass
`max_retries=0` to handle retrying yourself. If you supply your own
`httpx.Client`, its timeout is used as-is and `timeout` is ignored.

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

`document` accepts a `str`, `bytes`, or `bytearray`. The content type is sniffed from the bytes (PDF vs XML) unless you pass `content_type=`. `generate` and `convert` return the raw document `content` (bytes) plus the response-header metadata: `meta.schematron_version`, `meta.pdf_kind`, `meta.source_format`/`meta.target_format`, `meta.lost_elements`, `meta.conversion_tools`, the ruleset fingerprint `meta.ruleset_sha256` / `meta.ruleset_artifacts`, and `meta.livemode`. For an XML output, `generate` also decodes `xml`.

JSON responses are Pydantic models. Any field not explicitly typed (such as the per-country authority versions on a validation result) is preserved and accessible. Errors raise `BeliqApiError` with a typed `.code`, HTTP `.status`, and any `.details`:

```python
from beliq import BeliqApiError

try:
    beliq.validate("not xml")
except BeliqApiError as err:
    print(err.code, err.status, err.message)
```

## Method options

Keyword arguments the examples on this page do not show. `Beliq` and `AsyncBeliq` take the same ones, and an argument left out (or `None`) is not sent.

`generate`:

- `template="standard"` renders the built-in invoice layout for `output="pdf"`. It is the only value. `xrechnung` and `peppol-bis` have no hybrid PDF, so they need it (or `pdf_template_id`) to return a PDF at all: a visualization PDF with no embedded XML (`meta.pdf_kind == "visualization"`), while the legal document stays the XML. `zugferd` and `facturx` render that same layout onto their hybrid PDF with or without it.
- `pdf_template_id="k3d-9mp"` renders the PDF from one of your organization's own templates, designed in the dashboard. The value is the short ref shown next to the template there. It takes precedence over `template` and applies to any `output="pdf"`. An unknown ref raises `BeliqApiError` with code `PDF_TEMPLATE_NOT_FOUND`.

`validate`:

- `france_ctc=True` also runs the FNFE-MPE BR-FR-CTC Flux 2 rules of the French e-invoicing reform on a CII or UBL document. They run without it when the document's BT-24 is the EXTENDED-CTC-FR CustomizationID or its BT-23 carries a French *cadre de facturation* code, so `france_ctc=False` does not switch them off.

`convert`:

- `target_profile` picks the profile when `target_format` is `"zugferd"` or `"facturx"`, one of `LIVE_PROFILES` (`"basicwl"`, `"en16931"`, `"extended"`, `"extended-ctc-fr"`). The API uses `"en16931"` when it is left out. For any other `target_format` the SDK does not send it.
- `drop_france_ctc_overlay=True` lets a CII source that carries a French *cadre de facturation* code (BT-23) convert to a UBL target (`"ubl"`, `"xrechnung"`, `"peppol-bis"`). UBL has no place for that code, so by default the API refuses with `CONVERSION_LOSSY_FAILCLOSED` (422). With this set, the code is dropped and counted in `meta.lost_elements_count`.

`generate`, `validate`, `parse` and `convert`:

- `advanced` is a dict deep-merged over what the SDK sends, and its values win over the named arguments: into the JSON body on `generate`, into the query string on the other three. It is there for a field the API accepts before this SDK has an argument for it.

## Allowances and charges

A discount or surcharge sits either on the invoice or on a single line, and the two shapes differ: a document-level entry states its own VAT, a line-level one inherits the line's. The API rejects an unknown key rather than ignoring it, so the two are not interchangeable.

```python
from beliq import DocumentAllowanceCharge, LineAllowanceCharge

document_discount: DocumentAllowanceCharge = {
    "amount": 25,
    "vatCategoryCode": "S",  # required at document level
    "vatRate": 19,
    "reason": "Volume discount",
    "reasonCode": "95",  # UNTDID 5189
}
line_surcharge: LineAllowanceCharge = {"amount": 12.5, "reason": "Express handling"}

invoice = {
    # number, dates, parties and totals as in the quick start
    "lines": [
        {
            "description": "Consulting", "quantity": 10, "unitCode": "HUR",
            "unitPrice": 100, "lineTotal": 1000, "vatRate": 19, "vatCategoryCode": "S",
            "charges": [line_surcharge],
        },
    ],
    "allowances": [document_discount],
}
```

The invoice itself stays a plain dict, so these two are annotations you opt into; they exist so a type checker and an IDE can see the fields. `tests/test_spec_contract.py` pins both shapes to the vendored `openapi.json`, including which fields are required.

## The seal: verify it yourself

Pass `seal=True` to `generate` to get the document back as a JSON envelope: the decoded `content` (bytes) plus its `sha256` and the full `validation_result`. Hashing the returned bytes reproduces the returned hash, so you can prove which ruleset the document passed.

```python
import hashlib

sealed = beliq.generate(standard="xrechnung", verify=True, invoice=invoice, seal=True)
assert hashlib.sha256(sealed.content).hexdigest() == sealed.sha256
print(sealed.validation_result.valid, sealed.meta.ruleset_sha256)
```

Without `seal`, `generate` returns the raw document body (unchanged, the default). The ruleset fingerprint (`meta.ruleset_sha256`, `meta.ruleset_artifacts`) is present in both modes.

## Sandbox and live keys

A `blq_test_` key is a sandbox key; a `blq_live_` key is live. The client derives the mode from the key prefix before any request:

```python
beliq = Beliq(api_key="blq_test_...")
beliq.livemode  # False for a sandbox key, True for a live key
```

Each `generate` / `convert` response also carries the authoritative mode from the server as `meta.livemode`.

## Generate presets

`LIVE_GENERATE_PRESETS` is the curated set of public generate targets (matching beliq.eu's own generator). NLCIUS is a Peppol BIS profile rather than a standalone standard, so it is reachable here:

```python
from beliq import LIVE_GENERATE_PRESETS

nlcius = next(p for p in LIVE_GENERATE_PRESETS if p.id == "nlcius")
beliq.generate(standard=nlcius.standard, profile=nlcius.profile, output=nlcius.output, invoice=invoice)
```

## Which profiles a standard accepts

`profile` is pinned per standard, and the API answers a pair outside its table with `422 PROFILE_STANDARD_MISMATCH`. `LIVE_PROFILES` is one flat list for the Factur-X family, so offering it for every standard offers values that cannot succeed: none of them is legal on XRechnung or Peppol BIS, and `extended-ctc-fr` is Factur-X only. Build a per-standard choice from `profiles_for_standard` instead:

```python
from beliq import is_profile_allowed_for_standard, profiles_for_standard

profiles_for_standard("zugferd")                               # ('basicwl', 'en16931', 'extended')
is_profile_allowed_for_standard("zugferd", "extended-ctc-fr")  # False
```

An unknown standard returns `()` and is allowed, so the API stays the authority on values this table does not carry.

## Development

```bash
uv sync --locked --extra dev             # installs exactly what uv.lock pins
uv run ruff check src tests
bash scripts/scrub-check.sh              # no em-dash in any tracked file
uv run mypy
uv run pytest                            # unit tests (no network)
BELIQ_API_KEY=blq_xxx uv run pytest tests/test_integration.py   # hits the live API; draws quota
```

`uv.lock` pins the development and CI tree, not what `pip install beliq` resolves for users. It records the package's own version too, so a change to `pyproject.toml` (a dependency or the version) needs `uv lock` in the same commit. CI installs with `--locked` and fails on a stale lock.

`tests/test_spec_contract.py` reads the vendored `openapi.json` and fails if the error-code set, the core validate/seal fields, or the public option lists drift from the spec. Refresh the vendored spec with `python scripts/sync_spec.py`. A weekly workflow (`scripts/check_live_drift.py`) flags when the vendored spec falls behind the deployed API. `python scripts/check_profile_drift.py` checks `LIVE_PROFILES_BY_STANDARD` against the engine's own table; it needs a `beliq-engine` checkout beside this repo (or `BELIQ_ENGINE_PATH`) and fails without one, so it is run by hand, not in CI.

## Publishing

Released to PyPI as [`beliq`](https://pypi.org/project/beliq/). Releases run from `.github/workflows/release.yml` via PyPI Trusted Publishing (OIDC, with attestations): bump `version` in `pyproject.toml` and `__version__` in `src/beliq/__init__.py`, run `uv lock`, add the release's entry to [`CHANGELOG.md`](CHANGELOG.md), merge, then push a `v*.*.*` tag on the merge commit to publish. No token is stored in the repo.

## License

MIT
