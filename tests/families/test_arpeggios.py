"""Tests for the `arpeggios` family (spec §7).

The shape follows `test_scales.py`, because every family makes the same promise
and §14 tests them the same way: one complete cycle, the central invariant, the
key the notes are spelled against, the exact parameters travelling inside the
Score, a family-declared tempo, and a wide parameter sweep over the axes.

Three groups are specific to this family. The *content* tests assert that the
chord tones come from `theory.chord_pitches` and that `inversion` rotates them
— including that an inversion the chord cannot support raises rather than
wrapping round to root position. The *layout* tests assert that choosing where
each chord tone is played is the family's job (spec §6) and not the emitter's.
The *error* tests assert that a specification the profile cannot supply raises
and names what could not be satisfied — §9 resamples that case and §13 forbids
clamping it into something engravable.
"""

from __future__ import annotations

from fractions import Fraction
from itertools import product
from typing import TYPE_CHECKING

import pytest
from conftest import assert_central_invariant, assert_spelling_sounds_correctly, notes_of

from melete import theory, vocabulary
from melete.families.arpeggios import DEFAULT_TEMPO_RANGE, INSTRUCTION, INVERSIONS, generate
from melete.instrument import PROFILES

if TYPE_CHECKING:
    from melete.score import Score

BASS6 = PROFILES["bass6"]

#: The four lowest strings of a six-string bass: B E A D.
STRING_SET: tuple[int, ...] = (0, 1, 2, 3)

#: A1 = 33, so the worked example is A major 7 in root position — the same root
#: `test_scales.py` uses, so the two families' examples sit in the same key.
PARAMS: dict[str, object] = {
    "root": 33,
    "quality": "maj7",
    "inversion": "root",
    "traversal": "across_strings",
    "string_set": STRING_SET,
    "pattern": "straight",
    "range_octaves": 1,
    "direction": "up",
}

#: One octave of A major 7: the four chord tones and the closing octave.
AMAJ7 = [33, 37, 40, 44, 45]

QUALITIES = sorted(theory.CHORDS)
PATTERNS = ["straight", "numeric_1353", "broken", "sweep_ordered"]
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
    # Four chord tones plus the closing octave (spec §7: never truncated).
    assert len(generate(BASS6, PARAMS).voice) == 5


def test_obeys_the_central_invariant() -> None:
    assert_central_invariant(generate(BASS6, PARAMS))


def test_spells_every_note_as_it_sounds() -> None:
    assert_spelling_sounds_correctly(generate(BASS6, PARAMS))


def test_the_key_is_the_root_and_the_quality_s_implied_parent() -> None:
    # §10a: a chord is spelled by function, and the implied parent is what
    # turns that into the one `Key` mechanism the scales already use. Without
    # this the Score still engraves — spelled by the tier 3 direction rule,
    # silently — which is the defect §10a exists to fix.
    assert generate(BASS6, PARAMS).key == theory.Key(9, "ionian")


@pytest.mark.parametrize("quality", QUALITIES)
def test_every_quality_is_spelled_against_its_implied_parent(quality: str) -> None:
    score = generate(BASS6, params(quality=quality))
    assert score.key == theory.Key(9, theory.IMPLIED_PARENT[quality])
    assert_spelling_sounds_correctly(score)


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
    score = generate(BASS6, PARAMS)
    assert score.title == "A major 7th, across strings, ascending"
    assert score.instruction == INSTRUCTION


def test_the_title_names_an_inversion_and_a_pattern_only_when_there_is_one() -> None:
    score = generate(BASS6, params(inversion="first", pattern="broken", direction="down"))
    assert score.title == "A major 7th, first inversion, across strings, descending broken"


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
# Chord content comes from `theory`
# --------------------------------------------------------------------------


def test_chord_tone_content_is_root_third_fifth_and_seventh() -> None:
    score = generate(BASS6, PARAMS)
    assert {note.pitch % 12 for note in notes_of(score)} == {
        (33 + offset) % 12 for offset in (0, 4, 7, 11)
    }


