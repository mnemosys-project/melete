"""Tests for the family registry (spec §7).

`REGISTRY` is the one place `config`, `selection` and `cli` learn which
families exist. The tests that matter are therefore about agreement: every key
is an identifier `vocabulary` knows, and every value really is a family
function that returns a `(Score, LayoutHints)` pair (§4.2). With task B8 all four
of §7's families are
registered, so the vocabulary agreement is an equality rather than a subset: a
family enumerated for configuration but missing from the registry is one
`selection` could draw and nothing could realize.

The entries are `Family` records rather than bare functions, so the tempo range
and the axis list each family declares reach a caller through the same lookup
the generate function does. Two tests below are what keep that lookup honest:
one asserts the record really is the family module's own declaration, and one
asserts those declarations are §7's revised tempo table.
"""

from __future__ import annotations

from conftest import assert_central_invariant, assert_spelling_sounds_correctly

from melete import vocabulary
from melete.families import REGISTRY, arpeggios, chromatic, intervals, scales
from melete.families.arpeggios import generate as arpeggios_generate
from melete.families.chromatic import generate as chromatic_generate
from melete.families.intervals import generate as intervals_generate
from melete.families.scales import generate as scales_generate
from melete.instrument import PROFILES
from melete.layout import LayoutHints
from melete.score import Score

SPEC: dict[str, object] = {
    "permutation": (4, 3, 2, 1),
    "start_string": 0,
    "start_fret": 3,
    "string_traversal": "adjacent",
    "shift": "none",
    "span": 2,
}

#: The computed outer-to-outer journey (epic #72 §5): the four axes the family
#: reads after the three geometry axes were retired. Extent, string coverage and
#: octave count are emergent, not sampled — a positional box climbs the whole
#: neck within one hand on this draw.
SCALES_SPEC: dict[str, object] = {
    "root": 33,
    "scale_type": "dorian",
    "traversal": "positional",
    "pattern": "straight",
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
    assert REGISTRY["chromatic"].generate is chromatic_generate
    assert REGISTRY["scales"].generate is scales_generate
    assert REGISTRY["arpeggios"].generate is arpeggios_generate
    assert REGISTRY["intervals"].generate is intervals_generate


def test_the_registry_carries_each_familys_own_declarations() -> None:
    # The record is a lookup over the family module, never a copy of it: a
    # tempo range or an axis list restated here would be exactly the second
    # source of truth `config.DEFAULT_TEMPO` was.
    for identifier, module in (
        ("chromatic", chromatic),
        ("scales", scales),
        ("arpeggios", arpeggios),
        ("intervals", intervals),
    ):
        entry = REGISTRY[identifier]
        assert entry.axes is module.AXES, identifier
        assert entry.default_tempo_range is module.DEFAULT_TEMPO_RANGE, identifier


def test_the_default_tempo_ranges_are_the_ones_in_section_7() -> None:
    # §7's revised table, restated once and deliberately: this is the assertion
    # that fails when the spec is revised and the code is not, or the reverse.
    # Every other reader of a tempo range reaches it through this registry.
    assert {identifier: entry.default_tempo_range for identifier, entry in REGISTRY.items()} == {
        "chromatic": (60, 120),
        "scales": (80, 140),
        "arpeggios": (80, 140),
        "intervals": (70, 130),
    }


def test_every_registered_family_is_in_the_vocabulary() -> None:
    # A family the registry has and the registry of identifiers does not would
    # be one `config` cannot validate a pool section for (§13); one the
    # identifiers have and the registry does not is one `selection` can draw
    # and nothing can realize. All four of §7's families exist, so this is now
    # an equality.
    assert set(REGISTRY) == set(vocabulary.accepted("family"))


def test_a_family_can_be_generated_through_the_registry() -> None:
    score, _hints = REGISTRY["chromatic"].generate(PROFILES["bass5"], SPEC)
    assert isinstance(score, Score)
    assert_central_invariant(score)


def test_every_family_answers_the_same_call() -> None:
    # The contract is `generate(profile, params) -> (Score, LayoutHints)` and
    # nothing else, so a caller dispatching through the registry never learns
    # which family it reached.
    families = (
        ("chromatic", SPEC),
        ("scales", SCALES_SPEC),
        ("arpeggios", ARPEGGIOS_SPEC),
        ("intervals", INTERVALS_SPEC),
    )
    for identifier, spec in families:
        score, _hints = REGISTRY[identifier].generate(PROFILES["bass6"], spec)
        assert isinstance(score, Score)
        assert_central_invariant(score)
        assert_spelling_sounds_correctly(score)
        # The tempo the family declares is the tempo it engraves with, so a
        # caller reading the registry sees what the sheet will say.
        assert score.tempo_range == REGISTRY[identifier].default_tempo_range


def test_every_family_returns_a_score_and_layout_hints() -> None:
    # §4.2 widened the family contract: `generate` returns the Score *and* the
    # LayoutHints the fitter needs, because the natural cell and the turnaround
    # seam are the family's to know and are not recoverable from the voice after
    # the fact. Every family in the registry must satisfy the widened shape, and
    # the one invariant that holds for all four — before #116/#117 settle the
    # precise cycle semantics — is that the cell is a real group size (g >= 1).
    specifications = (
        ("chromatic", SPEC),
        ("scales", SCALES_SPEC),
        ("arpeggios", ARPEGGIOS_SPEC),
        ("intervals", INTERVALS_SPEC),
    )
    for identifier, spec in specifications:
        result = REGISTRY[identifier].generate(PROFILES["bass6"], spec)
        score, hints = result
        assert isinstance(score, Score), identifier
        assert isinstance(hints, LayoutHints), identifier
        assert hints.cell >= 1, identifier


def test_a_specification_names_every_axis_the_registry_advertises() -> None:
    # The registry's `axes` is what `config` builds a pool section from, so a
    # specification satisfying the family must be exactly that set of keys.
    # Anything less is a family that cannot be realized from its own pool.
    specifications = (
        ("chromatic", SPEC),
        ("scales", SCALES_SPEC),
        ("arpeggios", ARPEGGIOS_SPEC),
        ("intervals", INTERVALS_SPEC),
    )
    for identifier, spec in specifications:
        assert set(spec) == set(REGISTRY[identifier].axes), identifier
