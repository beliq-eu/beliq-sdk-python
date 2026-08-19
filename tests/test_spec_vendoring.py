"""The vendored openapi.json must be byte-identical to beliq-api's copy.

Three copies of one contract exist — beliq-api's generated artifact, the Node
SDK's vendored copy, and this one — and a client generated from a stale or
differently-serialized copy types the API wrongly.

Byte equality across three languages only holds if every copy is serialized the
same way, and that is where it broke: `scripts/sync_spec.py` used `json.dumps`
at its default `ensure_ascii=True`, so this copy escaped every non-ASCII
character in a description and could never match, however often it was
re-synced.

Re-serializing here and requiring a fixpoint catches that class without needing
the sibling checkout this SDK's CI does not have.
"""

from __future__ import annotations

import json
from pathlib import Path

VENDORED = Path(__file__).resolve().parent.parent / "openapi.json"


def test_vendored_spec_is_in_canonical_form() -> None:
    text = VENDORED.read_text(encoding="utf-8")
    canonical = json.dumps(json.loads(text), indent=2, ensure_ascii=False) + "\n"
    assert text == canonical, (
        "openapi.json is not in canonical form, so it was written by something "
        "other than the current sync script. Run `python scripts/sync_spec.py` "
        "and commit the result."
    )


def test_vendored_spec_declares_a_real_document_version() -> None:
    spec = json.loads(VENDORED.read_text(encoding="utf-8"))
    assert spec["info"]["version"] not in ("", "0.1.0")