def test_the_tones_are_theory_s_and_in_theory_s_order() -> None:
    assert pitches_of(generate(BASS6, PARAMS)) == [*theory.chord_pitches(33, "maj7"), 45]
    assert pitches_of(generate(BASS6, PARAMS)) == AMAJ7


def test_min7_flattens_the_third_and_the_seventh() -> None:
    major = sorted(pitches_of(generate(BASS6, PARAMS)))
    minor = sorted(pitches_of(generate(BASS6, params(quality="min7"))))
    assert minor[1] == major[1] - 1
    assert minor[3] == major[3] - 1


def test_a_triad_is_three_tones_plus_the_octave() -> None:
    assert pitches_of(generate(BASS6, params(quality="maj"))) == [33, 37, 40, 45]


@pytest.mark.parametrize("quality", QUALITIES)
def test_every_quality_takes_its_tones_from_theory(quality: str) -> None:
    played = pitches_of(generate(BASS6, params(quality=quality)))
    assert played == [*theory.chord_pitches(33, quality), 45]


def test_two_octaves_repeat_the_chord_an_octave_up() -> None:
    played = pitches_of(generate(BASS6, params(range_octaves=2)))
    assert played == [*AMAJ7[:-1], *(pitch + 12 for pitch in AMAJ7[:-1]), 57]


def test_three_octaves_span_three_octaves() -> None:
    # Across the strings rather than positional: three octaves is 36 semitones
    # and no hand covers that, so a `positional` three-octave arpeggio is a
    # contradiction the family now refuses (issue #57).
    spec = params(range_octaves=3, traversal="across_strings", string_set=(0, 1, 2, 3, 4, 5))
    played = pitches_of(generate(BASS6, spec))
    assert len(played) == 13
    assert played[-1] - played[0] == 36


# --------------------------------------------------------------------------
# `inversion` rotates the chord tones (spec §7)
# --------------------------------------------------------------------------


def test_the_inversion_identifiers_are_the_registry_s() -> None:
    # §7 writes the axis as root/first/second/third and `config` samples it as
    # a registry identifier, so the family reads an identifier and never the
    # bare rotation count it hands to `theory`.
    assert set(INVERSIONS) == set(vocabulary.accepted("inversion"))


def test_first_inversion_starts_on_the_third() -> None:
    root_position = pitches_of(generate(BASS6, PARAMS))
    first = pitches_of(generate(BASS6, params(inversion="first")))
    assert first[0] % 12 == (root_position[0] + 4) % 12


def test_each_inversion_starts_on_the_next_chord_tone() -> None:
    starts = [pitches_of(generate(BASS6, params(inversion=name)))[0] for name in INVERSIONS]
    assert starts == [33, 37, 40, 44]


def test_an_inversion_keeps_the_pitch_classes_and_stays_ascending() -> None:
    for name in INVERSIONS:
        played = pitches_of(generate(BASS6, params(inversion=name)))
        assert {pitch % 12 for pitch in played} == {pitch % 12 for pitch in AMAJ7}
        assert played == sorted(played)


def test_an_inversion_a_triad_cannot_support_raises() -> None:
    # A triad has no third inversion. Wrapping quietly round to root position
    # would engrave the wrong chord convincingly (§13), so `theory` refuses and
    # the family lets the refusal through with the quality named.
    with pytest.raises(ValueError, match=r"inversion 3 is out of range for 'maj'"):
        generate(BASS6, params(quality="maj", inversion="third"))


# --------------------------------------------------------------------------
# `direction` orders the sequence (the `scales` precedent)
# --------------------------------------------------------------------------


def test_direction_up_ascends() -> None:
    assert pitches_of(generate(BASS6, PARAMS)) == AMAJ7


def test_direction_down_reverses_the_sequence() -> None:
    assert pitches_of(generate(BASS6, params(direction="down"))) == AMAJ7[::-1]


def test_up_down_returns_without_replaying_the_apex() -> None:
    score = generate(BASS6, params(direction="up_down"))
    assert pitches_of(score) == AMAJ7 + AMAJ7[-2::-1]
    assert len(score.voice) == 9


