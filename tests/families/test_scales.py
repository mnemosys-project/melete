"""Tests for the `scales` family (spec §7).

The shape follows `test_chromatic.py`, because every family makes the same
promise and §14 tests them the same way: one complete cycle, the central
invariant, the exact parameters travelling inside the Score, a family-declared
tempo, and a wide parameter sweep over the axes.

Two halves are specific to this family. The *layout* tests assert that position
selection is the family's job (spec §6): a traversal decides which string each
scale degree is played on, and a degree that the pattern visits twice is played
in the same place both times. The *error* tests assert that a specification the
profile cannot supply raises and names what could not be satisfied — §9
resamples that case and §13 forbids clamping it into something engravable.
"""

from __future__ import annotations

from collections import Counter
from fractions import Fraction
from itertools import product
from typing import TYPE_CHECKING

import pytest
from conftest import assert_central_invariant, assert_spelling_sounds_correctly, notes_of

from melete import theory
from melete.families.scales import DEFAULT_TEMPO_RANGE, INSTRUCTION, generate
from melete.instrument import PROFILES, positions

if TYPE_CHECKING:
    from melete.score import Score

BASS6 = PROFILES["bass6"]

#: The four lowest strings of a six-string bass: B E A D.
STRING_SET: tuple[int, ...] = (0, 1, 2, 3)

#: A1 = 33. Two octaves of Ionian is fifteen degrees, which is the length the
#: plan's worked example uses throughout.
PARAMS: dict[str, object] = {
    "root": 33,
    "scale_type": "ionian",
    "traversal": "positional",
    "string_set": STRING_SET,
    "pattern": "straight",
    "range_octaves": 2,
    "direction": "up",
}

#: The degrees of two-octave A Ionian, ascending. Written out rather than
#: derived so the expectations below are readable without running `theory`.
IONIAN_A2 = [33, 35, 37, 38, 40, 42, 44, 45, 47, 49, 50, 52, 54, 56, 57]

PATTERNS = ["straight", "thirds", "fourths", "groups_of_3", "groups_of_4", "numeric_1235"]
DIRECTIONS = ["up", "down", "up_down"]


def params(**overrides: object) -> dict[str, object]:
    """`PARAMS` with one or more axes replaced."""
    return {**PARAMS, **overrides}


def pitches_of(score: Score) -> list[int]:
    """The pitch of every note, in playing order."""
    return [note.pitch for note in notes_of(score)]


def places_of(score: Score) -> list[tuple[int, int]]:
    """The (string, fret) of every note, in playing order."""
    return [(note.string, note.fret) for note in notes_of(score)]


# --------------------------------------------------------------------------
# The family contract
# --------------------------------------------------------------------------


def test_generates_one_complete_cycle() -> None:
    # 2 x 7 degrees plus the closing octave (spec §7: never truncated).
    assert len(generate(BASS6, PARAMS).voice) == 15


def test_obeys_the_central_invariant() -> None:
    assert_central_invariant(generate(BASS6, PARAMS))


def test_spells_every_note_as_it_sounds() -> None:
    assert_spelling_sounds_correctly(generate(BASS6, PARAMS))


def test_the_key_is_the_root_and_the_scale_type() -> None:
    # §10a: the family already holds both, so stating the key costs it nothing
    # — and not stating it costs every note on the sheet its spelling.
    assert generate(BASS6, PARAMS).key == theory.Key(9, "ionian")


@pytest.mark.parametrize(("root", "tonic"), [(33, 9), (24, 0), (30, 6)])
def test_the_tonic_is_a_pitch_class_and_not_the_root_pitch(root: int, tonic: int) -> None:
    # A1 and A2 are the same key. `root` stays an absolute pitch everywhere
    # else (§10a), which is exactly why the reduction has to happen here.
    assert generate(BASS6, params(root=root)).key == theory.Key(tonic, "ionian")


def test_params_travel_inside_the_score() -> None:
    assert generate(BASS6, PARAMS).params == PARAMS


def test_default_tempo_range_is_declared_by_the_family() -> None:
    # Spec §7: the family declares the range and the selector never samples it.
    assert DEFAULT_TEMPO_RANGE == (80, 140)
    assert generate(BASS6, PARAMS).tempo_range == (80, 140)


def test_the_notes_are_plain_and_unaccented() -> None:
    # §8's rhythm modifier owns subdivision and accents; this family states the
    # un-modified reading and nothing more.
    score = generate(BASS6, PARAMS)
    assert score.time_signature == (4, 4)
    assert {(note.duration, note.accent) for note in notes_of(score)} == {(Fraction(1, 4), False)}


