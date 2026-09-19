from importlib.metadata import version

import beliq


def test_dunder_version_matches_the_published_package_version():
    # __version__ is a hand-kept copy of pyproject.toml's version; 0.2.1 shipped
    # to PyPI still saying 0.2.0.
    assert beliq.__version__ == version("beliq")
