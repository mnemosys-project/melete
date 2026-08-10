"""Tests for the family registry (spec §7).

`REGISTRY` is the one place `config`, `selection` and `cli` learn which
families exist. The tests that matter are therefore about agreement: every key
is an identifier `vocabulary` knows, and every value really is a family
function that returns a Score. With task B8 all four of §7's families are
registered, so the vocabulary agreement is an equality rather than a subset: a
family enumerated for configuration but missing from the registry is one
`selection` could draw and nothing could realize.
"""

from __future__ import annotations

from conftest import assert_central_invariant, assert_spelling_sounds_correctly

from melete import vocabulary
from melete.families import REGISTRY
from melete.families.arpeggios import generate as arpeggios_generate
from melete.families.chromatic import generate as chromatic_generate
from melete.families.intervals import generate as intervals_generate
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

INTERVALS_SPEC: dict[str, object] = {
    "interval": 3,
    "context": "diatonic",
    "root": 33,
    "scale_type": "dorian",
    "string_skip": "1",
    "string_set": (0, 1, 2, 3),
    "direction": "up",
    "pattern": "ascending_pairs",
}


def test_the_registry_maps_an_identifier_to_the_family_function() -> None:
    assert REGISTRY["chromatic"] is chromatic_generate
    assert REGISTRY["scales"] is scales_generate
    assert REGISTRY["arpeggios"] is arpeggios_generate
    assert REGISTRY["intervals"] is intervals_generate


def test_every_registered_family_is_in_the_vocabulary() -> None:
    # A family the registry has and the registry of identifiers does not would
    # be one `config` cannot validate a pool section for (§13); one the
    # identifiers have and the registry does not is one `selection` can draw
    # and nothing can realize. All four of §7's families exist, so this is now
    # an equality.
    assert set(REGISTRY) == set(vocabulary.accepted("family"))


def test_a_family_can_be_generated_through_the_registry() -> None:
    score = REGISTRY["chromatic"](PROFILES["bass5"], SPEC)
    assert isinstance(score, Score)
    assert_central_invariant(score)


def test_every_family_answers_the_same_call() -> None:
    # The contract is `generate(profile, params) -> Score` and nothing else, so
    # a caller dispatching through the registry never learns which family it
    # reached.
    families = (
        ("chromatic", SPEC),
        ("scales", SCALES_SPEC),
        ("arpeggios", ARPEGGIOS_SPEC),
        ("intervals", INTERVALS_SPEC),
    )
    for identifier, spec in families:
        score = REGISTRY[identifier](PROFILES["bass6"], spec)
        assert isinstance(score, Score)
        assert_central_invariant(score)
        assert_spelling_sounds_correctly(score)
