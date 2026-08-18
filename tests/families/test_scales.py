"""Tests for the `scales` family (spec §7, epic #72 §5-§7).

The shape follows `test_chromatic.py`, because every family makes the same
promise and §14 tests them the same way: one complete cycle, the central
invariant, the exact parameters travelling inside the Score, a family-declared
tempo, and a wide parameter sweep over the axes.

Since epic #72 the exercise is a **computed outer-to-outer journey**: the root
anchors on the lowest string, the journey climbs string by string to the
opposite outer string under a fingering style, and the whole thing is played up
and back. The three geometry axes the old model sampled — `direction`,
`string_set`, `range_octaves` — are gone; extent and octave count are emergent
from reaching the top string. The *journey* tests assert that coverage
(outer-to-outer, no gaps) and the up-and-down shape; the *layout* tests assert
that position selection is the family's job (spec §6) — a fingering style
decides which string each degree is played on, and a degree the pattern visits
twice is played in the same place both times. The *error* tests assert that a
specification the profile cannot supply raises rather than truncating the
journey to fit (spec §10).
"""

from __future__ import annotations

from collections import Counter
from fractions import Fraction
from itertools import product
from typing import TYPE_CHECKING

import pytest
from conftest import assert_central_invariant, assert_spelling_sounds_correctly, notes_of

from melete import theory
from melete.families._shared import derive_legato
from melete.families.scales import DEFAULT_TEMPO_RANGE, INSTRUCTION
from melete.families.scales import generate as _generate
from melete.instrument import PROFILES, hand_span
from melete.layout import Lever
from melete.score import Attack, Hand, Note, Voice

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


BASS6 = PROFILES["bass6"]  # tuning B0 E1 A1 D2 G2 C3 = (23, 28, 33, 38, 43, 48).

#: The lowest and highest string indices of a six-string bass — the outer
#: strings the journey travels between.
_LOW = 0
_HIGH = len(BASS6.tuning) - 1

#: A1 = 33 (fret 10 on the low B string). The four axes the family now reads: a
#: content root and scale, a fingering style, and a grouping pattern. `positional`
#: is the default because, across every root and scale in the sweep, the box
#: reaches the top string within one hand — a clean journey on every draw.
PARAMS: dict[str, object] = {
    "root": 33,
    "scale_type": "ionian",
    "traversal": "positional",
    "pattern": "straight",
}

PATTERNS = ["straight", "thirds", "fourths", "groups_of_3", "groups_of_4", "numeric_1235"]
TRAVERSALS = ["positional", "three_note_per_string"]


def params(**overrides: object) -> dict[str, object]:
    """`PARAMS` with one or more axes replaced."""
    return {**PARAMS, **overrides}


def pitches_of(score: Score) -> list[int]:
    """The pitch of every note, in playing order."""
    return [note.pitch for note in notes_of(score)]


def places_of(score: Score) -> list[tuple[int, int]]:
    """The (string, fret) of every note, in playing order."""
    return [(note.string, note.fret) for note in notes_of(score)]


def strings_of(score: Score) -> list[int]:
    """The string of every note, in playing order."""
    return [note.string for note in notes_of(score)]


# --------------------------------------------------------------------------
# The family contract
# --------------------------------------------------------------------------


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


def test_extra_axes_are_carried_untouched() -> None:
    # The retired geometry axes no longer arrive from config (Task E2 removed
    # them), but a replayed pre-E2 session.json may still carry them, and §8's
    # rhythm axes always do. The family reads neither and carries both into the
    # Score untouched (the existing contract).
    spec = params(direction="up", string_set=(0, 1, 2, 3), range_octaves=2, subdivision="triplet")
    assert generate(BASS6, spec).params == spec


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
    # The title no longer names a direction: every scale is drilled up and down.
    score = generate(BASS6, params(root=38, scale_type="dorian"))
    assert score.title == "D Dorian, positional"
    assert score.instruction == INSTRUCTION


def test_the_title_names_a_pattern_only_when_there_is_one() -> None:
    assert generate(BASS6, PARAMS).title == "A Ionian, positional"
    thirds = generate(BASS6, params(pattern="thirds"))
    assert thirds.title == "A Ionian, positional, thirds"
    three_note = generate(BASS6, params(traversal="three_note_per_string"))
    assert three_note.title == "A Ionian, three-notes-per-string"


