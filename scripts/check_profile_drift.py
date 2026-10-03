"""Fail when LIVE_PROFILES_BY_STANDARD offers a pair the engine would reject.

The table is a client-side copy of a rule only the engine holds, so it can drift
silently: nothing in the vendored spec expresses the pairing (the OpenAPI
``profile`` enum is flat), and a wrong pair surfaces as a 422
PROFILE_STANDARD_MISMATCH in a user's code rather than as a red build. This
reads the engine's own table.

It needs a checkout of the engine's source, named by BELIQ_ENGINE_PATH, and
EXITS NON-ZERO without one, rather than passing quietly: a check that reports
success when it did not run is worse than no check. The engine's source is not
public, so this does not belong in CI. Run it whenever the table or the engine's table changes. The
Node SDK's ``npm run check:profiles`` is the same check for its copy.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import sys
from functools import cache
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from beliq.constants import LIVE_PROFILES_BY_STANDARD  # noqa: E402

ENGINE_ENV = os.environ.get("BELIQ_ENGINE_PATH")
ENGINE = Path(ENGINE_ENV).resolve() if ENGINE_ENV else None
ROUTE = ENGINE / "app/routes/generate.py" if ENGINE else None
VERSIONS = ENGINE / "third-party/versions.json" if ENGINE else None
HELPERS = ENGINE / "app/versions.py" if ENGINE else None


@cache
def engine_helpers() -> ModuleType:
    """The engine's own ``app/versions.py``, imported from the checkout.

    Two rows of the table are calls (``"zugferd": zugferd_profile_keys()``):
    the engine projects both profile sets from the pinned Factur-X artifact
    rather than writing them out. Calling its own function is the only
    resolution that cannot disagree with it, where re-deriving the set here
    would add a third copy of the very rule this check compares. The module is
    stdlib-only at import time and reads the checkout's own
    ``third-party/versions.json``.
    """
    spec = importlib.util.spec_from_file_location("beliq_engine_versions", HELPERS)
    if spec is None or spec.loader is None:
        raise SystemExit(f"could not import {HELPERS}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve(standard: str, value: ast.expr) -> set[str]:
    """One row's profile set, from a literal or from the engine's own helper.

    Anything else EXITS NON-ZERO instead of being skipped or crashing. A row
    this script cannot read is a row it cannot compare, and a checker that
    tracebacks on the engine's own table reads, from the repo, exactly like a
    checker that works.
    """
    if isinstance(value, ast.Call):
        if not isinstance(value.func, ast.Name) or value.args or value.keywords:
            raise SystemExit(f"{standard}: cannot resolve {ast.unparse(value)}; teach this script about it")
        resolver = getattr(engine_helpers(), value.func.id, None)
        if resolver is None:
            raise SystemExit(f"{standard}: {HELPERS} defines no {value.func.id}; teach this script about it")
        profiles = resolver()
    else:
        try:
            profiles = ast.literal_eval(value)
        except ValueError:
            raise SystemExit(
                f"{standard}: cannot resolve {ast.unparse(value)}; teach this script about it"
            ) from None

    if not isinstance(profiles, (set, frozenset, list, tuple)) or not all(
        isinstance(profile, str) for profile in profiles
    ):
        raise SystemExit(f"{standard}: resolved to {profiles!r}, which is not a set of profile keys")
    return set(profiles)


def engine_table() -> dict[str, set[str]]:
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
                table[standard] = resolve(standard, value)
            return table
    raise SystemExit(f"could not find ALLOWED_PROFILES_FOR_STANDARD in {ROUTE}")


def main() -> int:
    if (
        ROUTE is None
        or VERSIONS is None
        or HELPERS is None
        or not ROUTE.is_file()
        or not VERSIONS.is_file()
        or not HELPERS.is_file()
    ):
        print(
            (f"no engine checkout at {ENGINE}.\n" if ENGINE else "BELIQ_ENGINE_PATH is not set.\n")
            + "Set BELIQ_ENGINE_PATH to a checkout of the engine source. This check cannot run without the engine, "
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
