"""Tests for the `intervals` family (spec §7).

The shape follows `test_arpeggios.py`, because every family makes the same
promise and §14 tests them the same way: one complete cycle, the central
invariant, the key the notes are spelled against, the exact parameters
travelling inside the Score, a family-declared tempo, and a wide parameter
sweep over the axes.

What is specific to this family is the *string* assertions. §7 puts `intervals`
in the tool because tablature makes string topology expressible and these
exercises cannot be described by pitch alone — which is the whole justification
for modelling the fretboard in the core rather than treating position as a
rendering detail. A test suite that only checked pitches would pass on an
`intervals` family that ignored `string_skip` entirely, and the exercise would
be a plausible-looking sheet that is not the one that was asked for (§13). So
the topology group below asserts which strings each pair lands on, that the
distance between them is exactly `string_skip + 1`, and that a specification
that cannot be placed at that distance *raises* rather than quietly settling
for an adjacent string.

The `context` group is the second half of the same argument. A diatonic third
is three semitones on some degrees and four on others; a chromatic third is
always four. Asserting both is what proves the axis is realized rather than
assumed.
"""

from __future__ import annotations

from fractions import Fraction
from itertools import product
from typing import TYPE_CHECKING

import pytest
from conftest import assert_central_invariant, assert_spelling_sounds_correctly, notes_of

from melete import theory
from melete.families.intervals import (
    DEFAULT_TEMPO_RANGE,
    INSTRUCTION,
    INTERVAL_NAMES,
)
from melete.families.intervals import generate as _generate
from melete.instrument import PROFILES
from melete.layout import Lever

if TYPE_CHECKING:
    from collections.abc import Mapping

    from melete.instrument import InstrumentProfile
    from melete.score import Score


def generate(profile: InstrumentProfile, params: Mapping[str, object]) -> Score:
    """Unpack the family's `(Score, LayoutHints)`; these tests assert on the Score.

    §4.2 widened every family to return its layout hints alongside the Score.
    The hint contract is covered in `test_registry`; here the Score is the
    subject, so a single wrapper unpacks it rather than every call site.
    """
    score, _hints = _generate(profile, params)
    return score


BASS6 = PROFILES["bass6"]

#: The four lowest strings of a six-string bass: B E A D.
STRING_SET: tuple[int, ...] = (0, 1, 2, 3)

#: A1 = 33, the same root `test_scales.py` and `test_arpeggios.py` use, so all
#: three families' worked examples sit in the same key.
PARAMS: dict[str, object] = {
    "interval": 3,
    "context": "diatonic",
    "root": 33,
    "scale_type": "ionian",
    "string_skip": "0",
    "string_set": STRING_SET,
    "direction": "up",
    "pattern": "ascending_pairs",
}

#: One octave of A Ionian, closing on the octave: the lower note of each pair.
A_IONIAN = [33, 35, 37, 38, 40, 42, 44, 45]

#: The diatonic third above each of them — a scale degree away, not a fixed
#: semitone count.
A_IONIAN_THIRDS = [37, 38, 40, 42, 44, 45, 47, 49]

INTERVALS = sorted(INTERVAL_NAMES)
SKIPS = ("0", "1", "2")
CONTEXTS = ("diatonic", "chromatic")
PATTERNS = ("ascending_pairs", "descending_pairs", "alternating")
DIRECTIONS = ("up", "down", "up_down")


def params(**overrides: object) -> dict[str, object]:
    """`PARAMS` with one or more axes replaced."""
    return {**PARAMS, **overrides}


def pitches_of(score: Score) -> list[int]:
    """The pitch of every note, in playing order."""
    return [note.pitch for note in notes_of(score)]


def strings_of(score: Score) -> list[int]:
    """The string index of every note, in playing order."""
    return [note.string for note in notes_of(score)]


def places_of(score: Score) -> list[tuple[int, int]]:
    """The (string, fret) of every note, in playing order."""
    return [(note.string, note.fret) for note in notes_of(score)]


def steps_of(score: Score) -> list[int]:
    """The string distance between every consecutive pair of notes."""
    played = strings_of(score)
    return [abs(a - b) for a, b in zip(played, played[1:], strict=False)]