def test_the_fingering_is_left_unspecified() -> None:
    # §6 makes `finger` first class because in *chromatic* work the fingering is
    # the exercise. Here the position is, and prescribing a finger would engrave
    # a fingering the caller never asked for.
    assert {note.finger for note in notes_of(generate(BASS6, PARAMS))} == {None}


def test_the_score_carries_a_title_and_a_focus_cue() -> None:
    score = generate(BASS6, params(root=38, scale_type="dorian"))
    assert score.title == "D Dorian, positional, ascending"
    assert score.instruction == INSTRUCTION


def test_the_title_names_a_pattern_only_when_there_is_one() -> None:
    assert generate(BASS6, PARAMS).title == "A Ionian, positional, ascending"
    thirds = generate(BASS6, params(pattern="thirds"))
    assert thirds.title == "A Ionian, positional, ascending thirds"


def test_generate_is_pure() -> None:
    given = params()
    first, second = generate(BASS6, given), generate(BASS6, given)
    assert first == second
    assert given == PARAMS

    # The Score owns its parameters: a caller reusing the dictionary it passed
    # in must not be able to rewrite the record of what was generated.
    first.params["root"] = 99
    assert given["root"] == 33


# --------------------------------------------------------------------------
# Pitch content comes from `theory`
# --------------------------------------------------------------------------


def test_scale_content_matches_theory() -> None:
    score = generate(BASS6, PARAMS)
    assert {note.pitch % 12 for note in notes_of(score)} == {
        (33 + offset) % 12 for offset in (0, 2, 4, 5, 7, 9, 11)
    }


def test_the_degrees_are_theory_s_and_in_theory_s_order() -> None:
    assert pitches_of(generate(BASS6, PARAMS)) == theory.scale_pitches(33, "ionian", 2)
    assert pitches_of(generate(BASS6, PARAMS)) == IONIAN_A2


def test_one_octave_closes_on_the_octave() -> None:
    score = generate(BASS6, params(range_octaves=1))
    assert pitches_of(score) == [33, 35, 37, 38, 40, 42, 44, 45]


def test_three_octaves_span_three_octaves() -> None:
    score = generate(BASS6, params(range_octaves=3, string_set=(0, 1, 2, 3, 4, 5)))
    assert len(score.voice) == 22
    assert pitches_of(score)[-1] - pitches_of(score)[0] == 36


def test_stays_within_the_declared_string_set() -> None:
    score = generate(BASS6, PARAMS)
    assert {note.string for note in notes_of(score)} <= {0, 1, 2, 3}


# --------------------------------------------------------------------------
# `direction` orders the sequence (the `chromatic` precedent)
# --------------------------------------------------------------------------


def test_direction_up_ascends() -> None:
    assert pitches_of(generate(BASS6, PARAMS)) == IONIAN_A2


def test_direction_down_reverses_the_sequence() -> None:
    assert pitches_of(generate(BASS6, params(direction="down"))) == IONIAN_A2[::-1]


def test_up_down_returns_without_replaying_the_apex() -> None:
    score = generate(BASS6, params(direction="up_down"))
    assert len(score.voice) == 29  # 15 up + 14 down
    assert pitches_of(score) == IONIAN_A2 + IONIAN_A2[-2::-1]


def test_direction_reorders_without_changing_the_content() -> None:
    up = generate(BASS6, PARAMS)
    for direction in DIRECTIONS:
        other = generate(BASS6, params(direction=direction))
        assert set(pitches_of(other)) == set(pitches_of(up))


# --------------------------------------------------------------------------
# `pattern` reorders the degrees before positions are assigned
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pattern", "count"),
    [
        ("straight", 15),  # every degree once
        ("thirds", 26),  # 2 x (15 - 2)
        ("fourths", 24),  # 2 x (15 - 3)
        ("groups_of_3", 39),  # 3 x (15 - 2)
        ("groups_of_4", 48),  # 4 x (15 - 3)
        ("numeric_1235", 44),  # 4 x (15 - 4)
    ],
)
def test_each_pattern_emits_one_complete_cycle(pattern: str, count: int) -> None:
    score = generate(BASS6, params(pattern=pattern))
    assert len(score.voice) == count
    assert_central_invariant(score)


def test_thirds_produces_more_notes_than_straight() -> None:
    straight = generate(BASS6, PARAMS)
    thirds = generate(BASS6, params(pattern="thirds"))
    assert len(thirds.voice) > len(straight.voice)


