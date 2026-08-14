"""Tests for the `chromatic` family (spec §7).

The first five are the family contract every later family repeats: one
complete cycle, the central invariant, fingering carried on the notes, the
exact parameters travelling inside the Score, and a family-declared tempo.

The rest fall into two halves. The sweeps assert the central invariant across
every profile and a wide draw of parameters, which is §14's stated approach for
families. The error tests assert the other half of the contract: a
specification that cannot be realized raises and names what it could not
satisfy, because §9 resamples that case and §13 forbids quietly clamping it
into something engravable.
"""

from __future__ import annotations

from fractions import Fraction
from typing import TYPE_CHECKING

import pytest
from conftest import assert_central_invariant, assert_spelling_sounds_correctly, notes_of

from melete.families.chromatic import DEFAULT_TEMPO_RANGE, INSTRUCTION
from melete.families.chromatic import generate as _generate
from melete.instrument import PROFILES
from melete.layout import Lever, plan_voice

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


PARAMS: dict[str, object] = {
    "permutation": (1, 2, 3, 4),
    "start_string": 0,
    "start_fret": 5,
    "string_traversal": "adjacent",
    "shift": "none",
    "span": 4,
}

BASS6 = PROFILES["bass6"]

PERMUTATIONS = [
    (1, 2, 3, 4),
    (1, 2, 4, 3),
    (1, 3, 2, 4),
    (1, 3, 4, 2),
    (1, 4, 2, 3),
    (1, 4, 3, 2),
    (2, 1, 3, 4),
    (2, 1, 4, 3),
    (2, 3, 1, 4),
    (2, 3, 4, 1),
    (2, 4, 1, 3),
    (2, 4, 3, 1),
    (3, 1, 2, 4),
    (3, 1, 4, 2),
    (3, 2, 1, 4),
    (3, 2, 4, 1),
    (3, 4, 1, 2),
    (3, 4, 2, 1),
    (4, 1, 2, 3),
    (4, 1, 3, 2),
    (4, 2, 1, 3),
    (4, 2, 3, 1),
    (4, 3, 1, 2),
    (4, 3, 2, 1),
]


def params(**overrides: object) -> dict[str, object]:
    """`PARAMS` with one or more axes replaced."""
    return {**PARAMS, **overrides}


def strings_of(score: Score) -> list[int]:
    """The string index of every note, in playing order."""
    return [note.string for note in notes_of(score)]


# --------------------------------------------------------------------------
# The family contract
# --------------------------------------------------------------------------


def test_generates_one_complete_cycle() -> None:
    # span 4 strings, up-and-down: there_and_back walks 7 string-groups
    # (4 out, 3 back) x 4 fingers = 28 notes, no truncation (spec §7, §5).
    assert len(generate(BASS6, PARAMS).voice) == 28


def test_obeys_the_central_invariant() -> None:
    assert_central_invariant(generate(BASS6, PARAMS))


def test_spells_every_note_as_it_sounds() -> None:
    assert_spelling_sounds_correctly(generate(BASS6, PARAMS))


def test_a_chromatic_exercise_has_no_key() -> None:
    # §10a: `None` is this family's answer, not a field it forgot. Permutation
    # work asserts no tonal center, so it is tier 3 by definition and spells by
    # direction.
    assert generate(BASS6, PARAMS).key is None


def test_fingering_is_first_class() -> None:
    score = generate(BASS6, PARAMS)
    assert [note.finger for note in notes_of(score)[:4]] == [1, 2, 3, 4]


def test_every_group_plays_the_whole_permutation() -> None:
    fingers = [note.finger for note in notes_of(generate(BASS6, params(permutation=(3, 1, 4, 2))))]
    # span 4, up-and-down: 7 string-groups, each the whole permutation as written.
    assert fingers == [3, 1, 4, 2] * 7


def test_params_travel_inside_the_score() -> None:
    assert generate(BASS6, PARAMS).params == PARAMS


def test_default_tempo_range_is_declared_by_the_family() -> None:
    # Spec §7: the family declares the range and the selector never samples it.
    assert DEFAULT_TEMPO_RANGE == (60, 120)
    assert generate(BASS6, PARAMS).tempo_range == (60, 120)


def test_the_notes_are_plain_and_unaccented() -> None:
    # §8's rhythm modifier owns subdivision and accents; this family states the
    # un-modified reading and nothing more.
    score = generate(BASS6, PARAMS)
    assert score.time_signature == (4, 4)
    assert {(note.duration, note.accent) for note in notes_of(score)} == {(Fraction(1, 4), False)}


