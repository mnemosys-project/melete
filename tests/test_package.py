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

    Rendering is a toolchain on PATH, not a Python package: the vendored
    `melete-render/` Node tool (which drives alphaTab) turns emitted alphaTex
    into a Guitar Pro `.gp`, so it is an environment concern rather than a hard
    dependency of the package.
    """
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)
    assert pyproject["project"]["dependencies"] == []
