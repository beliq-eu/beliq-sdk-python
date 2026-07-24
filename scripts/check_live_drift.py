"""Fail when the vendored openapi.json has fallen BEHIND the deployed live spec.

tests/test_spec_contract.py only checks the hand-written contracts against the
vendored spec; this catches the vendored spec itself going stale. Run on a
schedule.

The check is directional: it fails only when the live spec carries surface the
vendored copy is missing (a new path, operation, field, or enum value). A
vendored copy AHEAD of live (merged but not yet deployed) passes quietly, so
manual deploys never turn this red. A network failure is a soft pass (warn,
exit 0) so a hiccup never cries wolf.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

VENDORED = Path(__file__).resolve().parent.parent / "openapi.json"
LIVE_URL = "https://api.beliq.eu/openapi.json"


def covered_by(live: Any, vendored: Any, path: str, missing: list[str]) -> None:
    """Record every value in ``live`` not present in ``vendored`` (objects by key,
    arrays by element, scalars by equality)."""
    if isinstance(live, list):
        if not isinstance(vendored, list):
            missing.append(path)
            return
        for item in live:
            if not any(_is_covered(item, cand) for cand in vendored):
                missing.append(f"{path}[{json.dumps(item, sort_keys=True)}]")
        return
    if isinstance(live, dict):
        if not isinstance(vendored, dict):
            missing.append(path)
            return
        for key, value in live.items():
            covered_by(value, vendored.get(key), f"{path}.{key}" if path else key, missing)
        return
    if live != vendored:
        missing.append(path)


def _is_covered(live: Any, vendored: Any) -> bool:
    """Boolean form used for array-element matching."""
    probe: list[str] = []
    covered_by(live, vendored, "", probe)
    return not probe


def main() -> int:
    try:
        with urllib.request.urlopen(LIVE_URL) as resp:  # noqa: S310 (trusted URL)
            live_text = resp.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError) as err:
        print(f"could not reach {LIVE_URL} ({err}); skipping drift check")
        return 0

    missing: list[str] = []
    covered_by(json.loads(live_text), json.loads(VENDORED.read_text()), "", missing)

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