# --------------------------------------------------------------------------
# The family contract
# --------------------------------------------------------------------------


def test_generates_one_complete_cycle() -> None:
    # Eight scale degrees including the closing octave, each with its partner
    # (spec §7: one complete cycle of the pattern, never truncated).
    assert len(generate(BASS6, PARAMS).voice) == 16


def test_obeys_the_central_invariant() -> None:
    assert_central_invariant(generate(BASS6, PARAMS))


def test_spells_every_note_as_it_sounds() -> None:
    assert_spelling_sounds_correctly(generate(BASS6, PARAMS))


def test_params_travel_inside_the_score() -> None:
    assert generate(BASS6, PARAMS).params == PARAMS


def test_default_tempo_range_is_declared_by_the_family() -> None:
    # Spec §7: the family declares the range and the selector never samples it.
    # String crossing costs accuracy at speed, so the range starts lower than
    # the scales' — but not by as much as the first table assumed.
    assert DEFAULT_TEMPO_RANGE == (70, 130)
    assert generate(BASS6, PARAMS).tempo_range == (70, 130)


def test_the_notes_are_plain_and_unaccented() -> None:
    # §8's rhythm modifier owns subdivision and accents; this family states the
    # un-modified reading and nothing more.
    score = generate(BASS6, PARAMS)
    assert score.time_signature == (4, 4)
    assert {(note.duration, note.accent) for note in notes_of(score)} == {(Fraction(1, 4), False)}


def test_the_fingering_is_left_unspecified() -> None:
    # §6 makes `finger` first class because in *chromatic* work the fingering is
    # the exercise. Here the string pair is, and prescribing a finger would
    # engrave a fingering the caller never asked for.
    assert {note.finger for note in notes_of(generate(BASS6, PARAMS))} == {None}


def test_the_score_carries_a_title_and_a_focus_cue() -> None:
    score = generate(BASS6, PARAMS)
    assert score.title == "A Ionian thirds, adjacent strings, ascending pairs, ascending"
    assert score.instruction == INSTRUCTION


def test_a_chromatic_title_names_the_context_rather_than_a_scale() -> None:
    score = generate(BASS6, params(context="chromatic", string_skip="1", direction="down"))
    assert score.title == "A chromatic thirds, skipping one string, ascending pairs, descending"


def test_generate_is_pure() -> None:
    given = params()
    first, second = generate(BASS6, given), generate(BASS6, given)
    assert first == second
    assert given == PARAMS

    # The Score owns its parameters: a caller reusing the dictionary it passed
    # in must not be able to rewrite the record of what was generated.
    first.params["interval"] = 99
    assert given["interval"] == 3


# --------------------------------------------------------------------------
# The key, which is a branch on `context` (spec §10a)
# --------------------------------------------------------------------------


def test_a_diatonic_context_is_spelled_against_its_root_and_scale() -> None:
    # Without this the Score still engraves — spelled by the tier 3 direction
    # rule, silently, so notation and tablature disagree with nothing raising.
    # That is the defect §10a exists to fix, and no other assertion catches it:
    # G♭ sounds pitch class 6 exactly as F♯ does.
    assert generate(BASS6, PARAMS).key == theory.Key(9, "ionian")


def test_a_chromatic_context_has_no_key() -> None:
    # `None` is the answer, not an omission: a chromatic interval sequence
    # asserts no tonal center, so it is tier 3 by definition (§10a) and takes
    # sharps ascending, flats descending.
    assert generate(BASS6, params(context="chromatic")).key is None


def test_the_tonic_is_a_pitch_class_and_not_the_root_pitch() -> None:
    # A1 and A2 are the same key. `root` stays an absolute pitch everywhere
    # else (§10a), which is exactly why the reduction has to happen here.
    for root, tonic in ((33, 9), (45, 9), (30, 6)):
        assert generate(BASS6, params(root=root)).key == theory.Key(tonic, "ionian")


def test_the_key_changes_how_the_notes_are_spelled() -> None:
    # The key is load-bearing rather than decorative: B♭ Ionian writes B♭ and
    # E♭, while the same pitches with no key take the ascending sharps A♯ and
    # D♯. If this passes with `key=None` the field is doing nothing.
    score = generate(BASS6, params(root=34))
    played = pitches_of(score)
    assert theory.spell(score.key, played) != theory.spell(None, played)


