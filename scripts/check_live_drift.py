"""Fail when the vendored openapi.json has fallen BEHIND the deployed live spec.

tests/test_spec_contract.py only checks the hand-written contracts against the
vendored spec; this catches the vendored spec itself going stale. Runs on every
change and weekly.

The comparison lives in ``_spec_surface.py``, which explains what counts as
surface and why values are never compared; ``tests/test_spec_surface.py`` pins
the behaviour in both directions. A network failure is a soft pass (warn, exit
0) so a hiccup never cries wolf.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _spec_surface import surface_missing_from  # noqa: E402

VENDORED = Path(__file__).resolve().parent.parent / "openapi.json"
LIVE_URL = "https://api.beliq.eu/openapi.json"


def main() -> int:
    try:
        with urllib.request.urlopen(LIVE_URL) as resp:  # noqa: S310 (trusted URL)
            live_text = resp.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError) as err:
        print(f"could not reach {LIVE_URL} ({err}); skipping drift check")
        return 0

    missing = surface_missing_from(
        json.loads(live_text),
        json.loads(VENDORED.read_text(encoding="utf-8")),
    )

    if not missing:
        print("vendored openapi.json covers the live spec")
        return 0

    shown = "\n".join(f"  - {m}" for m in missing[:20])
    extra = f"\n  ...and {len(missing) - 20} more" if len(missing) > 20 else ""
    print(
        f"vendored openapi.json is behind the live spec ({len(missing)} missing):\n{shown}{extra}\n"
        "Run `python scripts/sync_spec.py` and commit the result.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
