"""Refresh the vendored openapi.json.

Prefers a sibling beliq-api checkout (../../beliq-api/openapi.json), falls back
to fetching the live spec. The vendored copy is committed so builds stay
reproducible; run this only when the API surface changes, then
`python scripts/gen_models.py` and commit both.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "openapi.json"
SIBLING = ROOT / ".." / ".." / "beliq-api" / "openapi.json"
LIVE_URL = "https://api.beliq.eu/openapi.json"


def normalize(text: str) -> str:
    return json.dumps(json.loads(text), indent=2) + "\n"


def main() -> None:
    if SIBLING.exists():
        DEST.write_text(normalize(SIBLING.read_text()))
        print(f"synced from {SIBLING}")
    else:
        with urllib.request.urlopen(LIVE_URL) as resp:  # noqa: S310 (trusted URL)
            DEST.write_text(normalize(resp.read().decode("utf-8")))
        print(f"synced from {LIVE_URL}")


if __name__ == "__main__":
    main()