@pytest.mark.parametrize("scale_type", ["ionian", "dorian", "aeolian", "minor_pentatonic"])
def test_every_diatonic_scale_is_spelled_against_itself(scale_type: str) -> None:
    score = generate(BASS6, params(scale_type=scale_type, interval=5))
    assert score.key == theory.Key(9, scale_type)
    assert_spelling_sounds_correctly(score)


# --------------------------------------------------------------------------
# `context`: a diatonic interval bends to the scale, a chromatic one does not
# --------------------------------------------------------------------------


def test_diatonic_thirds_are_three_or_four_semitones() -> None:
    played = pitches_of(generate(BASS6, PARAMS))
    for lower, upper in zip(played[::2], played[1::2], strict=True):
        assert upper - lower in (3, 4)


def test_chromatic_context_makes_every_interval_exact() -> None:
    played = pitches_of(generate(BASS6, params(context="chromatic")))
    for lower, upper in zip(played[::2], played[1::2], strict=True):
        assert upper - lower == 4


def test_the_context_axis_is_realized_and_not_assumed() -> None:
    # The two contexts must actually differ: a diatonic third is minor on some
    # degrees and major on others, and a chromatic third is major everywhere.
    diatonic = pitches_of(generate(BASS6, PARAMS))
    chromatic = pitches_of(generate(BASS6, params(context="chromatic")))
    assert {b - a for a, b in zip(diatonic[::2], diatonic[1::2], strict=True)} == {3, 4}
    assert {b - a for a, b in zip(chromatic[::2], chromatic[1::2], strict=True)} == {4}


def test_the_diatonic_pairs_are_degrees_of_the_scale() -> None:
    played = pitches_of(generate(BASS6, PARAMS))
    assert played[::2] == A_IONIAN
    assert played[1::2] == A_IONIAN_THIRDS


def test_the_chromatic_lower_notes_walk_by_semitone_through_one_octave() -> None:
    played = pitches_of(generate(BASS6, params(context="chromatic", interval=5)))
    assert played[::2] == list(range(33, 46))
    assert played[1::2] == list(range(40, 53))


@pytest.mark.parametrize(
    ("interval", "semitones"),
    [(2, 2), (3, 4), (4, 5), (5, 7), (6, 9), (7, 11), (8, 12), (9, 14), (10, 16)],
)
def test_a_chromatic_interval_takes_its_major_or_perfect_size(
    interval: int, semitones: int
) -> None:
    # A chromatic context has no scale to bend the interval, so every number is
    # its major (2nd, 3rd, 6th, 7th and their compounds) or perfect size.
    played = pitches_of(generate(BASS6, params(context="chromatic", interval=interval)))
    assert {b - a for a, b in zip(played[::2], played[1::2], strict=True)} == {semitones}


def test_a_diatonic_second_is_a_scale_step_and_not_always_a_tone() -> None:
    played = pitches_of(generate(BASS6, params(interval=2)))
    assert {b - a for a, b in zip(played[::2], played[1::2], strict=True)} == {1, 2}


def test_a_pentatonic_octave_has_fewer_pairs_than_a_seven_note_one() -> None:
    # The cycle is one octave of the scale's own degrees, so a five-note scale
    # is six pairs and a seven-note scale is eight.
    assert len(generate(BASS6, params(scale_type="minor_pentatonic")).voice) == 12
    assert len(generate(BASS6, PARAMS).voice) == 16


# --------------------------------------------------------------------------
# String topology: the reason this family exists (spec §7, decision #4)
# --------------------------------------------------------------------------


def test_adjacent_skip_zero_uses_neighbouring_strings() -> None:
    score = generate(BASS6, PARAMS)
    assert all(step <= 1 for step in steps_of(score))
    assert set(strings_of(score)) == {0, 1}


def test_string_skip_1_never_uses_adjacent_strings() -> None:
    score = generate(BASS6, params(string_skip="1"))
    assert all(step != 1 for step in steps_of(score))
    assert set(strings_of(score)) == {0, 2}