def test_the_score_carries_a_title_and_a_focus_cue() -> None:
    score = generate(BASS6, params(permutation=(2, 4, 1, 3)))
    assert "2-4-1-3" in score.title
    assert "adjacent strings" in score.title
    # The journey is always up-and-down, so the title states no direction word
    # (spec §5, decision 1) — an "ascending"/"descending" cue would name a
    # variation the family no longer produces.
    assert "ascending" not in score.title
    assert "descending" not in score.title
    assert score.instruction == INSTRUCTION


def test_the_title_names_a_shift_only_when_there_is_one() -> None:
    assert "per cycle" not in generate(BASS6, PARAMS).title
    assert "up one fret per cycle" in generate(BASS6, params(shift="fret_per_cycle")).title


def test_generate_is_pure() -> None:
    given = params()
    first, second = generate(BASS6, given), generate(BASS6, given)
    assert first == second
    assert given == PARAMS

    # The Score owns its parameters: a caller reusing the dictionary it passed
    # in must not be able to rewrite the record of what was generated.
    first.params["start_fret"] = 99
    assert given["start_fret"] == 5


# --------------------------------------------------------------------------
# The axes
# --------------------------------------------------------------------------


def test_chromatic_covers_the_full_span_and_returns() -> None:
    # spec §6, defect 1: start on an outer string, traverse the full set to the
    # opposite outer string, turn around and return — always up-and-down.
    spec = {
        "permutation": (3, 1, 4, 2),
        "start_string": 0,
        "start_fret": 5,
        "string_traversal": "adjacent",
        "shift": "none",
        "span": 6,
    }  # no `direction` axis: the journey is always up-and-down
    score = generate(BASS6, spec)
    strings = sorted({note.string for note in notes_of(score)})
    assert strings == list(range(6))  # every string, no gap or repeat-only
    first, last = notes_of(score)[0].string, notes_of(score)[-1].string
    assert first == 0 and last == 0  # outer string out and back


def test_the_journey_climbs_out_and_returns_without_replaying_the_turnaround() -> None:
    # Every journey is up-and-down (spec §5, decision 1): it climbs from the
    # start string to the opposite outer string of the set and returns, without
    # replaying the turnaround string (which would sound the same four notes
    # twice in a row).
    score = generate(BASS6, params(start_string=1, span=3))
    assert strings_of(score) == [1] * 4 + [2] * 4 + [3] * 4 + [2] * 4 + [1] * 4


def test_a_single_string_journey_is_a_single_pass() -> None:
    # The turnaround string is the only string, so there is nothing to return
    # along and the cycle is four notes rather than a repeat of them.
    score = generate(BASS6, params(span=1))
    assert strings_of(score) == [0] * 4


def test_the_permutation_is_played_as_written_in_both_directions() -> None:
    # `direction` is no longer an axis, but the permutation is still played as
    # written on the way down and never reversed: reversing it would alias two
    # specifications onto one exercise, which §9's coverage accounting could not
    # see.
    score = generate(BASS6, params(start_string=3, span=2))
    # span 2 up-and-down walks strings [3, 4, 3] — three groups.
    assert [note.finger for note in notes_of(score)] == [1, 2, 3, 4] * 3


def test_skip_1_traversal_steps_over_a_string() -> None:
    score = generate(BASS6, params(string_traversal="skip_1", span=3))
    assert strings_of(score) == [0] * 4 + [2] * 4 + [4] * 4 + [2] * 4 + [0] * 4


def test_single_string_traversal_stays_on_one_string() -> None:
    score = generate(BASS6, params(string_traversal="single_string", span=1, start_string=2))
    assert strings_of(score) == [2] * 4
    assert [note.fret for note in notes_of(score)] == [5, 6, 7, 8]


def test_shift_none_repeats_the_same_frets_on_every_string() -> None:
    # span 2 up-and-down walks three string-groups [0, 1, 0]; no shift, so the
    # same four frets sound on each.
    frets = [note.fret for note in notes_of(generate(BASS6, params(span=2)))]
    assert frets == [5, 6, 7, 8, 5, 6, 7, 8, 5, 6, 7, 8]


def test_shift_fret_per_cycle_walks_up_one_fret_per_permutation() -> None:
    # The per-cycle shift advances on every group of the whole up-and-down
    # journey, so the diagonal keeps climbing through the descent (spec §6).
    score = generate(BASS6, params(shift="fret_per_cycle", span=3))
    frets = [note.fret for note in notes_of(score)]
    assert frets == [5, 6, 7, 8, 6, 7, 8, 9, 7, 8, 9, 10, 8, 9, 10, 11, 9, 10, 11, 12]