def test_thirds_emits_1_3_2_4_3_5() -> None:
    played = pitches_of(generate(BASS6, params(pattern="thirds")))
    assert played[:6] == [IONIAN_A2[i] for i in (0, 2, 1, 3, 2, 4)]
    assert played[-2:] == [IONIAN_A2[12], IONIAN_A2[14]]


def test_groups_of_3_emits_overlapping_groups() -> None:
    played = pitches_of(generate(BASS6, params(pattern="groups_of_3")))
    assert played[:9] == [IONIAN_A2[i] for i in (0, 1, 2, 1, 2, 3, 2, 3, 4)]


def test_numeric_1235_skips_the_fourth_degree_of_each_group() -> None:
    played = pitches_of(generate(BASS6, params(pattern="numeric_1235")))
    assert played[:8] == [IONIAN_A2[i] for i in (0, 1, 2, 4, 1, 2, 3, 5)]


def test_a_pattern_reorders_without_changing_the_content() -> None:
    straight = generate(BASS6, PARAMS)
    for pattern in PATTERNS:
        other = generate(BASS6, params(pattern=pattern))
        assert set(pitches_of(other)) == set(pitches_of(straight))


def test_a_descending_pattern_is_the_retrograde_of_the_ascending_one() -> None:
    # `pattern` shapes the sequence and `direction` then orders it, so
    # descending thirds fall out as the retrograde rather than as a second
    # implementation of the same figure.
    up = pitches_of(generate(BASS6, params(pattern="thirds")))
    down = pitches_of(generate(BASS6, params(pattern="thirds", direction="down")))
    assert down == up[::-1]


def test_up_down_in_thirds_does_not_replay_the_apex() -> None:
    score = generate(BASS6, params(pattern="thirds", direction="up_down"))
    assert len(score.voice) == 51  # 26 up + 25 down


# --------------------------------------------------------------------------
# The traversals: position selection is the family's job (spec §6)
# --------------------------------------------------------------------------


def test_positional_chooses_the_box_minimizing_fret_travel() -> None:
    # A minor pentatonic over strings 2-3 of bass6 (A1 = 33, D2 = 38). Base
    # fret 5 costs eleven frets of travel and every other base fret costs more
    # — 12 at frets 3 and 4, 13 at frets 2 and 6 — so each degree takes the
    # candidate nearest fret 5. The answer is the box a player would use: A C D
    # E on the A string from the open root, then G A on the D string.
    score = generate(
        BASS6,
        params(root=33, scale_type="minor_pentatonic", range_octaves=1, string_set=(2, 3)),
    )
    assert places_of(score) == [(2, 0), (2, 3), (2, 5), (2, 7), (3, 5), (3, 7)]


def test_positional_travels_less_than_taking_every_degree_on_the_lowest_string() -> None:
    # The independent check on the objective: the layout the family chose is
    # tighter under the hand than the obvious alternative of always taking the
    # lowest string in the set that can reach the degree.
    chosen = [note.fret for note in notes_of(generate(BASS6, PARAMS))]
    lowest = [
        next(fret for string, fret in positions(BASS6, pitch) if string in STRING_SET)
        for pitch in IONIAN_A2
    ]
    assert max(chosen) - min(chosen) < max(lowest) - min(lowest)


def test_positional_may_use_every_string_in_the_set() -> None:
    score = generate(BASS6, PARAMS)
    assert len({note.string for note in notes_of(score)}) > 1


def test_three_note_per_string_puts_exactly_three_notes_on_each_string() -> None:
    score = generate(BASS6, params(traversal="three_note_per_string", string_set=(0, 1, 2, 3, 4)))
    counts = Counter(note.string for note in notes_of(score))
    assert set(counts.values()) == {3}
    assert sorted(counts) == [0, 1, 2, 3, 4]


def test_three_note_per_string_assigns_consecutive_degrees_to_each_string() -> None:
    score = generate(BASS6, params(traversal="three_note_per_string", string_set=(0, 1, 2, 3, 4)))
    assert places_of(score) == [
        (0, 10), (0, 12), (0, 14),
        (1, 10), (1, 12), (1, 14),
        (2, 11), (2, 12), (2, 14),
        (3, 11), (3, 12), (3, 14),
        (4, 11), (4, 13), (4, 14),
    ]  # fmt: skip


def test_octave_per_string_puts_one_octave_on_each_string() -> None:
    score = generate(BASS6, params(traversal="octave_per_string", string_set=(2, 3)))
    counts = Counter(note.string for note in notes_of(score))
    # The closing octave joins the last string rather than starting a third.
    assert counts == Counter({2: 7, 3: 8})
    assert places_of(score)[:7] == [(2, 0), (2, 2), (2, 4), (2, 5), (2, 7), (2, 9), (2, 11)]