def test_string_skip_2_leaves_two_strings_between() -> None:
    # A third across three strings is fifteen semitones of string for four
    # semitones of interval, which does not fit from this root — so the skip-2
    # example is a fifth. `test_string_skip_is_a_hard_constraint` covers the
    # third, which raises rather than settling for a nearer string.
    score = generate(BASS6, params(string_skip="2", interval=5))
    assert any(step >= 3 for step in steps_of(score))
    assert set(strings_of(score)) == {0, 3}


@pytest.mark.parametrize(("skip", "interval"), [("0", 3), ("1", 3), ("2", 5)])
def test_the_two_notes_of_a_pair_are_exactly_skip_plus_one_strings_apart(
    skip: str, interval: int
) -> None:
    # The axis is a distance between the notes of one pair, and it is realized
    # exactly: `string_skip` 1 means one string is skipped over, not "at least".
    score = generate(BASS6, params(string_skip=skip, interval=interval))
    played = strings_of(score)
    for lower, upper in zip(played[::2], played[1::2], strict=True):
        assert abs(upper - lower) == int(skip) + 1


def test_the_lower_note_of_each_pair_sits_on_the_lower_string() -> None:
    places = places_of(generate(BASS6, PARAMS))
    for lower, upper in zip(places[::2], places[1::2], strict=True):
        assert lower[0] < upper[0]


def test_the_whole_exercise_stays_on_one_string_pair() -> None:
    # The pair of strings is chosen once and held, which is what makes the
    # exercise a string-skipping drill rather than a scale that happens to
    # cross strings. Every pair therefore sits at the same distance.
    for skip, interval in (("0", 3), ("1", 3), ("2", 5)):
        score = generate(BASS6, params(string_skip=skip, interval=interval))
        assert len(set(strings_of(score))) == 2


def test_the_string_pair_is_drawn_from_the_declared_string_set() -> None:
    score = generate(BASS6, params(string_set=(2, 3, 4, 5), interval=5))
    assert set(strings_of(score)) <= {2, 3, 4, 5}


def test_the_lowest_workable_string_pair_wins() -> None:
    # Deterministic all the way down, which is what reproducibility from a
    # session log needs: of the pairs at the required distance, the lowest one
    # that can carry every note is taken.
    assert places_of(generate(BASS6, PARAMS))[:4] == [(0, 10), (1, 9), (0, 12), (1, 10)]


def test_a_higher_string_pair_is_taken_when_the_lowest_cannot_carry_the_notes() -> None:
    # A tenth from A1 runs off the top of the E string, so the pair moves up
    # rather than the exercise being clamped into something engravable.
    score = generate(BASS6, params(interval=10))
    assert set(strings_of(score)) == {2, 3}


# --------------------------------------------------------------------------
# `pattern` orders the notes inside a pair; `direction` orders the pairs
# --------------------------------------------------------------------------


def interleaved(first: list[int], second: list[int]) -> list[int]:
    """`first` and `second` played one note each, pair by pair."""
    return [pitch for pair in zip(first, second, strict=True) for pitch in pair]


def test_ascending_pairs_play_the_lower_note_first() -> None:
    assert pitches_of(generate(BASS6, PARAMS)) == interleaved(A_IONIAN, A_IONIAN_THIRDS)


def test_descending_pairs_invert_the_pair_order() -> None:
    up = generate(BASS6, PARAMS)
    down = generate(BASS6, params(pattern="descending_pairs"))
    assert pitches_of(down) != pitches_of(up)
    assert set(pitches_of(down)) == set(pitches_of(up))
    assert pitches_of(down) == interleaved(A_IONIAN_THIRDS, A_IONIAN)


def test_alternating_turns_every_other_pair_around() -> None:
    played = pitches_of(generate(BASS6, params(pattern="alternating")))
    assert played[:4] == [A_IONIAN[0], A_IONIAN_THIRDS[0], A_IONIAN_THIRDS[1], A_IONIAN[1]]
    assert played[4:8] == [A_IONIAN[2], A_IONIAN_THIRDS[2], A_IONIAN_THIRDS[3], A_IONIAN[3]]