def test_shift_position_per_cycle_moves_a_whole_hand_position() -> None:
    # A position is one finger per fret, so the next cycle starts where the
    # little finger left off plus one.
    # span 2 up-and-down walks three groups; the position shift advances a whole
    # hand position on each, climbing through the descent (spec §6).
    score = generate(BASS6, params(shift="position_per_cycle", span=2))
    frets = [note.fret for note in notes_of(score)]
    assert frets == [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]


def test_the_open_string_is_reachable() -> None:
    score = generate(BASS6, params(start_fret=0, span=1))
    assert [note.fret for note in notes_of(score)] == [0, 1, 2, 3]


# --------------------------------------------------------------------------
# The layout hints the fitter consumes (spec §4.2, §4.6)
# --------------------------------------------------------------------------


def test_every_journey_emits_the_apex_levers_and_a_seam() -> None:
    # The journey is always up-and-down (spec §5, decision 1), so it always
    # turns around on an apex: the cell is the permutation group, the seam is the
    # last note of the ascent (span * cell - 1 = 4 * 4 - 1 = 15), and the apex
    # levers repeat or omit that turnaround cell to reach a whole-bar count.
    _score, hints = _generate(BASS6, PARAMS)
    assert hints.cell == 4
    assert hints.seam == 15
    assert hints.levers == (Lever.APEX_REPEAT, Lever.APEX_OMIT)


def test_all_strings_up_and_down_emits_the_apex_levers_and_seam() -> None:
    # "Chromatic uses all strings" (spec §6) is driven by span = the profile's
    # string count from start_string 0, which the family already realizes via
    # `range(span)` — not an "all" sentinel. bass6 has six strings, so
    # `there_and_back` walks eleven string-groups (6 up, 5 back down).
    spec = params(
        permutation=(1, 2, 4, 3),
        start_string=0,
        string_traversal="adjacent",
        span=6,
    )
    score, hints = _generate(BASS6, spec)

    # 11 string-groups x 4 fingers = 44 notes, the apex played once.
    assert len(score.voice) == 44
    # The permutation group is the cell; the apex is the last note of the
    # ascending half (span * cell - 1 = 6 * 4 - 1); the apex may be repeated or
    # omitted to reach a whole-bar count.
    assert hints.cell == 4
    assert hints.seam == 23
    assert hints.levers == (Lever.APEX_REPEAT, Lever.APEX_OMIT)


def test_all_strings_cycle_fits_two_bars_of_six_four_via_apex_repeat() -> None:
    # 44 notes tiles no sane bar (11 beats is prime), so the fitter repeats the
    # apex cell to 48 = 12 beats and picks the fullest even meter, 6/4 x 2.
    spec = params(
        permutation=(1, 2, 4, 3),
        start_string=0,
        string_traversal="adjacent",
        span=6,
    )
    score, hints = _generate(BASS6, spec)
    fitted, plan = plan_voice(score.voice, hints)
    assert len(fitted) == 48
    assert plan.levers_applied == (Lever.APEX_REPEAT,)
    assert plan.time_signature == (6, 4)
    assert plan.bars == 2


# --------------------------------------------------------------------------
# The sweeps (spec §14: families are tested over a wide parameter sweep)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("profile_name", sorted(PROFILES))
@pytest.mark.parametrize("start_fret", range(13))
def test_invariant_holds_across_the_sweep(profile_name: str, start_fret: int) -> None:
    profile = PROFILES[profile_name]
    span = min(4, len(profile.tuning))
    spec = params(start_fret=start_fret, span=span)
    score = generate(profile, spec)
    assert_central_invariant(score)
    assert_spelling_sounds_correctly(score)
    assert score.key is None
    # up-and-down: there_and_back walks 2*span - 1 string-groups x 4 fingers.
    assert len(score.voice) == 4 * (2 * span - 1)


@pytest.mark.parametrize("permutation", PERMUTATIONS)
def test_invariant_holds_for_every_permutation(permutation: tuple[int, ...]) -> None:
    score = generate(BASS6, params(permutation=permutation))
    assert_central_invariant(score)
    # span 4 up-and-down: 7 string-groups, each the whole permutation as written.
    assert [note.finger for note in notes_of(score)] == list(permutation) * 7


