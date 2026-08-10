"""Package-level guards.

These are deliberately not placeholder tests. The version check catches a real
drift: VERSION is the source of truth that the release tooling bumps, and
pyproject.toml carries its own copy, so the two can silently disagree.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import melete

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_package_imports_and_exposes_a_version() -> None:
    assert melete.__version__
    assert melete.__version__.count(".") == 2


def test_version_matches_the_version_file() -> None:
    on_disk = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert melete.__version__ == on_disk, (
        f"melete.__version__ is {melete.__version__!r} but VERSION says {on_disk!r}"
    )


def test_version_matches_pyproject() -> None:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)
    assert melete.__version__ == pyproject["project"]["version"]


def test_there_are_no_runtime_python_dependencies() -> None:
    """Spec section 15, decision 5: a minimal dependency surface.

    Adding a runtime dependency is a design change, not a detail, so it should
    fail here and be argued for rather than arrive unnoticed.

    LilyPond is required but is a binary on PATH, not a Python package: the
    PyPI redistribution has no aarch64 wheel for any release, so it cannot be
    a hard dependency on the hardware this is developed and used on.
    """
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)
    assert pyproject["project"]["dependencies"] == []


def test_the_bundled_lilypond_extra_stays_pinned() -> None:
    """An unpinned range would silently change the renderer between installs."""
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)
    extras = pyproject["project"]["optional-dependencies"]
    assert extras["bundled-lilypond"] == ["lilypond==2.25.12"]