def test_generate_is_pure() -> None:
    given = params()
    first, second = generate(BASS6, given), generate(BASS6, given)
    assert first == second
    assert given == PARAMS

    # The Score owns its parameters: a caller reusing the dictionary it passed
    # in must not be able to rewrite the record of what was generated.
    first.params["root"] = 99
    assert given["root"] == 33


def test_the_hints_carry_the_up_and_down_apex_accounting() -> None:
    # The voice is always up-and-down (spec §5), so it always declares its apex
    # seam and carries the apex-repeat/omit levers the fitter reaches a whole
    # bar with — never the plain add/drop of a one-directional run.
    _score, hints = _generate(BASS6, PARAMS)
    assert hints.seam is not None
    assert hints.levers == (Lever.APEX_REPEAT, Lever.APEX_OMIT)
    assert hints.cell == 1  # `straight` is a one-note window


# --------------------------------------------------------------------------
# The journey: outer string to opposite outer string, up and down (spec §5)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("traversal", TRAVERSALS)
def test_the_journey_reaches_both_outer_strings(traversal: str) -> None:
    # Extent is governed by outer-string-to-outer-string, not an octave count:
    # every string is used, in order, with no gaps (the fix for defects 1 and 4).
    strings = strings_of(generate(BASS6, params(traversal=traversal)))
    assert min(strings) == _LOW and max(strings) == _HIGH
    assert sorted(set(strings)) == list(range(len(BASS6.tuning)))


@pytest.mark.parametrize("traversal", TRAVERSALS)
def test_the_journey_starts_and_ends_on_the_low_string(traversal: str) -> None:
    # Up and back: the round trip begins at the low anchor and returns to it.
    strings = strings_of(generate(BASS6, params(traversal=traversal)))
    assert strings[0] == _LOW
    assert strings[-1] == _LOW


def test_a_straight_journey_is_an_exact_palindrome() -> None:
    # `straight` is a one-note cell, so the descent is the note-level retrograde
    # of the ascent: the whole pitch sequence reads the same forwards and back.
    played = pitches_of(generate(BASS6, PARAMS))
    assert played == played[::-1]
    assert played[0] == 33  # anchored on the root


def test_the_ascent_climbs_then_the_descent_falls() -> None:
    played = pitches_of(generate(BASS6, PARAMS))
    apex = played.index(max(played))
    assert played[: apex + 1] == sorted(played[: apex + 1])  # strictly up to the apex
    assert played[apex:] == sorted(played[apex:], reverse=True)  # then down


# --------------------------------------------------------------------------
# Pitch content comes from `theory`, and the octaves it yields are emergent
# --------------------------------------------------------------------------


def test_scale_content_matches_theory() -> None:
    score = generate(BASS6, PARAMS)
    assert {note.pitch % 12 for note in notes_of(score)} == {
        (33 + offset) % 12 for offset in (0, 2, 4, 5, 7, 9, 11)
    }


def test_the_ascending_degrees_are_a_prefix_of_theory_s_supply() -> None:
    # The family draws a long ascending supply from `theory` and uses the leading
    # run that reaches the top string; the ascent is exactly that prefix, in order.
    played = pitches_of(generate(BASS6, PARAMS))
    ascent = played[: played.index(max(played)) + 1]
    supply = theory.scale_pitches(33, "ionian", len(BASS6.tuning) + 1)
    assert ascent == supply[: len(ascent)]


def test_octave_count_is_emergent_from_the_instrument() -> None:
    # A six-string yields roughly two and a half octaves — whatever reaching the
    # top string gives, never a sampled target.
    ascent_span = max(pitches_of(generate(BASS6, PARAMS))) - 33
    assert 24 <= ascent_span <= 36  # between two and three octaves


# --------------------------------------------------------------------------
# `pattern` reorders the degrees before positions are assigned (spec §7)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("pattern", PATTERNS)
def test_each_pattern_is_up_and_down_and_holds_the_invariant(pattern: str) -> None:
    score = generate(BASS6, params(pattern=pattern))
    assert_central_invariant(score)
    strings = strings_of(score)
    assert strings[0] == _LOW and strings[-1] == _LOW


def test_thirds_produces_more_notes_than_straight() -> None:
    straight = generate(BASS6, PARAMS)
    thirds = generate(BASS6, params(pattern="thirds"))
    assert len(thirds.voice) > len(straight.voice)