def test_direction_down_reverses_the_pairs_and_not_the_pattern() -> None:
    # `direction` orders the pairs and `pattern` orders the two notes inside
    # one. Reversing the whole note sequence instead would turn descending
    # pairs into ascending ones while the title still said "descending pairs"
    # — a sheet that is not the exercise it names (§13).
    played = pitches_of(generate(BASS6, params(pattern="descending_pairs", direction="down")))
    assert played == interleaved(A_IONIAN_THIRDS[::-1], A_IONIAN[::-1])


def test_up_down_returns_without_replaying_the_turnaround_pair() -> None:
    score = generate(BASS6, params(direction="up_down"))
    assert len(score.voice) == 30
    played = pitches_of(score)
    assert played[:16] == pitches_of(generate(BASS6, PARAMS))
    assert played[-2:] == [A_IONIAN[0], A_IONIAN_THIRDS[0]]


def test_a_direction_reorders_without_changing_the_content() -> None:
    up = generate(BASS6, PARAMS)
    for direction in DIRECTIONS:
        other = generate(BASS6, params(direction=direction))
        assert set(pitches_of(other)) == set(pitches_of(up))


def test_a_pattern_reorders_without_changing_the_content() -> None:
    reference = generate(BASS6, PARAMS)
    for pattern in PATTERNS:
        other = generate(BASS6, params(pattern=pattern))
        assert sorted(pitches_of(other)) == sorted(pitches_of(reference))
        assert places_of(other) != [] and set(places_of(other)) == set(places_of(reference))


# --------------------------------------------------------------------------
# Unrealizable specifications raise, naming what could not be satisfied (§13)
# --------------------------------------------------------------------------


def test_string_skip_is_a_hard_constraint_and_never_falls_back() -> None:
    # Four semitones of interval across fifteen semitones of string needs the
    # partner eleven frets *below* the lower note, and A1 does not sit high
    # enough on the B string for that. Quietly moving it to a nearer string
    # would produce a plausible exercise that is not the one requested (§13);
    # §9's validity gate resamples this instead.
    with pytest.raises(ValueError, match=r"no string pair 3 apart within string_set"):
        generate(BASS6, params(string_skip="2"))


def test_a_string_set_with_no_pair_at_the_required_distance_raises() -> None:
    with pytest.raises(ValueError, match=r"string_skip 2 needs two strings 3 apart"):
        generate(BASS6, params(string_set=(0, 1), string_skip="2"))


def test_a_lower_note_off_the_neck_raises() -> None:
    # The lower note is the half that fails here: C6 sits above the last fret
    # of every string a six-string bass has.
    with pytest.raises(ValueError, match=r"no string pair 1 apart within string_set"):
        generate(BASS6, params(root=84))


def test_a_missing_axis_names_the_axis_and_the_family_s_axes() -> None:
    spec = params()
    del spec["string_skip"]
    with pytest.raises(ValueError, match=r"parameter 'string_skip' is required.*'interval'"):
        generate(BASS6, spec)


def test_a_diatonic_context_requires_a_scale_type() -> None:
    spec = params()
    del spec["scale_type"]
    with pytest.raises(ValueError, match=r"parameter 'scale_type' is required"):
        generate(BASS6, spec)


def test_a_chromatic_context_does_not_need_a_scale_type() -> None:
    # Reading one would make two specifications that differ only in an unused
    # axis engrave the same exercise, which §9's coverage accounting could not
    # tell apart.
    spec = params(context="chromatic")
    del spec["scale_type"]
    assert generate(BASS6, spec).key is None


def test_an_unknown_identifier_lists_the_accepted_values() -> None:
    with pytest.raises(ValueError, match=r"unknown context 'modal'.*diatonic"):
        generate(BASS6, params(context="modal"))


def test_an_integer_string_skip_is_not_an_identifier() -> None:
    # §7 writes the column as 0, 1 and 2, but `vocabulary` carries them as
    # identifiers like every other axis so one lookup path serves them all.
    with pytest.raises(ValueError, match=r"unknown string_skip 1"):
        generate(BASS6, params(string_skip=1))


@pytest.mark.parametrize("interval", [1, 0, 11, -3])
def test_an_interval_outside_the_second_to_the_tenth_is_rejected(interval: int) -> None:
    with pytest.raises(ValueError, match=r"interval must be one of \[2, 3, 4, 5, 6, 7, 8, 9, 10\]"):
        generate(BASS6, params(interval=interval))