def test_single_string_stays_on_one_string() -> None:
    # String 2 is the open A1 the exercise starts on, so every fret is the
    # degree's distance above the root.
    score = generate(BASS6, params(traversal="single_string", string_set=(2,)))
    assert {note.string for note in notes_of(score)} == {2}
    assert [note.fret for note in notes_of(score)] == [pitch - 33 for pitch in IONIAN_A2]


@pytest.mark.parametrize(
    ("traversal", "string_set"),
    [
        ("positional", (0, 1, 2, 3)),
        ("three_note_per_string", (0, 1, 2, 3, 4)),
        ("octave_per_string", (2, 3)),
        ("single_string", (2,)),
    ],
)
def test_a_degree_keeps_its_place_however_often_the_pattern_visits_it(
    traversal: str,
    string_set: tuple[int, ...],
) -> None:
    # `groups_of_3` plays every inner degree three times. A traversal decides
    # where a degree lives, so all three must land in the same place — a scale
    # that moved under the player's hand mid-figure is a different exercise.
    score = generate(
        BASS6,
        params(traversal=traversal, string_set=string_set, pattern="groups_of_3"),
    )
    seen: dict[int, tuple[int, int]] = {}
    for note in notes_of(score):
        assert seen.setdefault(note.pitch, (note.string, note.fret)) == (note.string, note.fret)
    assert_central_invariant(score)


# --------------------------------------------------------------------------
# The sweeps (spec §14: families are tested over a wide parameter sweep)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("root", range(24, 36))
@pytest.mark.parametrize("scale_type", sorted(theory.SCALES))
def test_invariant_holds_across_every_root_and_scale(root: int, scale_type: str) -> None:
    score = generate(BASS6, params(root=root, scale_type=scale_type))
    assert_central_invariant(score)
    assert_spelling_sounds_correctly(score)
    assert score.key == theory.Key(root % 12, scale_type)
    assert len(score.voice) == len(theory.scale_pitches(root, scale_type, 2))
    assert {note.string for note in notes_of(score)} <= {0, 1, 2, 3}


@pytest.mark.parametrize(("pattern", "direction"), list(product(PATTERNS, DIRECTIONS)))
def test_invariant_holds_across_patterns_and_directions(pattern: str, direction: str) -> None:
    score = generate(BASS6, params(pattern=pattern, direction=direction))
    assert_central_invariant(score)
    assert_spelling_sounds_correctly(score)


@pytest.mark.parametrize("profile_name", sorted(PROFILES))
def test_invariant_holds_across_the_profiles(profile_name: str) -> None:
    profile = PROFILES[profile_name]
    # bass4 starts on E1 and has no low B, so the same box sits on strings 0-3
    # of whatever the profile provides.
    spec = params(root=33, string_set=tuple(range(min(4, len(profile.tuning)))))
    assert_central_invariant(generate(profile, spec))


@pytest.mark.parametrize("scale_type", sorted(theory.SCALES))
def test_three_note_per_string_realizes_or_names_what_it_cannot(scale_type: str) -> None:
    # Three notes per string fixes the note count at 3 x len(string_set), so a
    # scale whose two-octave cycle is not a multiple of three cannot be laid
    # out at all. §9 resamples that draw; §13 forbids truncating the cycle to
    # fit, so the family raises and says which axes disagreed.
    degrees = len(theory.scale_pitches(33, scale_type, 2))
    spec = params(
        scale_type=scale_type,
        traversal="three_note_per_string",
        string_set=tuple(range(degrees // 3)),
    )
    if degrees % 3:
        with pytest.raises(ValueError, match=r"cannot all be satisfied"):
            generate(BASS6, spec)
        return
    score = generate(BASS6, spec)
    assert_central_invariant(score)
    assert set(Counter(note.string for note in notes_of(score)).values()) == {3}


# --------------------------------------------------------------------------
# Unrealizable specifications raise, naming what could not be satisfied (§13)
# --------------------------------------------------------------------------


def test_a_missing_axis_names_the_axis_and_the_family_s_axes() -> None:
    spec = params()
    del spec["pattern"]
    with pytest.raises(ValueError, match=r"parameter 'pattern' is required.*'scale_type'"):
        generate(BASS6, spec)


def test_an_unknown_identifier_lists_the_accepted_values() -> None:
    with pytest.raises(ValueError, match=r"unknown scale_type 'lydian_b9'.*altered"):
        generate(BASS6, params(scale_type="lydian_b9"))


def test_a_non_string_identifier_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"unknown direction 3"):
        generate(BASS6, params(direction=3))


def test_a_traversal_this_family_cannot_realize_is_rejected() -> None:
    # `across_strings` is a registry identifier, but it belongs to `arpeggios`:
    # one axis, and each family validates the subset it can realize (§13).
    with pytest.raises(ValueError, match=r"traversal 'across_strings'.*scales realizes"):
        generate(BASS6, params(traversal="across_strings"))


def test_a_pattern_this_family_cannot_realize_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"pattern 'broken'.*scales realizes"):
        generate(BASS6, params(pattern="broken"))


