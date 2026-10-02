"""Refresh the vendored openapi.json.

Reads the file BELIQ_OPENAPI_PATH names when that is set, and fetches the live
spec otherwise. The vendored copy is committed so builds stay
reproducible; run this only when the API surface changes, then commit it.
Nothing is generated from it here: the models in src/beliq/types.py are
hand-written, and the spec is what tests/test_spec_contract.py pins them
against. The Node SDK does codegen from its copy (`npm run gen:types`).
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "openapi.json"
LIVE_URL = "https://api.beliq.eu/openapi.json"


def normalize(text: str) -> str:
    # ensure_ascii=False, or every non-ASCII character in a description is
    # escaped (`·` becomes `·`) and this copy can never be byte-identical to
    # the one the API generates or the one the Node SDK vendors, no matter how
    # often it is re-synced.
    return json.dumps(json.loads(text), indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    local = os.environ.get("BELIQ_OPENAPI_PATH")
    if local:
        DEST.write_text(normalize(Path(local).read_text()))
        print(f"synced from {local}")
    else:
        with urllib.request.urlopen(LIVE_URL) as resp:  # noqa: S310 (trusted URL)
            DEST.write_text(normalize(resp.read().decode("utf-8")))
        print(f"synced from {LIVE_URL}")


if __name__ == "__main__":
    main()
