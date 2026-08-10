"""Tests for the family registry (spec §7).

`REGISTRY` is the one place `config`, `selection` and `cli` learn which
families exist. The tests that matter are therefore about agreement: every key
is an identifier `vocabulary` knows, and every value really is a family
function that returns a Score. Tasks B6-B8 extend the first two assertions by
adding their family; nothing here is specific to `chromatic` except the
smoke test's parameters.
"""

from __future__ import annotations

from conftest import assert_central_invariant, assert_spelling_sounds_correctly

from melete import vocabulary
from melete.families import REGISTRY
from melete.families.arpeggios import generate as arpeggios_generate
from melete.families.chromatic import generate as chromatic_generate
from melete.families.scales import generate as scales_generate
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

SCALES_SPEC: dict[str, object] = {
    "root": 33,
    "scale_type": "dorian",
    "traversal": "positional",
    "string_set": (0, 1, 2, 3),
    "pattern": "straight",
    "range_octaves": 2,
    "direction": "up",
}

ARPEGGIOS_SPEC: dict[str, object] = {
    "root": 33,
    "quality": "maj7",
    "inversion": "root",
    "traversal": "across_strings",
    "string_set": (0, 1, 2, 3),
    "pattern": "straight",
    "range_octaves": 1,
    "direction": "up",
}


def test_the_registry_maps_an_identifier_to_the_family_function() -> None:
    assert REGISTRY["chromatic"] is chromatic_generate
    assert REGISTRY["scales"] is scales_generate
    assert REGISTRY["arpeggios"] is arpeggios_generate


def test_every_registered_family_is_in_the_vocabulary() -> None:
    # A family the registry has and the registry of identifiers does not would
    # be one `config` cannot validate a pool section for (§13).
    assert set(REGISTRY) <= set(vocabulary.accepted("family"))


def test_a_family_can_be_generated_through_the_registry() -> None:
    score = REGISTRY["chromatic"](PROFILES["bass5"], SPEC)
    assert isinstance(score, Score)
    assert_central_invariant(score)


def test_every_family_answers_the_same_call() -> None:
    # The contract is `generate(profile, params) -> Score` and nothing else, so
    # a caller dispatching through the registry never learns which family it
    # reached.
    families = (("chromatic", SPEC), ("scales", SCALES_SPEC), ("arpeggios", ARPEGGIOS_SPEC))
    for identifier, spec in families:
        score = REGISTRY[identifier](PROFILES["bass6"], spec)
        assert isinstance(score, Score)
        assert_central_invariant(score)
        assert_spelling_sounds_correctly(score)
