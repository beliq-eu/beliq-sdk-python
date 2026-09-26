"""The PyPI metadata claims only the Python versions CI actually tests.

The per-version classifiers in pyproject.toml are what the PyPI page lists as
supported, and the test matrix in .github/workflows/ci.yml is what runs the
suite. Both are hand-kept lists, so these tests read the two files side by side.
Releases up to 0.3.2 shipped with neither the per-version rows nor
`Typing :: Typed`, although the wheel carries py.typed.
"""

import ast
import re
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
CLASSIFIERS: list[str] = PROJECT["classifiers"]
VERSION_CLASSIFIER = re.compile(r"^Programming Language :: Python :: (3\.\d+)$")


def _ci_matrix_versions() -> list[str]:
    lines = (ROOT / ".github" / "workflows" / "ci.yml").read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "matrix:")
    key, _, value = lines[start + 1].strip().partition(":")
    # A reformatted matrix (a block list, another key first) fails here rather
    # than being read as "no versions".
    assert key == "python-version" and value.strip().startswith("["), (
        f"expected a one-line python-version list right under matrix:, got {lines[start + 1]!r}"
    )
    return list(ast.literal_eval(value.strip()))


def test_version_classifiers_are_exactly_the_ci_matrix() -> None:
    tested = set(_ci_matrix_versions())
    classified = {m.group(1) for c in CLASSIFIERS if (m := VERSION_CLASSIFIER.match(c))}
    assert tested, "found no Python versions in ci.yml's test matrix"
    assert classified == tested


def test_requires_python_floor_is_the_oldest_version_ci_tests() -> None:
    oldest = min(_ci_matrix_versions(), key=lambda v: tuple(int(p) for p in v.split(".")))
    assert PROJECT["requires-python"] == f">={oldest}"


def test_typed_classifier_matches_the_shipped_marker() -> None:
    assert (ROOT / "src" / "beliq" / "py.typed").is_file()
    assert "Typing :: Typed" in CLASSIFIERS
