"""Tests for the family registry (spec §7).

`REGISTRY` is the one place `config`, `selection` and `cli` learn which
families exist. The tests that matter are therefore about agreement: every key
is an identifier `vocabulary` knows, and every value really is a family
function that returns a Score. Tasks B6-B8 extend the first two assertions by
adding their family; nothing here is specific to `chromatic` except the
smoke test's parameters.
"""

from __future__ import annotations

from conftest import assert_central_invariant

from melete import vocabulary
from melete.families import REGISTRY
from melete.families.chromatic import generate as chromatic_generate
from melete.instrument import PROFILES
from melete.score import Score

SPEC: dict[str, object] = {
    "permutation": (4, 3, 2, 1),
    "start_string": 0,
    "start_fret": 3,
    "direction": "up",
    "string_traversal": "adjacent",
    "shift": "none",
    "span": 2,
}


def test_the_registry_maps_an_identifier_to_the_family_function() -> None:
    assert REGISTRY["chromatic"] is chromatic_generate


def test_every_registered_family_is_in_the_vocabulary() -> None:
    # A family the registry has and the registry of identifiers does not would
    # be one `config` cannot validate a pool section for (§13).
    assert set(REGISTRY) <= set(vocabulary.accepted("family"))


def test_a_family_can_be_generated_through_the_registry() -> None:
    score = REGISTRY["chromatic"](PROFILES["bass5"], SPEC)
    assert isinstance(score, Score)
    assert_central_invariant(score)
