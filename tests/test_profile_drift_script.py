"""``scripts/check_profile_drift.py`` must read the engine's table, or say it cannot.

The script compares LIVE_PROFILES_BY_STANDARD against the engine's
ALLOWED_PROFILES_FOR_STANDARD, and the engine's source is private, so CI cannot
run it against the real table. It spent a month crashing instead of reporting:
the engine moved two rows from a module constant to a function call
(``"zugferd": zugferd_profile_keys()``) and ``ast.literal_eval`` raised on the
call expression. Nothing noticed, because the only thing that ran the script was
a person running it by hand.

These cases run it against a generated stand-in engine, so the resolution and
the comparison are covered in CI even though the real table is not. The
stand-in's rows are rendered FROM ``LIVE_PROFILES_BY_STANDARD``, so nothing here
is a second copy of the engine's rule, and nothing here claims the real table
says anything in particular: that is what a run with BELIQ_ENGINE_PATH is for.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from beliq.constants import LIVE_PROFILES_BY_STANDARD

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_profile_drift.py"

# The row the stand-in renders as a call rather than a set literal, so a run
# covers both shapes the engine uses.
CALLED_STANDARD = "zugferd"


def write_engine(root: Path, table: dict[str, tuple[str, ...]], *, row: str | None = None) -> Path:
    """A stand-in engine checkout: the two files the script reads, and nothing else."""
    (root / "app" / "routes").mkdir(parents=True)
    (root / "third-party").mkdir()
    (root / "third-party" / "versions.json").write_text("{}", encoding="utf-8")

    helper = f"{CALLED_STANDARD}_profile_keys"
    rows = []
    for standard, profiles in table.items():
        if standard == CALLED_STANDARD and row is None:
            rows.append(f'    "{standard}": {helper}(),')
        elif standard == CALLED_STANDARD and row is not None:
            rows.append(f'    "{standard}": {row},')
        else:
            rows.append(f'    "{standard}": {{{", ".join(repr(p) for p in profiles)}}},')
    (root / "app" / "routes" / "generate.py").write_text(
        "ALLOWED_PROFILES_FOR_STANDARD = {\n" + "\n".join(rows) + "\n}\n", encoding="utf-8"
    )
    (root / "app" / "versions.py").write_text(
        f"def {helper}():\n    return frozenset({sorted(table[CALLED_STANDARD])!r})\n",
        encoding="utf-8",
    )
    return root


def run(engine: Path | None) -> subprocess.CompletedProcess[str]:
    # A bare environment, so a BELIQ_ENGINE_PATH in the shell that runs pytest
    # cannot point these cases at the real engine.
    env = {"PATH": "/usr/bin:/bin"}
    if engine is not None:
        env["BELIQ_ENGINE_PATH"] = str(engine)
    return subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True, env=env, check=False
    )


def test_passes_when_every_row_resolves_and_covers_the_map(tmp_path):
    result = run(write_engine(tmp_path, dict(LIVE_PROFILES_BY_STANDARD)))
    assert result.returncode == 0, result.stderr
    assert f"{len(LIVE_PROFILES_BY_STANDARD)} standards checked" in result.stdout


def test_reports_drift_in_a_set_literal_row(tmp_path):
    result = run(write_engine(tmp_path, {**LIVE_PROFILES_BY_STANDARD, "xrechnung": ("something-else",)}))
    assert result.returncode == 1
    assert 'xrechnung: "xrechnung" is not in the engine' in result.stderr


def test_reports_drift_in_a_row_the_engine_resolves_through_a_function(tmp_path):
    # The shape that crashed. A profile the engine's own helper does not return
    # has to read as drift, not as a traceback.
    table = dict(LIVE_PROFILES_BY_STANDARD)
    dropped, *rest = table[CALLED_STANDARD]
    table[CALLED_STANDARD] = tuple(rest)
    engine = write_engine(tmp_path, table)
    # The map still offers the profile the stand-in's helper no longer returns.
    result = run(engine)
    assert result.returncode == 1
    assert f'{CALLED_STANDARD}: "{dropped}" is not in the engine' in result.stderr


def test_reports_a_standard_the_engine_has_no_row_for(tmp_path):
    table = {k: v for k, v in LIVE_PROFILES_BY_STANDARD.items() if k != "ksef"}
    result = run(write_engine(tmp_path, table))
    assert result.returncode == 1
    assert "ksef: the engine has no entry for this standard" in result.stderr


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ("invented_profile_keys()", "defines no invented_profile_keys"),
        ("_SOME_CONSTANT", "cannot resolve _SOME_CONSTANT"),
        ("zugferd_profile_keys('v2')", "cannot resolve zugferd_profile_keys('v2')"),
        ("7", "is not a set of profile keys"),
    ],
)
def test_a_row_it_cannot_read_fails_loudly(tmp_path, row, expected):
    # Silence and a traceback are the same failure from the repo's point of
    # view: the check reads as if it ran. Every unreadable row says what it is
    # and exits non-zero.
    result = run(write_engine(tmp_path, dict(LIVE_PROFILES_BY_STANDARD), row=row))
    assert result.returncode == 1
    assert expected in result.stderr
    assert "Traceback" not in result.stderr


def test_without_an_engine_checkout_it_fails_rather_than_passing(tmp_path):
    assert run(None).returncode == 1
    assert run(tmp_path).returncode == 1