@pytest.mark.parametrize("shift", ["none", "fret_per_cycle", "position_per_cycle"])
def test_invariant_holds_across_shifts(shift: str) -> None:
    # Direction is no longer sampled; every journey is up-and-down (spec §5).
    # span 3 walks 2*3 - 1 = 5 string-groups x 4 fingers = 20 notes.
    score = generate(BASS6, params(shift=shift, start_string=2, span=3))
    assert_central_invariant(score)
    assert_spelling_sounds_correctly(score)
    assert len(score.voice) == 20


@pytest.mark.parametrize(
    ("traversal", "start_string", "span"),
    [("adjacent", 1, 3), ("skip_1", 0, 3), ("single_string", 4, 1)],
)
def test_invariant_holds_across_string_traversals(
    traversal: str,
    start_string: int,
    span: int,
) -> None:
    spec = params(string_traversal=traversal, start_string=start_string, span=span)
    assert_central_invariant(generate(BASS6, spec))


# --------------------------------------------------------------------------
# Unrealizable specifications raise, naming what could not be satisfied (§13)
# --------------------------------------------------------------------------


def test_a_missing_axis_names_the_axis_and_the_family_s_axes() -> None:
    spec = params()
    del spec["shift"]
    with pytest.raises(ValueError, match=r"parameter 'shift' is required.*'permutation'"):
        generate(BASS6, spec)


def test_an_unknown_identifier_lists_the_accepted_values() -> None:
    # An identifier axis names its accepted values when handed one it does not
    # know (§13). `direction` is no longer an axis, so `string_traversal` stands
    # in for the identifier contract.
    with pytest.raises(ValueError, match=r"unknown string_traversal 'both'.*adjacent"):
        generate(BASS6, params(string_traversal="both"))


def test_a_non_string_identifier_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"unknown shift 3"):
        generate(BASS6, params(shift=3))


def test_a_non_integer_range_axis_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"start_fret must be an integer, got '5'"):
        generate(BASS6, params(start_fret="5"))


def test_a_boolean_is_not_an_integer() -> None:
    # `True` is not fret 1, however willingly Python would add it.
    with pytest.raises(ValueError, match=r"span must be an integer, got True"):
        generate(BASS6, params(span=True))


@pytest.mark.parametrize("permutation", [(1, 2, 3), (1, 2, 3, 3), (0, 1, 2, 3), "1234", None])
def test_a_permutation_must_order_all_four_fingers(permutation: object) -> None:
    with pytest.raises(ValueError, match=r"is not an ordering of the fretting fingers"):
        generate(BASS6, params(permutation=permutation))


def test_a_span_must_cover_at_least_one_string() -> None:
    with pytest.raises(ValueError, match=r"span must cover at least one string, got 0"):
        generate(BASS6, params(span=0))


def test_single_string_traversal_contradicts_a_wider_span() -> None:
    with pytest.raises(ValueError, match=r"'single_string' covers one string, so span must be 1"):
        generate(BASS6, params(string_traversal="single_string", span=3))


def test_running_off_the_top_of_the_fretboard_raises() -> None:
    # bass4 has four strings, so a skip-1 pass over three of them needs five.
    with pytest.raises(ValueError, match=r"strings 0 to 4 are off profile 'bass4'"):
        generate(PROFILES["bass4"], params(string_traversal="skip_1", span=3))


def test_starting_below_the_lowest_string_raises() -> None:
    # The journey climbs from `start_string`, so a negative start runs off the
    # bottom of the neck; it is raised, never clamped (§10).
    with pytest.raises(ValueError, match=r"strings -1 to 1 are off profile 'bass6'"):
        generate(BASS6, params(start_string=-1, span=3))


def test_running_past_the_last_fret_raises() -> None:
    with pytest.raises(ValueError, match=r"frets 19 to 22 are off profile 'bass4'"):
        generate(PROFILES["bass4"], params(start_fret=19))


def test_a_negative_start_fret_raises() -> None:
    with pytest.raises(ValueError, match=r"frets -1 to 2 are off profile 'bass6'"):
        generate(BASS6, params(start_fret=-1))


def test_a_shift_that_walks_off_the_neck_raises() -> None:
    # span 3 up-and-down walks five string-groups, so the position shift climbs
    # four positions (cycles 0..4): 18 + 3 + 4 * 4 = fret 37, off the neck.
    spec = params(shift="position_per_cycle", start_fret=18, span=3)
    with pytest.raises(ValueError, match=r"frets 18 to 37 are off profile 'bass6'"):
        generate(BASS6, spec)