def test_direction_reorders_without_changing_the_content() -> None:
    up = generate(BASS6, PARAMS)
    for direction in DIRECTIONS:
        other = generate(BASS6, params(direction=direction))
        assert set(pitches_of(other)) == set(pitches_of(up))


# --------------------------------------------------------------------------
# `pattern` reorders the chord tones before `direction` orders them
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pattern", "count"),
    [
        ("straight", 5),  # every tone once
        ("numeric_1353", 12),  # 4 x (5 - 2)
        ("broken", 6),  # 2 x (5 - 2)
        ("sweep_ordered", 9),  # 3 x (5 - 2)
    ],
)
def test_each_pattern_emits_one_complete_cycle(pattern: str, count: int) -> None:
    score = generate(BASS6, params(pattern=pattern))
    assert len(score.voice) == count
    assert_central_invariant(score)


def test_numeric_1353_emits_1_3_5_3() -> None:
    played = pitches_of(generate(BASS6, params(pattern="numeric_1353")))
    assert played[:4] == [AMAJ7[i] for i in (0, 1, 2, 1)]
    assert played[4:8] == [AMAJ7[i] for i in (1, 2, 3, 2)]


def test_broken_skips_a_tone_and_comes_back_for_it() -> None:
    played = pitches_of(generate(BASS6, params(pattern="broken")))
    assert played == [AMAJ7[i] for i in (0, 2, 1, 3, 2, 4)]


def test_broken_reorders_without_changing_the_content() -> None:
    straight = generate(BASS6, PARAMS)
    broken = generate(BASS6, params(pattern="broken"))
    assert pitches_of(broken) != sorted(pitches_of(broken))
    assert set(pitches_of(broken)) == set(pitches_of(straight))


def test_sweep_ordered_rolls_three_tones_at_a_time() -> None:
    played = pitches_of(generate(BASS6, params(pattern="sweep_ordered")))
    assert played == [AMAJ7[i] for i in (0, 1, 2, 1, 2, 3, 2, 3, 4)]


def test_a_pattern_reorders_without_changing_the_content() -> None:
    straight = generate(BASS6, PARAMS)
    for pattern in PATTERNS:
        other = generate(BASS6, params(pattern=pattern))
        assert set(pitches_of(other)) == set(pitches_of(straight))


def test_a_descending_pattern_is_the_retrograde_of_the_ascending_one() -> None:
    up = pitches_of(generate(BASS6, params(pattern="numeric_1353")))
    down = pitches_of(generate(BASS6, params(pattern="numeric_1353", direction="down")))
    assert down == up[::-1]


# --------------------------------------------------------------------------
# The traversals: position selection is the family's job (spec §6)
# --------------------------------------------------------------------------


def test_across_strings_puts_one_chord_tone_on_each_string() -> None:
    # The four chord tones walk the string set and the closing octave stays on
    # the top string of it, because there is no further string to move to.
    assert places_of(generate(BASS6, PARAMS)) == [(0, 10), (1, 9), (2, 7), (3, 6), (3, 7)]


def test_across_strings_stays_put_when_the_next_string_cannot_reach_the_tone() -> None:
    # C1 = 24 sits one fret above the open low B, so the fifth is below the
    # open A string and the tone waits a string rather than needing fret -2.
    assert places_of(generate(BASS6, params(root=24))) == [
        (0, 1),
        (1, 0),
        (1, 3),
        (2, 2),
        (2, 3),
    ]


def test_across_strings_stays_within_the_declared_string_set() -> None:
    score = generate(BASS6, params(range_octaves=2))
    assert {note.string for note in notes_of(score)} <= set(STRING_SET)


def test_positional_keeps_the_hand_in_one_place() -> None:
    # Every tone takes the position nearest the base fret that minimizes total
    # travel, which for A major 7 over the low four strings is the box at fret
    # 6 — a hand position, not five scattered reaches.
    score = generate(BASS6, params(traversal="positional"))
    assert places_of(score) == [(1, 5), (2, 4), (2, 7), (3, 6), (3, 7)]
    frets = [fret for _string, fret in places_of(score)]
    assert max(frets) - min(frets) <= 4


