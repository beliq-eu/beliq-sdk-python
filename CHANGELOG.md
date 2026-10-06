# Changelog

`beliq` is on a 0.x line. Releases are cut from `main` by pushing a `v*.*.*`
tag, and the release workflow refuses a tag whose version disagrees with
`pyproject.toml`.

This SDK types `Invoice` as `dict[str, Any]`, so a new invoice field the API
accepts needs no SDK release to be usable. A spec sync listed below moves the
vendored `openapi.json`, which is what the contract tests and the drift check
read; it does not gate the caller.

## 0.3.7 - 2026-10-06

- The vendored `openapi.json` carries the four fields `POST /v1/parse` answers
  with and the previous copy did not. `warnings` is always present, and empty
  when the parser read every element that holds something: `PARSE_NOT_RETURNED`
  lists what the document carries beyond the parsed `invoice`, by path and
  count, and `PARSE_VALUE_NOT_FOUND` names a field no value could be read for.
  `profileUrn` (BT-24) and `businessProcessId` (BT-23) carry what the document
  states, and the latter is not the `businessProcessId` a `generate()` invoice
  takes, which is an input limited to the three French Flux 2 codes.
  `franceCtcDetected` is true when BT-23 is one of the French cadre de
  facturation codes or BT-24 is the EXTENDED-CTC-FR URN, and absent otherwise.
- `ParseResult` declares all four, as `profile_urn`, `business_process_id`,
  `france_ctc_detected` and `warnings`. The models here are hand-written, so
  the spec sync on its own would have left the four reachable only under their
  wire names through `extra='allow'`. `ParseWarning` and `ParseElementCount`
  carry the warning shape and are exported beside `ParseResult`. The warning
  code stays a `str` rather than a closed set, because a published client has
  to keep parsing an answer from a newer API than it was built against.
- `tests/test_spec_contract.py` pins the seven fields of the `/v1/parse`
  response to the vendored spec, the way it already pins the validate ones.

## 0.3.6 - 2026-10-03

- `LIVE_GENERATE_STANDARDS` carries all eight standards `POST /v1/generate`
  accepts, where it had carried four. The four added are the national XSD
  formats: `fatturapa`, `facturae`, `eslog` and `ksef`. Each is Schema-checked,
  meaning structure only and no business rules, because its authority publishes
  no machine-readable rule pack, and `GET /v1/rulesets` carries the badge.
  `LIVE_PROFILES_BY_STANDARD` gains the one profile each allows: `ordinaria`
  for `fatturapa` and `facturae`, `eracun` for `eslog`, `fa3` for `ksef`. The
  map stays narrower than the engine in one place, the Factur-X `minimum` and
  `basic` profiles, for FNFE-MPE source gating. `LIVE_GENERATE_PRESETS` is
  unchanged: it mirrors what beliq.eu's own generator offers.
- The vendored `openapi.json` carries the corrected `/v1/validate` description.
  It had said that matching a verdict's `rulesetArtifacts` rows against the
  `GET /v1/rulesets` catalog covers publicly-supported formats only, and that a
  national format's components are kept off the catalog. Both were false: the
  catalog publishes every format beliq carries and the component rows each
  ruleset is built from.

## 0.3.5 - 2026-10-02

- `API_ERROR_CODES` carries `INSUFFICIENT_ROLE`: the 403 for a credential that
  is valid while the member behind it holds a role without the capability the
  route needs. Distinct from `INVALID_API_KEY` because the remedy is an owner
  or admin changing a role, not a new key.
- The sdist ships the package only: `src/beliq`, `README.md`, `LICENSE` and
  `CHANGELOG.md`, plus the `pyproject.toml` and `PKG-INFO` hatchling adds
  itself. Releases up to 0.3.4 had no allowlist, so hatchling put every tracked
  file of the repo into the sdist, tests and scripts included. A test now pins
  the allowlist.
- The vendored spec carries Poland KSeF FA(3): `ksef` as a `standard`, with
  profile `fa3`, and an optional `poland` object of FA(3) document fields:
  `placeOfIssue` (emitted as `P_1M`), `dataWytworzenia`, the `Adnotacje`
  markers `P_16`, `P_17`, `P_18`, `P_18A` and `P_23`, and the local-government
  marker `JST` and VAT-group marker `GV`. Each of those seven markers takes a
  `TWybor1_2` value, `"1"` or `"2"`. `GET /v1/rulesets` reports
  `polandKsefFa3RuntimeVersion` and `polandKsefFa3XsdBundle`.
- The vendored spec carries the invoice's billing period (BG-14) and an invoice
  line's own period (BG-26) as `invoicingPeriod`, with `startDate` (BT-73 on
  the invoice, BT-134 on a line) and `endDate` (BT-74, BT-135); the VAT point
  date as `vatPointDate` (BT-7) or `vatPointDateCode` (BT-8, one of `3`, `35`
  and `432`), which exclude each other under BR-CO-03; and the document
  references BT-11 to BT-19 as `projectReference`, `contractReference`,
  `salesOrderReference`, `receivingAdviceReference`, `despatchAdviceReference`,
  `tenderReference`, `invoicedObjectIdentifier` and
  `buyerAccountingReference`. The fatturapa, facturae, eslog and ksef targets
  drop all of them.
- The vendored spec carries additional supporting documents (BG-24) as
  `supportingDocuments`, at most 50 of them: `id` (BT-122), which BR-52
  requires, `description` (BT-123), `externalLocation` (BT-124) and
  `attachment` (BT-125) with the file as base64 `content`, its `mimeCode` and
  its `filename`. Written as a CII `ram:AdditionalReferencedDocument` with type
  code 916, from the Factur-X EN16931 profile up, and as a UBL
  `cac:AdditionalDocumentReference`. On XRechnung BR-DE-22 refuses two
  attachments sharing a `filename`, and DE-R-022 does the same on Peppol BIS
  between two German parties.
- The `/v1/parse` `format` query parameter describes itself in the spec: it is
  checked against the allowed values and otherwise ignored, because the syntax
  is always read from the document itself.

## 0.3.4 - 2026-09-26

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
