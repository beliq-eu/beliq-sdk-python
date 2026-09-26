# Changelog

`beliq` is on a 0.x line. Releases are cut from `main` by pushing a `v*.*.*`
tag, and the release workflow refuses a tag whose version disagrees with
`pyproject.toml`.

This SDK types `Invoice` as `dict[str, Any]`, so a new invoice field the API
accepts needs no SDK release to be usable. A spec sync listed below moves the
vendored `openapi.json`, which is what the contract tests and the drift check
read; it does not gate the caller.

## 0.3.4 - unreleased

- The README says that a timeout or a failed connection raises httpx's own
  exception, a subclass of `httpx.TransportError`, not `BeliqApiError`, and is
  not retried, and shows catching both. It had said every error raises
  `BeliqApiError`. The behaviour is unchanged, and a test now pins it for a
  connection error as the existing one did for a timeout.

## 0.3.3 - 2026-09-26

- The PyPI metadata names the supported Python versions, 3.10 to 3.14, and
  `Typing :: Typed`, since the wheel ships `py.typed`. CI tests 3.14 too, and
  a test fails when the version classifiers drift from the CI matrix.
- The README documents the keyword arguments `template`, `pdf_template_id`,
  `france_ctc`, `target_profile`, `drop_france_ctc_overlay` and `advanced`.
- The vendored spec carries `payee` (BG-10), `taxRepresentative` (BG-11),
  `paidAmount` (BT-113), `roundingAmount` (BT-114) and `typeCode` (BT-3) on
  the invoice of `/v1/generate` and `/v1/parse`, and `precedingInvoiceReference`
  (BG-3) on invoices as well as credit notes. The API derives the amount due
  (BT-115) from the two amounts. `Invoice` stays `dict[str, Any]`, so the
  fields need no code to send, and a `typeCode` sent with `fatturapa`,
  `facturae` or `eslog` is a 422 `DOCUMENT_TYPE_STANDARD_MISMATCH`, a code
  `API_ERROR_CODES` already lists.

## 0.3.2 - 2026-09-23

- `DocumentAllowanceCharge` and `LineAllowanceCharge` name the allowances and
  charges an invoice carries at document level (BG-20, BG-21) and line level
  (BG-27, BG-28), as `allowances` and `charges`. A document-level entry states
  its own VAT (`vatCategoryCode` required, `vatRate` optional); a line-level
  entry inherits the line's and accepts neither, so a line entry with
  `vatRate` is a 400. `Invoice` stays `dict[str, Any]`; the two TypedDicts are
  annotations a caller opts into. The README shows both.
- The vendored spec carries those fields on `/v1/generate` and `/v1/parse`,
  and `previousChannel` on `GET /v1/rulesets`: what `Beliq-Ruleset: previous`
  reaches for each format, with `servingVersion`, `previousVersion` and a
  `fallbackReason` of `sunset`, `notice-period` or `superseded`.

## 0.3.1 - 2026-09-21

- The vendored spec carries item price detail and item identity on the invoice
  line: `grossPrice` (BT-148) with the per-unit `priceDiscount` (BT-147),
  `priceBaseQuantity` (BT-149/150), `standardItemId` (BT-157),
  `classifications` (BT-158), `originCountryCode` (BT-159) and `attributes`
  (BG-32). A discount needs a gross price and `unitPrice` must equal
  `grossPrice` minus `priceDiscount`, or the API answers 400. With a base
  quantity the line net (BT-131) is quantity x (`unitPrice` /
  `priceBaseQuantity`), which is what lets a caller who prices per 100 units
  pass PEPPOL-EN16931-R120. The fatturapa, facturae and eslog targets read none
  of these fields. No source change: these fields already passed through.
- `uv.lock` pins the development and CI tree, and CI installs with `--locked`
  so a stale lock fails the job instead of being re-resolved quietly. It pins
  what contributors and CI get, not what `pip install beliq` resolves for users.
- The release workflow refuses a tag whose version disagrees with
  `pyproject.toml`. Tagging v0.3.1 against a manifest reading 0.3.0 used to
  publish 0.3.0 and exit green, leaving a tag naming a version that never
  shipped.

## 0.3.0 - 2026-09-19

- `LIVE_PROFILES_BY_STANDARD`, the per-standard profile table the Node SDK
  already had: which profile each standard accepts, and which standards pin
  their own and reject one sent by the caller.
- `GET /v1/rulesets` reports retained ruleset versions, so a caller can see
  which older rule sets are still servable rather than only the current one.
- Participant enrollment codes, the invoice delivery fields, and the
  capabilities reported on a scheduled ruleset change are in the vendored spec
  and the contract tests.
- BT-6 (VAT accounting currency) and BT-111 (VAT amount in the accounting
  currency) are in the vendored spec.
- The PyPI project page shows an invoice the API accepts as-is.
- An em-dash scrub gate runs over the whole tree before publish, and the
  release workflow carries job timeouts and refuses a tag that is not on `main`.

## 0.2.1 - 2026-09-02

- A spent monthly quota is raised, not retried. A 429 carrying
  `QUOTA_EXCEEDED` is terminal, so the SDK makes exactly one attempt; a 429
  carrying `RATE_LIMITED` or `ACCOUNT_THROTTLED` still retries. Retrying an
  exhausted quota only burned the caller's own backoff window.
- A per-attempt deadline, and transient failures are retried.
- The France transmission verdict fields and pre-flight error codes, the ten
  Peppol emit error codes, the 413 responses and the verdict verification tier
  are typed; two error codes the API no longer declares are dropped.
- The three `/v1/me` fields the models had never caught up with are declared.
- The drift check is directional in the code rather than only in its docstring,
  and the vendored spec stops escaping non-ASCII.
- GitHub Actions are pinned to commit SHAs, on node24 runtimes.

## 0.2.0 - 2026-07-24

- Refreshed to API 0.2.0: the generate seal, `livemode`, and the NLCIUS preset.

## 0.1.0 - 2026-06-30

- First published release. Python SDK for the beliq e-invoice API: generate,
  validate, parse and convert, typed and `py.typed`.