def test_thirds_emits_overlapping_thirds_across_the_ascent() -> None:
    played = pitches_of(generate(BASS6, params(pattern="thirds")))
    ascent = pitches_of(generate(BASS6, PARAMS))
    ascent = ascent[: ascent.index(max(ascent)) + 1]  # the underlying scale run
    # 1-3, 2-4, 3-5: each window starts one degree higher and skips one.
    assert played[:6] == [ascent[i] for i in (0, 2, 1, 3, 2, 4)]


def test_groups_of_3_emits_overlapping_groups() -> None:
    played = pitches_of(generate(BASS6, params(pattern="groups_of_3")))
    ascent = pitches_of(generate(BASS6, PARAMS))
    ascent = ascent[: ascent.index(max(ascent)) + 1]
    assert played[:9] == [ascent[i] for i in (0, 1, 2, 1, 2, 3, 2, 3, 4)]


def test_numeric_1235_skips_the_fourth_degree_of_each_group() -> None:
    played = pitches_of(generate(BASS6, params(pattern="numeric_1235")))
    ascent = pitches_of(generate(BASS6, PARAMS))
    ascent = ascent[: ascent.index(max(ascent)) + 1]
    assert played[:8] == [ascent[i] for i in (0, 1, 2, 4, 1, 2, 3, 5)]


