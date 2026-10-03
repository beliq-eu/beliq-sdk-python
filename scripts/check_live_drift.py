"""Fail when the vendored openapi.json disagrees with the deployed live spec.

tests/test_spec_contract.py only checks the hand-written contracts against the
vendored spec; this catches the vendored spec itself going stale. Runs on every
change and weekly.

Two questions, both from ``_spec_surface.py``, which explains what counts as
surface and why no other value is compared; ``tests/test_spec_surface.py`` pins
the behaviour in both directions:

- missing surface: a path, field or enum value the live spec has and the
  vendored copy lacks. Directional, so a copy legitimately ahead of the deploy
  is silent.
- diverging descriptions: text the two documents do not spell identically,
  in either direction, because prose carries no direction.

A network failure is a soft pass (warn, exit 0) so a hiccup never cries wolf.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _spec_surface import descriptions_diverging, surface_missing_from  # noqa: E402

VENDORED = Path(__file__).resolve().parent.parent / "openapi.json"
LIVE_URL = "https://api.beliq.eu/openapi.json"


SHOWN = 20


def listing(entries: list[str]) -> str:
    shown = "\n".join(f"  - {entry}" for entry in entries[:SHOWN])
    return shown + (f"\n  ...and {len(entries) - SHOWN} more" if len(entries) > SHOWN else "")


def main() -> int:
    try:
        with urllib.request.urlopen(LIVE_URL) as resp:  # noqa: S310 (trusted URL)
            live_text = resp.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError) as err:
        print(f"could not reach {LIVE_URL} ({err}); skipping drift check")
        return 0

    live = json.loads(live_text)
    vend = json.loads(VENDORED.read_text(encoding="utf-8"))

    missing = surface_missing_from(live, vend)
    diverging = descriptions_diverging(live, vend)

    if not missing and not diverging:
        print("vendored openapi.json covers the live spec, descriptions included")
        return 0

    if missing:
        print(
            f"vendored openapi.json is behind the live spec ({len(missing)} missing):\n"
            + listing(missing),
            file=sys.stderr,
        )
    if diverging:
        print(
            f"vendored openapi.json and the live spec disagree on "
            f"{len(diverging)} description(s):\n" + listing(diverging),
            file=sys.stderr,
        )
    print(
        "Run `python scripts/sync_spec.py` and commit the result. A description the vendored copy "
        "carries and the live spec does not can also mean the spec change it was synced from is "
        "merged but not deployed yet.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