def test_a_non_integer_range_axis_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"root must be an integer, got '33'"):
        generate(BASS6, params(root="33"))


def test_a_boolean_is_not_an_integer() -> None:
    with pytest.raises(ValueError, match=r"range_octaves must be an integer, got True"):
        generate(BASS6, params(range_octaves=True))


@pytest.mark.parametrize("octaves", [0, 4, -1])
def test_range_octaves_is_one_two_or_three(octaves: int) -> None:
    with pytest.raises(ValueError, match=r"range_octaves must be one of \[1, 2, 3\]"):
        generate(BASS6, params(range_octaves=octaves))


def test_a_string_set_must_be_a_sequence_of_strings() -> None:
    with pytest.raises(ValueError, match=r"string_set must be a non-empty sequence"):
        generate(BASS6, params(string_set=2))


def test_an_empty_string_set_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"string_set must be a non-empty sequence"):
        generate(BASS6, params(string_set=()))


def test_a_string_set_holds_integers() -> None:
    with pytest.raises(ValueError, match=r"string_set must hold integer string indices"):
        generate(BASS6, params(string_set=(0, "1")))


@pytest.mark.parametrize("string_set", [(2, 1, 0), (0, 1, 1)])
def test_a_string_set_is_ascending_and_never_re_sorted(string_set: tuple[int, ...]) -> None:
    # Re-sorting or de-duplicating silently would engrave a different string
    # set from the one the selector drew (§13's stance on tunings).
    with pytest.raises(ValueError, match=r"string_set .* must be strictly ascending"):
        generate(BASS6, params(string_set=string_set))


def test_a_string_set_off_the_instrument_raises() -> None:
    with pytest.raises(ValueError, match=r"string_set .* is off profile 'bass4'"):
        generate(PROFILES["bass4"], params(string_set=(0, 1, 2, 3, 4)))


def test_a_negative_string_index_raises() -> None:
    with pytest.raises(ValueError, match=r"string_set .* is off profile 'bass6'"):
        generate(BASS6, params(string_set=(-1, 0)))


def test_a_degree_no_string_in_the_set_can_reach_raises() -> None:
    # A1 is fifteen semitones below the open C string, so a positional
    # traversal confined to it has nowhere to put the root.
    with pytest.raises(ValueError, match=r"pitch 33 is unreachable on strings \[5\]"):
        generate(BASS6, params(string_set=(5,)))


def test_three_note_per_string_needs_one_string_per_group() -> None:
    with pytest.raises(ValueError, match=r"three_note_per_string.*cannot all be satisfied"):
        generate(BASS6, params(traversal="three_note_per_string", string_set=(0, 1, 2, 3)))


def test_octave_per_string_needs_one_string_per_octave() -> None:
    with pytest.raises(ValueError, match=r"octave_per_string.*cannot all be satisfied"):
        generate(BASS6, params(traversal="octave_per_string", string_set=(0, 1, 2)))


def test_single_string_contradicts_a_wider_string_set() -> None:
    with pytest.raises(ValueError, match=r"single_string.*cannot all be satisfied"):
        generate(BASS6, params(traversal="single_string", string_set=(0, 1)))


def test_running_past_the_last_fret_raises() -> None:
    # Three octaves from the open A string runs out of neck one degree past
    # the top fret, and the cycle is never truncated to fit (spec §7).
    spec = params(traversal="single_string", string_set=(2,), range_octaves=3)
    with pytest.raises(ValueError, match=r"fret 26 on string \d+ of profile 'bass6'"):
        generate(BASS6, spec)


def test_a_degree_below_the_open_string_raises() -> None:
    # The lowest degree is below the open G string, so the first group of a
    # three-notes-per-string layout would need a negative fret.
    spec = params(
        root=33,
        traversal="three_note_per_string",
        string_set=(4, 5),
        range_octaves=1,
        scale_type="major_pentatonic",
    )
    with pytest.raises(ValueError, match=r"fret -10 on string \d+ of profile 'bass6'"):
        generate(BASS6, spec)
