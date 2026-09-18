"""Fail when LIVE_PROFILES_BY_STANDARD offers a pair the engine would reject.

The table is a client-side copy of a rule only the engine holds, so it can drift
silently: nothing in the vendored spec expresses the pairing (the OpenAPI
``profile`` enum is flat), and a wrong pair surfaces as a 422
PROFILE_STANDARD_MISMATCH in a user's code rather than as a red build. This
reads the engine's own table.

It needs a beliq-engine checkout beside this repo and EXITS NON-ZERO without
one, rather than passing quietly: a check that reports success when it did not
run is worse than no check. That also means it does not belong in CI, where no
sibling exists. Run it whenever the table or the engine's table changes. The
Node SDK's ``npm run check:profiles`` is the same check for its copy.
"""

from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from beliq.constants import LIVE_PROFILES_BY_STANDARD  # noqa: E402

ENGINE = Path(os.environ.get("BELIQ_ENGINE_PATH", ROOT / "../../beliq-engine")).resolve()
ROUTE = ENGINE / "app/routes/generate.py"
VERSIONS = ENGINE / "third-party/versions.json"


def engine_table() -> dict[str, set[str]]:
    # The engine projects the Factur-X set from the pinned artifact rather than
    # writing it out, and ZUGFeRD drops extended-ctc-fr from it. Resolve both
    # the same way, from the same file, instead of keeping a third copy here.
    urns = json.loads(VERSIONS.read_text(encoding="utf-8"))["facturx_schematron"]["profileUrns"]
    facturx = {key.replace("_", "-") for key in urns}
    named = {
        "_FACTURX_PROFILES": facturx,
        "_ZUGFERD_PROFILES": facturx - {"extended-ctc-fr"},
    }

    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "ALLOWED_PROFILES_FOR_STANDARD" for t in node.targets)
            and isinstance(node.value, ast.Dict)
        ):
            table: dict[str, set[str]] = {}
            for key, value in zip(node.value.keys, node.value.values, strict=True):
                standard = ast.literal_eval(key) if key is not None else None
                if not isinstance(standard, str):
                    raise SystemExit(f"unexpected key in ALLOWED_PROFILES_FOR_STANDARD: {ast.dump(key)}")
                if isinstance(value, ast.Name):
                    if value.id not in named:
                        raise SystemExit(f"{standard}: cannot resolve {value.id}; teach this script about it")
                    table[standard] = named[value.id]
                else:
                    table[standard] = set(ast.literal_eval(value))
            return table
    raise SystemExit(f"could not find ALLOWED_PROFILES_FOR_STANDARD in {ROUTE}")


def main() -> int:
    if not ROUTE.is_file() or not VERSIONS.is_file():
        print(
            f"no beliq-engine checkout at {ENGINE}.\n"
            "Set BELIQ_ENGINE_PATH to one. This check cannot run without the engine, "
            "and does not pass without running.",
            file=sys.stderr,
        )
        return 1

    table = engine_table()
    drift: list[str] = []
    for standard, profiles in LIVE_PROFILES_BY_STANDARD.items():
        allowed = table.get(standard)
        if allowed is None:
            drift.append(f"{standard}: the engine has no entry for this standard")
            continue
        for profile in profiles:
            if profile not in allowed:
                drift.append(f'{standard}: "{profile}" is not in the engine\'s set {sorted(allowed)}')

    if drift:
        print("LIVE_PROFILES_BY_STANDARD offers pairs the engine rejects:", file=sys.stderr)
        for line in drift:
            print(f"  - {line}", file=sys.stderr)
        return 1

    checked = len(LIVE_PROFILES_BY_STANDARD)
    print(f"LIVE_PROFILES_BY_STANDARD is a subset of the engine's table ({checked} standards checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