def test_positional_travels_less_than_taking_one_string_per_tone() -> None:
    boxed = places_of(generate(BASS6, params(traversal="positional")))
    across = places_of(generate(BASS6, PARAMS))
    assert _fret_span(boxed) < _fret_span(across)


def _fret_span(places: list[tuple[int, int]]) -> int:
    """How far the fretting hand reaches across one layout."""
    frets = [fret for _string, fret in places]
    return max(frets) - min(frets)


def test_single_string_stays_on_one_string() -> None:
    # String 2 is the open A1 the chord starts on, so every fret is the tone's
    # distance above the root.
    score = generate(BASS6, params(traversal="single_string", string_set=(2,)))
    assert places_of(score) == [(2, pitch - 33) for pitch in AMAJ7]


@pytest.mark.parametrize(
    ("traversal", "string_set"),
    [("positional", STRING_SET), ("across_strings", STRING_SET), ("single_string", (2,))],
)
def test_a_tone_keeps_its_place_however_often_the_pattern_visits_it(
    traversal: str,
    string_set: tuple[int, ...],
) -> None:
    # `numeric_1353` plays most tones three times. A traversal decides where a
    # tone lives, so every repeat must land in the same place — an arpeggio
    # that moved under the player's hand mid-figure is a different exercise.
    score = generate(
        BASS6,
        params(traversal=traversal, string_set=string_set, pattern="numeric_1353"),
    )
    seen: dict[int, tuple[int, int]] = {}
    for note in notes_of(score):
        assert seen.setdefault(note.pitch, (note.string, note.fret)) == (note.string, note.fret)
    assert_central_invariant(score)


# --------------------------------------------------------------------------
# Unrealizable specifications raise, naming what could not be satisfied (§13)
# --------------------------------------------------------------------------


def test_a_missing_axis_names_the_axis_and_the_family_s_axes() -> None:
    spec = params()
    del spec["pattern"]
    with pytest.raises(ValueError, match=r"parameter 'pattern' is required.*'quality'"):
        generate(BASS6, spec)


def test_an_unknown_identifier_lists_the_accepted_values() -> None:
    with pytest.raises(ValueError, match=r"unknown quality 'maj9'.*m7b5"):
        generate(BASS6, params(quality="maj9"))


def test_an_integer_inversion_is_not_an_identifier() -> None:
    # §7's inversion column is a registry axis like every other identifier, so
    # the bare rotation count `theory` takes is not accepted here.
    with pytest.raises(ValueError, match=r"unknown inversion 1"):
        generate(BASS6, params(inversion=1))


def test_a_traversal_this_family_cannot_realize_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"traversal 'three_note_per_string'.*arpeggios realizes"):
        generate(BASS6, params(traversal="three_note_per_string"))


def test_a_pattern_this_family_cannot_realize_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"pattern 'thirds'.*arpeggios realizes"):
        generate(BASS6, params(pattern="thirds"))


def test_a_non_integer_range_axis_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"root must be an integer, got '33'"):
        generate(BASS6, params(root="33"))


@pytest.mark.parametrize("octaves", [0, 4, -1])
def test_range_octaves_is_one_two_or_three(octaves: int) -> None:
    with pytest.raises(ValueError, match=r"range_octaves must be one of \[1, 2, 3\]"):
        generate(BASS6, params(range_octaves=octaves))


def test_a_string_set_off_the_instrument_raises() -> None:
    with pytest.raises(ValueError, match=r"string_set .* is off profile 'bass4'"):
        generate(PROFILES["bass4"], params(string_set=(0, 1, 2, 3, 4)))


def test_a_string_set_is_ascending_and_never_re_sorted() -> None:
    with pytest.raises(ValueError, match=r"string_set .* must be strictly ascending"):
        generate(BASS6, params(string_set=(2, 1, 0)))


def test_single_string_contradicts_a_wider_string_set() -> None:
    with pytest.raises(ValueError, match=r"single_string.*cannot both be satisfied"):
        generate(BASS6, params(traversal="single_string", string_set=(0, 1)))