def test_a_non_integer_range_axis_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"root must be an integer, got '33'"):
        generate(BASS6, params(root="33"))


def test_a_pattern_this_family_cannot_realize_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"pattern 'thirds'.*intervals realizes"):
        generate(BASS6, params(pattern="thirds"))


def test_a_string_set_off_the_instrument_raises() -> None:
    with pytest.raises(ValueError, match=r"string_set .* is off profile 'bass4'"):
        generate(PROFILES["bass4"], params(string_set=(0, 1, 2, 3, 4)))


def test_a_string_set_is_ascending_and_never_re_sorted() -> None:
    with pytest.raises(ValueError, match=r"string_set .* must be strictly ascending"):
        generate(BASS6, params(string_set=(3, 2, 1, 0)))


# --------------------------------------------------------------------------
# The sweeps (spec §14: families are tested over a wide parameter sweep)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("interval", INTERVALS)
@pytest.mark.parametrize("string_skip", SKIPS)
@pytest.mark.parametrize("context", CONTEXTS)
def test_invariant_holds_across_intervals_skips_and_contexts(
    interval: int, string_skip: str, context: str
) -> None:
    spec = params(interval=interval, string_skip=string_skip, context=context)
    try:
        score = generate(BASS6, spec)
    except ValueError as error:
        # Over-constrained: §9 resamples this rather than clamping it, so an
        # unrealizable draw is an outcome of the sweep and not a failure. What
        # is asserted is that it named what could not be satisfied (§13).
        assert "string_skip" in str(error) or "string pair" in str(error)
        return

    assert_central_invariant(score)
    assert_spelling_sounds_correctly(score)
    played = strings_of(score)
    for lower, upper in zip(played[::2], played[1::2], strict=True):
        assert abs(upper - lower) == int(string_skip) + 1


@pytest.mark.parametrize(("pattern", "direction"), list(product(PATTERNS, DIRECTIONS)))
def test_invariant_holds_across_patterns_and_directions(pattern: str, direction: str) -> None:
    score = generate(BASS6, params(pattern=pattern, direction=direction))
    assert_central_invariant(score)
    assert_spelling_sounds_correctly(score)
    assert set(pitches_of(score)) == set(A_IONIAN) | set(A_IONIAN_THIRDS)


@pytest.mark.parametrize("scale_type", sorted(theory.SCALES))
def test_invariant_holds_across_every_scale(scale_type: str) -> None:
    score = generate(BASS6, params(scale_type=scale_type, interval=5))
    assert_central_invariant(score)
    assert_spelling_sounds_correctly(score)
    assert score.key == theory.Key(9, scale_type)


@pytest.mark.parametrize("profile_name", sorted(PROFILES))
def test_invariant_holds_across_the_profiles(profile_name: str) -> None:
    profile = PROFILES[profile_name]
    spec = params(string_set=tuple(range(min(4, len(profile.tuning)))))
    assert_central_invariant(generate(profile, spec))


def test_layout_hints_report_the_pair_as_the_cell() -> None:
    # §4.2's cell here is the pair: two notes sounded together to a beat.
    _score, hints = _generate(BASS6, PARAMS)
    assert hints.cell == 2


def test_a_one_directional_exercise_has_no_seam_and_no_apex_levers() -> None:
    # `up` (and `down`) never turn around, so only the trailing add/drop apply.
    _score, hints = _generate(BASS6, PARAMS)
    assert hints.seam is None
    assert set(hints.levers) == {Lever.ADD_ONE, Lever.DROP_ONE}


def test_an_up_down_exercise_names_its_apex_seam_and_offers_apex_levers() -> None:
    # The pairs turn around on the top pair of the ascending pass, played once,
    # so the seam is that pair's last note — the end of the `len(pairs)` pairs
    # the pass sounds — and the apex levers become legal (§4.6).
    _score, hints = _generate(BASS6, params(direction="up_down"))
    assert hints.seam == 2 * len(A_IONIAN) - 1
    assert {Lever.APEX_REPEAT, Lever.APEX_OMIT} <= set(hints.levers)