def test_a_grouping_pattern_reaches_the_top_string_before_turning() -> None:
    # Defect 3 was the window running out of notes before the top; the full
    # outer-to-outer ascent supplies the notes it needs, so the ascending half
    # reaches the top string.
    notes = notes_of(generate(BASS6, params(pattern="groups_of_4")))
    ascent = notes[: len(notes) // 2 + 1]
    assert max(note.string for note in ascent) == _HIGH


def test_a_pattern_reorders_without_changing_the_content() -> None:
    straight = generate(BASS6, PARAMS)
    for pattern in PATTERNS:
        other = generate(BASS6, params(pattern=pattern))
        assert set(pitches_of(other)) == set(pitches_of(straight))


# --------------------------------------------------------------------------
# The fingering styles: position selection is the family's job (spec §6)
# --------------------------------------------------------------------------


def test_positional_stays_within_one_hand_position() -> None:
    score = generate(BASS6, PARAMS)
    assert hand_span(note.fret for note in notes_of(score)) <= BASS6.position_span


def test_positional_uses_more_than_one_string() -> None:
    score = generate(BASS6, PARAMS)
    assert len({note.string for note in notes_of(score)}) > 1


def test_three_note_per_string_puts_exactly_three_notes_on_each_string() -> None:
    score = generate(BASS6, params(traversal="three_note_per_string"))
    # Ascending, each string is visited once with three consecutive degrees; the
    # up-and-down return revisits them, so three-per-string is the ascending count.
    ascent = notes_of(score)[: len(notes_of(score)) // 2 + 1]
    counts = Counter(note.string for note in ascent)
    assert set(counts.values()) == {3}
    assert sorted(counts) == list(range(len(BASS6.tuning)))


def test_three_note_per_string_assigns_consecutive_degrees_to_each_string() -> None:
    score = generate(BASS6, params(traversal="three_note_per_string"))
    ascent = places_of(score)[:18]  # three notes on each of six strings
    assert ascent == [
        (0, 10), (0, 12), (0, 14),
        (1, 10), (1, 12), (1, 14),
        (2, 11), (2, 12), (2, 14),
        (3, 11), (3, 12), (3, 14),
        (4, 11), (4, 13), (4, 14),
        (5, 11), (5, 13), (5, 14),
    ]  # fmt: skip
    for string, fret in ascent:
        assert BASS6.tuning[string] + fret in {note.pitch for note in notes_of(score)}


@pytest.mark.parametrize("traversal", TRAVERSALS)
def test_a_degree_keeps_its_place_however_often_the_pattern_visits_it(traversal: str) -> None:
    # `groups_of_3` plays every inner degree three times. A fingering style
    # decides where a degree lives, so all three must land in the same place — a
    # scale that moved under the player's hand mid-figure is a different exercise.
    score = generate(BASS6, params(traversal=traversal, pattern="groups_of_3"))
    seen: dict[int, tuple[int, int]] = {}
    for note in notes_of(score):
        assert seen.setdefault(note.pitch, (note.string, note.fret)) == (note.string, note.fret)
    assert_central_invariant(score)


# --------------------------------------------------------------------------
# The sweeps (spec §14: families are tested over a wide parameter sweep)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("root", range(24, 36))
@pytest.mark.parametrize("scale_type", sorted(theory.SCALES))
def test_positional_realizes_every_root_and_scale_outer_to_outer(
    root: int, scale_type: str
) -> None:
    # The positional box reaches the opposite outer string within one hand on
    # every draw in this range, so the sweep asserts the journey outright: a
    # Score that holds together, spelled correctly, covering the whole neck.
    score = generate(BASS6, params(root=root, scale_type=scale_type))
    assert_central_invariant(score)
    assert_spelling_sounds_correctly(score)
    assert score.key == theory.Key(root % 12, scale_type)
    strings = strings_of(score)
    assert min(strings) == _LOW and max(strings) == _HIGH
    assert hand_span(note.fret for note in notes_of(score)) <= BASS6.position_span


@pytest.mark.parametrize(("pattern", "traversal"), list(product(PATTERNS, TRAVERSALS)))
def test_invariant_holds_across_patterns_and_traversals(pattern: str, traversal: str) -> None:
    score = generate(BASS6, params(pattern=pattern, traversal=traversal))
    assert_central_invariant(score)
    assert_spelling_sounds_correctly(score)


@pytest.mark.parametrize("profile_name", sorted(PROFILES))
def test_the_journey_reaches_both_outer_strings_on_every_profile(profile_name: str) -> None:
    # A four-string yields ≈1.5 octaves and a six-string ≈2.5, but each reaches
    # its own opposite outer string — the invariant that generalizes across
    # instruments where a fixed octave count would not (spec §5).
    profile = PROFILES[profile_name]
    score = generate(profile, PARAMS)
    strings = [note.string for note in notes_of(score)]
    assert min(strings) == 0 and max(strings) == len(profile.tuning) - 1
    assert_central_invariant(score)


@pytest.mark.parametrize("scale_type", sorted(theory.SCALES))
def test_three_note_per_string_realizes_or_names_what_it_cannot(scale_type: str) -> None:
    # Three notes per string climbs every string; a scale whose degrees run off
    # the neck (below the open low string, or past the top fret) cannot be laid
    # out. §9 resamples that draw; §10 forbids truncating the journey to fit, so
    # the family raises and names the fret that could not be placed.
    spec = params(scale_type=scale_type, traversal="three_note_per_string")
    try:
        score = generate(BASS6, spec)
    except ValueError as error:
        assert "needs fret" in str(error)
        assert "scales" in str(error)
        return
    assert_central_invariant(score)
    ascent = notes_of(score)[: len(notes_of(score)) // 2 + 1]
    assert set(Counter(note.string for note in ascent).values()) == {3}


# --------------------------------------------------------------------------
# Unrealizable or malformed specifications raise, naming what failed (§13)
# --------------------------------------------------------------------------


def test_a_missing_axis_names_the_axis_and_the_family_s_axes() -> None:
    spec = params()
    del spec["pattern"]
    with pytest.raises(ValueError, match=r"parameter 'pattern' is required.*'scale_type'"):
        generate(BASS6, spec)


def test_an_unknown_identifier_lists_the_accepted_values() -> None:
    with pytest.raises(ValueError, match=r"unknown scale_type 'lydian_b9'.*altered"):
        generate(BASS6, params(scale_type="lydian_b9"))


def test_a_traversal_this_family_cannot_realize_is_rejected() -> None:
    # `across_strings` is a registry identifier, but it belongs to `arpeggios`:
    # one axis, and each family validates the subset it can realize (§13).
    with pytest.raises(ValueError, match=r"traversal 'across_strings'.*scales realizes"):
        generate(BASS6, params(traversal="across_strings"))


def test_a_deferred_traversal_is_rejected() -> None:
    # `single_string` and `octave_per_string` are deferred to the single/two
    # string modes (spec §13); the family names them as another family's values.
    with pytest.raises(ValueError, match=r"traversal 'single_string'.*scales realizes"):
        generate(BASS6, params(traversal="single_string"))


def test_a_pattern_this_family_cannot_realize_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"pattern 'broken'.*scales realizes"):
        generate(BASS6, params(pattern="broken"))


def test_a_non_integer_root_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"root must be an integer, got '33'"):
        generate(BASS6, params(root="33"))


def test_a_boolean_root_is_not_an_integer() -> None:
    with pytest.raises(ValueError, match=r"root must be an integer, got True"):
        generate(BASS6, params(root=True))


def test_a_journey_running_off_the_low_string_raises_rather_than_truncating() -> None:
    # Three notes per string from a root whose opening degrees fall below the
    # open low string needs a negative fret; the journey is never truncated to
    # fit (spec §10), so the family surfaces the fret it could not place.
    spec = params(root=24, scale_type="diminished_half_whole", traversal="three_note_per_string")
    with pytest.raises(ValueError, match=r"scales: pitch \d+ needs fret -\d+ on string"):
        generate(BASS6, spec)


def test_a_journey_running_past_the_top_fret_raises() -> None:
    # And the same at the other end: a root high enough that a string's group
    # runs past the last fret is unrealizable rather than clamped.
    spec = params(root=32, scale_type="minor_pentatonic", traversal="three_note_per_string")
    with pytest.raises(ValueError, match=r"scales: pitch \d+ needs fret 25 on string"):
        generate(BASS6, spec)


# --------------------------------------------------------------------------
# The two-hand tapped 3nps scale (hands == 2; corpus R9/R10, epic #67, #214)
# --------------------------------------------------------------------------

LEFT, RIGHT = Hand.LEFT, Hand.RIGHT
TAPPED, PLUCKED, SLURRED = Attack.TAPPED, Attack.PLUCKED, Attack.SLURRED

#: A 3nps scale known to lay out on the whole bass6 neck (the one-hand 3nps tests
#: pin its exact places): A Ionian, three notes per string, drawn with two hands.
TAPPED_PARAMS: dict[str, object] = {
    "root": 33,
    "scale_type": "ionian",
    "traversal": "three_note_per_string",
    "pattern": "straight",
    "hands": 2,
}


def tapped(**overrides: object) -> Score:
    """A two-hand tapped 3nps scale, one or more axes replaced."""
    return generate(BASS6, {**TAPPED_PARAMS, **overrides})


def test_a_tapped_scale_taps_every_note_with_both_hands() -> None:
    # R9: a two-hand shape — every note tapped at the family layer (the legato
    # pass derives the hammers/pulls after the fitter), both hands in play.
    notes = notes_of(tapped())
    assert {note.hand for note in notes} == {LEFT, RIGHT}


def test_a_tapped_scale_puts_the_two_lower_notes_left_and_the_top_right() -> None:
    # R9, per string: of each string's three consecutive degrees the two lower
    # are LEFT-hand and the top is RIGHT-hand. Checked on the ascending pass,
    # grouped three-to-a-string.
    notes = notes_of(tapped())
    ascent = notes[: len(notes) // 2]  # apex-doubled, so the ascent is the first half
    for start in range(0, len(ascent), 3):
        low, mid, top = ascent[start : start + 3]
        assert low.hand is LEFT and mid.hand is LEFT and top.hand is RIGHT
        assert low.fret < mid.fret < top.fret  # low, mid, top by fret within the string


def test_a_tapped_scale_obeys_the_central_invariant_and_spelling() -> None:
    score = tapped()
    assert_central_invariant(score)
    assert_spelling_sounds_correctly(score)


def test_a_tapped_scale_pitch_content_is_the_scale_tiled() -> None:
    # The pitch content is exactly the one-hand 3nps journey's — the scale tiled
    # across the neck — the hand split and articulation do not touch which notes
    # sound.
    one_hand = pitches_of(generate(BASS6, params(traversal="three_note_per_string")))
    assert set(pitches_of(tapped())) == set(one_hand)


def test_a_tapped_scale_climbs_up_and_back_to_the_low_root() -> None:
    # The journey is an apex-doubled symmetric palindrome (corpus R7/R12): it
    # reads the same forwards and back, re-taps the apex at the fold, and returns
    # to the low root — an even count that tiles with no lever.
    pitches = pitches_of(tapped())
    assert len(pitches) % 2 == 0
    assert pitches == pitches[::-1]
    half = len(pitches) // 2
    assert pitches[half - 1] == pitches[half]  # the doubled apex
    assert pitches[0] == pitches[-1] == 33  # begins and ends on the low root


def test_a_tapped_scale_stamps_the_descending_cross_hand_pull() -> None:
    # The descending group's first pull crosses hands (right-tapped top -> left
    # mid): the shared legato pass cannot derive it, so the family stamps it
    # SLURRED. The mid of every descending group (the note right after a
    # same-string, other-hand, higher-fret note) is SLURRED at the family layer.
    notes = notes_of(tapped())
    stamped = [
        note
        for prev, note in zip(notes, notes[1:], strict=False)
        if prev.string == note.string and prev.hand is not note.hand and prev.fret > note.fret
    ]
    assert stamped  # there are descending groups
    assert all(note.attack is SLURRED for note in stamped)


def test_a_tapped_scale_declares_a_lever_free_apex_doubled_layout() -> None:
    # Like the tapped arpeggio journey: the single tap is the cell, the apex is
    # the seam, and no note-count lever is offered — the even apex-doubled count
    # always tiles, and a lever would only break the symmetric descent (R12).
    _score, hints = _generate(BASS6, TAPPED_PARAMS)
    assert hints.cell == 1
    assert hints.seam is not None
    assert hints.levers == ()


def test_a_positional_scale_with_two_hands_is_deferred_and_raises() -> None:
    # Only the 3nps traversal taps in H1; a two-hand positional scale is a
    # separate deferred shape and raises rather than silently tapping (§9/§13).
    with pytest.raises(ValueError, match=r"three_note_per_string.*deferred"):
        tapped(traversal="positional")


def test_a_non_integer_hands_is_a_loud_failure() -> None:
    # `hands` is a hand count: a non-integer (here a string) is rejected rather
    # than silently defaulting, so a misspelled value is a loud failure (§13).
    with pytest.raises(ValueError, match="hands must be an integer"):
        tapped(hands="two")


@pytest.mark.parametrize("hands", [None, 1])
def test_a_one_hand_scale_is_unchanged_by_the_hands_axis(hands: object) -> None:
    # The default (no `hands`) and an explicit `hands == 1` are the existing
    # one-hand journey, byte-for-byte: every note plucked by the left hand, no
    # tapping. Only `hands == 2` taps.
    spec = params(traversal="three_note_per_string")
    if hands is not None:
        spec["hands"] = hands
    notes = notes_of(generate(BASS6, spec))
    assert all(note.attack is PLUCKED for note in notes)
    assert all(note.hand is LEFT for note in notes)


def test_the_hands_axis_leaves_the_one_hand_score_byte_for_byte_identical() -> None:
    # `hands == 1` produces the identical Score the axis-free spec does — the new
    # routing is a no-op for the one-hand path (the frozen goldens are safe).
    base = params(traversal="three_note_per_string")
    assert generate(BASS6, base).voice == generate(BASS6, {**base, "hands": 1}).voice


# --------------------------------------------------------------------------
# The shared legato pass preserves the descending cross-hand pull (R9/R10)
# --------------------------------------------------------------------------


def _tapped_note(string: int, hand: Hand, fret: int, attack: Attack = TAPPED) -> Note:
    return Note(
        pitch=BASS6.tuning[string] + fret,
        string=string,
        fret=fret,
        duration=Fraction(1, 4),
        finger=None,
        accent=False,
        hand=hand,
        attack=attack,
    )


def _attacks(voice: Voice) -> list[Attack]:
    return [note.attack for note in voice if isinstance(note, Note)]


def test_legato_derives_the_ascending_tap_hammer_tap_group() -> None:
    # R9 ascending: left-tap the low, hammer-on (same hand, fret rising) to the
    # mid, right-tap the top (a fresh cross-hand tap, not a slur).
    group: Voice = [
        _tapped_note(0, LEFT, 10),
        _tapped_note(0, LEFT, 12),
        _tapped_note(0, RIGHT, 14),
    ]
    assert _attacks(derive_legato(group)) == [TAPPED, SLURRED, TAPPED]


def test_legato_preserves_the_descending_tap_pull_pull_group() -> None:
    # R9/R10 descending: the family stamps the cross-hand pull (right top -> left
    # mid) SLURRED; the legato pass preserves it and derives the same-hand lower
    # pull, yielding tap · pull · pull.
    group: Voice = [
        _tapped_note(0, RIGHT, 14),
        _tapped_note(0, LEFT, 12, attack=SLURRED),  # family-stamped cross-hand pull
        _tapped_note(0, LEFT, 10),
    ]
    assert _attacks(derive_legato(group)) == [TAPPED, SLURRED, SLURRED]


def test_legato_does_not_slur_a_rising_cross_hand_tap() -> None:
    # The mirror of the descending pull: a cross-hand move whose fret RISES is a
    # fresh right-hand tap, not a pull-off — even if it arrived SLURRED, the
    # geometry is not a pull-off so it re-taps.
    voice: Voice = [
        _tapped_note(0, LEFT, 12),
        _tapped_note(0, RIGHT, 14, attack=SLURRED),
    ]
    assert _attacks(derive_legato(voice)) == [TAPPED, TAPPED]