def test_a_tone_below_the_string_set_raises() -> None:
    # A1 is fifteen semitones below the open C string, so an arpeggio confined
    # to it has nowhere to put the root.
    with pytest.raises(ValueError, match=r"needs fret -15 on string 5"):
        generate(BASS6, params(string_set=(5,)))


def test_a_positional_arpeggio_wider_than_the_hand_raises() -> None:
    # Two octaves of A major 7 over the low four strings puts the second octave
    # up the D string, nine frets above the first. That is a shift, and calling
    # it `positional` on the cover page is the mislabelling of issue #57.
    spec = params(traversal="positional", range_octaves=2)
    with pytest.raises(ValueError, match=r"positional traversal must fit one position") as raised:
        generate(BASS6, spec)
    assert "root, quality, inversion, range_octaves and string_set" in str(raised.value)


def test_a_tone_no_string_in_the_set_can_reach_raises() -> None:
    with pytest.raises(ValueError, match=r"pitch 33 is unreachable on strings \[5\]"):
        generate(BASS6, params(traversal="positional", string_set=(5,)))


def test_running_past_the_last_fret_raises() -> None:
    # Three octaves from the open A string runs out of neck, and the cycle is
    # never truncated to fit (spec §7).
    spec = params(traversal="single_string", string_set=(2,), range_octaves=3)
    with pytest.raises(ValueError, match=r"needs fret 28 on string 2"):
        generate(BASS6, spec)


# --------------------------------------------------------------------------
# The sweeps (spec §14: families are tested over a wide parameter sweep)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("root", range(24, 36))
@pytest.mark.parametrize("quality", QUALITIES)
@pytest.mark.parametrize("inversion", INVERSIONS)
def test_invariant_holds_across_roots_qualities_and_inversions(
    root: int,
    quality: str,
    inversion: str,
) -> None:
    spec = params(root=root, quality=quality, inversion=inversion)
    if INVERSIONS.index(inversion) >= len(theory.CHORDS[quality]):
        # A triad has no third inversion (§13): the specification is rejected
        # rather than wrapped round to something engravable.
        with pytest.raises(ValueError, match=r"out of range"):
            generate(BASS6, spec)
        return

    score = generate(BASS6, spec)
    assert_central_invariant(score)
    assert_spelling_sounds_correctly(score)
    assert score.key == theory.Key(root % 12, theory.IMPLIED_PARENT[quality])
    assert len(score.voice) == len(theory.CHORDS[quality]) + 1
    assert {note.string for note in notes_of(score)} <= set(STRING_SET)


@pytest.mark.parametrize(("pattern", "direction"), list(product(PATTERNS, DIRECTIONS)))
def test_invariant_holds_across_patterns_and_directions(pattern: str, direction: str) -> None:
    score = generate(BASS6, params(pattern=pattern, direction=direction))
    assert_central_invariant(score)
    assert_spelling_sounds_correctly(score)


@pytest.mark.parametrize("traversal", ["positional", "across_strings"])
@pytest.mark.parametrize("octaves", [1, 2])
def test_invariant_holds_across_traversals_and_octaves(traversal: str, octaves: int) -> None:
    # Every string, because a two-octave arpeggio fits under one hand only when
    # the set is wide enough to carry it: over the low four strings the second
    # octave lies up the D string, which is a shift and not a position.
    spec = params(traversal=traversal, range_octaves=octaves, string_set=(0, 1, 2, 3, 4, 5))
    score = generate(BASS6, spec)
    assert_central_invariant(score)
    assert_spelling_sounds_correctly(score)


@pytest.mark.parametrize("profile_name", sorted(PROFILES))
def test_invariant_holds_across_the_profiles(profile_name: str) -> None:
    profile = PROFILES[profile_name]
    # bass4 starts on E1 and has no low B, so the same shape sits on strings
    # 0-3 of whatever the profile provides.
    spec = params(string_set=tuple(range(min(4, len(profile.tuning)))))
    assert_central_invariant(generate(profile, spec))
