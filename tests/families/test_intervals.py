"""Tests for the `intervals` family (spec §7, epic #72).

The shape follows `test_scales.py`, because every family makes the same promise
and §14 tests them the same way: one complete cycle, the central invariant, the
key the notes are spelled against, the exact parameters travelling inside the
Score, a family-declared tempo, and a wide parameter sweep over the axes.

What is specific to this family is the *string* assertions. §7 puts `intervals`
in the tool because tablature makes string topology expressible and these
exercises cannot be described by pitch alone — which is the whole justification
for modelling the fretboard in the core rather than treating position as a
rendering detail. A test suite that only checked pitches would pass on an
`intervals` family that ignored `string_skip` entirely, and the exercise would
be a plausible-looking sheet that is not the one that was asked for (§13). So the
topology group below asserts which strings each pair lands on and that the
distance between the two notes of a pair is exactly `string_skip + 1`.

Epic #72 replaced the sampled `direction`/`string_set`/octave draws with a
computed journey: the lower voice climbs the lower strings under
`journey.per_string`, each partner sits `string_skip + 1` strings above, and the
pairs always go up and down. The journey group below is the mirror of
`test_scales.py`'s — the exercise starts on the low outer string, reaches the
opposite outer string, and returns, covering the whole instrument with no gap.

The `context` group is the second half of the same argument. A diatonic third is
three semitones on some degrees and four on others; a chromatic third is always
four. Asserting both is what proves the axis is realized rather than assumed.
"""

from __future__ import annotations

from fractions import Fraction
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
from melete.instrument import PROFILES, InstrumentProfile
from melete.layout import Lever

if TYPE_CHECKING:
    from collections.abc import Mapping

    from melete.score import Note, Score


def generate(profile: InstrumentProfile, params: Mapping[str, object]) -> Score:
    """Unpack the family's `(Score, LayoutHints)`; these tests assert on the Score.

    §4.2 widened every family to return its layout hints alongside the Score. The
    hint contract is covered in `test_registry`; here the Score is the subject, so
    a single wrapper unpacks it rather than every call site.
    """
    score, _hints = _generate(profile, params)
    return score


BASS6 = PROFILES["bass6"]

#: A1 = 33, the same root `test_scales.py` and `test_arpeggios.py` use, so all
#: three families' worked examples sit in the same key. No `string_set` and no
#: `direction`: coverage is the whole instrument and every journey is up and down
#: (epic #72), so neither is a sampled axis any longer.
PARAMS: dict[str, object] = {
    "interval": 3,
    "context": "diatonic",
    "root": 33,
    "scale_type": "ionian",
    "string_skip": "0",
    "pattern": "ascending_pairs",
}

INTERVALS = sorted(INTERVAL_NAMES)
SKIPS = ("0", "1", "2")
CONTEXTS = ("diatonic", "chromatic")
PATTERNS = ("ascending_pairs", "descending_pairs", "alternating")


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


def beats_of(score: Score) -> list[tuple[Note, Note]]:
    """The notes grouped two to a beat — one pair as it is played."""
    notes = notes_of(score)
    return list(zip(notes[::2], notes[1::2], strict=True))


def lower_of(beat: tuple[Note, Note]) -> int:
    """The lower note's pitch of a beat, whichever order the pattern plays it in."""
    return min(beat[0].pitch, beat[1].pitch)


def pair_interval(beat: tuple[Note, Note]) -> int:
    """The semitone size of one pair, whichever order the pattern plays it in."""
    return abs(beat[0].pitch - beat[1].pitch)


def ascent_of(score: Score) -> list[tuple[Note, Note]]:
    """The beats of the ascending pass, up to and including the apex pair.

    The lower voice climbs monotonically to a single apex and then retraces it,
    so the apex is the last pair whose lower note is the highest — the turnaround
    the up-and-down journey folds around (spec §5).
    """
    beats = beats_of(score)
    lows = [lower_of(beat) for beat in beats]
    apex = lows.index(max(lows))
    return beats[: apex + 1]


def ascending_scale(root: int, scale_type: str, length: int) -> list[int]:
    """`length` ascending degrees of a scale from `root`, for pinning the content."""
    degrees_per_octave = len(theory.SCALES[scale_type])
    octaves = -(-(length + 1) // degrees_per_octave) + 1
    return theory.scale_pitches(root, scale_type, octaves)[:length]


# --------------------------------------------------------------------------
# The family contract
# --------------------------------------------------------------------------


def test_generates_one_complete_up_and_down_journey() -> None:
    # The cycle is the full outer-to-outer ascent and its retrograde, never
    # truncated (spec §5): `p` pairs up, then all but the apex pair back, so the
    # descent is the exact retrograde of the ascent without replaying the apex.
    score = generate(BASS6, PARAMS)
    beats = beats_of(score)
    ascent = ascent_of(score)
    p = len(ascent)
    assert len(beats) == 2 * p - 1
    replay = [(lower_of(beat), max(beat[0].pitch, beat[1].pitch)) for beat in beats]
    assert replay[p:] == replay[: p - 1][::-1]


def test_obeys_the_central_invariant() -> None:
    assert_central_invariant(generate(BASS6, PARAMS))


def test_spells_every_note_as_it_sounds() -> None:
    assert_spelling_sounds_correctly(generate(BASS6, PARAMS))


def test_params_travel_inside_the_score() -> None:
    assert generate(BASS6, PARAMS).params == PARAMS


def test_default_tempo_range_is_declared_by_the_family() -> None:
    # Spec §7: the family declares the range and the selector never samples it.
    assert DEFAULT_TEMPO_RANGE == (70, 130)
    assert generate(BASS6, PARAMS).tempo_range == (70, 130)


def test_the_notes_are_plain_and_unaccented() -> None:
    # §8's rhythm modifier owns subdivision and accents; this family states the
    # un-modified reading and nothing more.
    score = generate(BASS6, PARAMS)
    assert score.time_signature == (4, 4)
    assert {(note.duration, note.accent) for note in notes_of(score)} == {(Fraction(1, 4), False)}


def test_the_fingering_is_left_unspecified() -> None:
    assert {note.finger for note in notes_of(generate(BASS6, PARAMS))} == {None}


def test_the_score_carries_a_title_and_a_focus_cue() -> None:
    # The direction word is gone from the cover page: every journey is
    # up-and-down now (epic #72), so a word that never varies is only noise.
    score = generate(BASS6, PARAMS)
    assert score.title == "A Ionian thirds, adjacent strings, ascending pairs"
    assert score.instruction == INSTRUCTION


def test_a_chromatic_title_names_the_context_rather_than_a_scale() -> None:
    score = generate(BASS6, params(context="chromatic", string_skip="1", interval=5))
    assert score.title == "A chromatic fifths, skipping one string, ascending pairs"


def test_generate_is_pure() -> None:
    given = params()
    first, second = generate(BASS6, given), generate(BASS6, given)
    assert first == second
    assert given == PARAMS

    # The Score owns its parameters: a caller reusing the dictionary it passed in
    # must not be able to rewrite the record of what was generated.
    first.params["interval"] = 99
    assert given["interval"] == 3


# --------------------------------------------------------------------------
# The journey: low outer string to high outer string and back (spec §5)
# --------------------------------------------------------------------------


def test_the_journey_starts_low_reaches_the_top_and_returns() -> None:
    # The mirror of `test_scales.py`'s journey test: anchored on the low outer
    # string, the journey climbs to the opposite outer string and comes back.
    score = generate(BASS6, PARAMS)
    played = strings_of(score)
    top = len(BASS6.tuning) - 1
    assert played[0] == 0  # anchored on the low outer string
    assert min(played) == 0
    assert max(played) == top  # reaches the opposite outer string
    ascent = played[: len(played) // 2 + 1]
    assert max(ascent) == top  # the top is reached on the ascent
    # The retrograde returns: the final pair is the opening pair again.
    assert places_of(score)[-2:] == places_of(score)[:2]


def test_the_two_voices_cover_the_whole_instrument_with_no_gap() -> None:
    # The lower voice climbs the lower strings and the partner sits above it, so
    # together they use every string, outer to outer (spec §4/§5).
    score = generate(BASS6, PARAMS)
    assert sorted(set(strings_of(score))) == list(range(len(BASS6.tuning)))


def test_the_lower_voice_boxes_into_one_hand_position() -> None:
    # The lower voice is boxed (`journey.boxed_span`), so it sits under one hand
    # position — that is the shared fingering journey, not a full-neck shift.
    from melete.instrument import hand_span

    score = generate(BASS6, PARAMS)
    lower_frets = [lower.fret for lower, _upper in beats_of(score)]
    assert hand_span(lower_frets) <= BASS6.position_span


def test_the_lower_voice_climbs_string_by_string_to_the_partner_s_floor() -> None:
    # The lower voice starts on the low outer string and climbs to the string one
    # below the partner's outer string, using each string in between with no gap.
    score = generate(BASS6, PARAMS)
    distance = int(str(PARAMS["string_skip"])) + 1
    top_lower = len(BASS6.tuning) - 1 - distance
    lower_strings = sorted({lower.string for lower, _upper in beats_of(score)})
    assert lower_strings == list(range(top_lower + 1))


def test_the_opening_pair_is_anchored_on_the_low_string() -> None:
    # Deterministic all the way down (§9): A1 sits at fret 10 on the low B
    # string, and its diatonic third E2 sits at fret 9 on the string above.
    assert places_of(generate(BASS6, PARAMS))[:2] == [(0, 10), (1, 9)]


# --------------------------------------------------------------------------
# The key, which is a branch on `context` (spec §10a)
# --------------------------------------------------------------------------


def test_a_diatonic_context_is_spelled_against_its_root_and_scale() -> None:
    assert generate(BASS6, PARAMS).key == theory.Key(9, "ionian")


def test_a_chromatic_context_has_no_key() -> None:
    assert generate(BASS6, params(context="chromatic")).key is None


def test_the_tonic_is_a_pitch_class_and_not_the_root_pitch() -> None:
    for root, tonic in ((33, 9), (45, 9), (30, 6)):
        assert generate(BASS6, params(root=root)).key == theory.Key(tonic, "ionian")


def test_the_key_changes_how_the_notes_are_spelled() -> None:
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
    # `ascending_pairs` plays the lower note first, so the beats are (lower, upper).
    for lower, upper in beats_of(generate(BASS6, PARAMS)):
        assert upper.pitch - lower.pitch in (3, 4)


def test_chromatic_context_makes_every_interval_exact() -> None:
    for lower, upper in beats_of(generate(BASS6, params(context="chromatic"))):
        assert upper.pitch - lower.pitch == 4


def test_the_context_axis_is_realized_and_not_assumed() -> None:
    diatonic = {pair_interval(beat) for beat in beats_of(generate(BASS6, PARAMS))}
    chromatic_score = generate(BASS6, params(context="chromatic"))
    chromatic = {pair_interval(beat) for beat in beats_of(chromatic_score)}
    assert diatonic == {3, 4}
    assert chromatic == {4}


def test_the_diatonic_lower_notes_climb_the_scale_from_the_root() -> None:
    # The lower voice is the ascending scale unwound across the neck: the ascent's
    # lower notes are consecutive degrees of the scale, starting on the root.
    ascent = ascent_of(generate(BASS6, PARAMS))
    lowers = [lower_of(beat) for beat in ascent]
    assert lowers == ascending_scale(33, "ionian", len(ascent))


def test_the_diatonic_partner_is_a_scale_degree_above_the_lower_note() -> None:
    # A fourth is three scale degrees up, so the partner is the degree three
    # places past the lower note in the same ascending scale.
    ascent = ascent_of(generate(BASS6, params(interval=4)))
    degrees = ascending_scale(33, "ionian", len(ascent) + 3)
    for index, beat in enumerate(ascent):
        lower, upper = (beat[0], beat[1]) if beat[0].pitch < beat[1].pitch else (beat[1], beat[0])
        assert lower.pitch == degrees[index]
        assert upper.pitch == degrees[index + 3]


def test_the_chromatic_lower_notes_walk_by_semitone() -> None:
    ascent = ascent_of(generate(BASS6, params(context="chromatic", interval=5)))
    lowers = [lower_of(beat) for beat in ascent]
    assert lowers == list(range(33, 33 + len(ascent)))


@pytest.mark.parametrize(
    ("interval", "semitones"),
    [(2, 2), (3, 4), (4, 5), (5, 7), (6, 9)],
)
def test_a_chromatic_interval_takes_its_major_or_perfect_size(
    interval: int, semitones: int
) -> None:
    # A chromatic context has no scale to bend the interval, so every number is
    # its major (2nd, 3rd, 6th) or perfect (4th, 5th) size. Larger intervals run
    # the low partner off the neck from this root and are covered by the sweep.
    played = generate(BASS6, params(context="chromatic", interval=interval))
    assert {pair_interval(beat) for beat in beats_of(played)} == {semitones}


def test_a_diatonic_second_is_a_scale_step_and_not_always_a_tone() -> None:
    played = generate(BASS6, params(interval=2))
    assert {pair_interval(beat) for beat in beats_of(played)} == {1, 2}


def test_a_pentatonic_journey_still_covers_the_instrument() -> None:
    # The cycle length is emergent — as many pairs as fit one hand position — so
    # a five-note scale need not match a seven-note one; what the geometry
    # guarantees is that either still reaches outer to outer.
    score = generate(BASS6, params(scale_type="minor_pentatonic"))
    assert sorted(set(strings_of(score))) == list(range(len(BASS6.tuning)))


# --------------------------------------------------------------------------
# String topology: the reason this family exists (spec §7, decision #4)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("skip", "interval"), [("0", 3), ("1", 3), ("1", 5)])
def test_the_two_notes_of_a_pair_are_exactly_skip_plus_one_strings_apart(
    skip: str, interval: int
) -> None:
    # The axis is a distance between the notes of one pair, realized exactly:
    # `string_skip` 1 means one string is skipped over, not "at least".
    score = generate(BASS6, params(string_skip=skip, interval=interval))
    for lower, upper in beats_of(score):
        assert abs(upper.string - lower.string) == int(skip) + 1


def test_the_lower_note_of_each_pair_sits_on_the_lower_string() -> None:
    for lower, upper in beats_of(generate(BASS6, PARAMS)):
        assert lower.string < upper.string


@pytest.mark.parametrize("skip", ["0", "1"])
def test_the_partner_reaches_the_high_outer_string(skip: str) -> None:
    # The lower voice stops one skip below the top, so the partner is what
    # reaches the opposite outer string — the topology fix for defect 4.
    score = generate(BASS6, params(string_skip=skip, interval=5))
    top = len(BASS6.tuning) - 1
    uppers = {upper.string for _lower, upper in beats_of(score)}
    assert top in uppers


# --------------------------------------------------------------------------
# `pattern` orders the two notes inside a pair; the pairs always go up and down
# --------------------------------------------------------------------------


def test_ascending_pairs_play_the_lower_note_first() -> None:
    for lower, upper in beats_of(generate(BASS6, PARAMS)):
        assert lower.pitch < upper.pitch


def test_descending_pairs_play_the_upper_note_first() -> None:
    for first, second in beats_of(generate(BASS6, params(pattern="descending_pairs"))):
        assert first.pitch > second.pitch


def test_alternating_turns_every_other_pair_around() -> None:
    beats = beats_of(generate(BASS6, params(pattern="alternating")))
    # Even-numbered pairs lead with the lower note, odd-numbered with the upper.
    assert beats[0][0].pitch < beats[0][1].pitch
    assert beats[1][0].pitch > beats[1][1].pitch
    assert beats[2][0].pitch < beats[2][1].pitch


def test_a_pattern_reorders_without_changing_the_content() -> None:
    reference = generate(BASS6, PARAMS)
    for pattern in PATTERNS:
        other = generate(BASS6, params(pattern=pattern))
        assert sorted(pitches_of(other)) == sorted(pitches_of(reference))
        assert places_of(other) != [] and set(places_of(other)) == set(places_of(reference))


def test_the_journey_is_always_up_and_down() -> None:
    # There is no `direction` axis any more (epic #72): the pairs ascend and then
    # retrace their steps, and the closing pair is the opening pair once more.
    score = generate(BASS6, PARAMS)
    beats = beats_of(score)
    assert (beats[0][0].pitch, beats[0][1].pitch) == (beats[-1][0].pitch, beats[-1][1].pitch)


# --------------------------------------------------------------------------
# Unrealizable specifications raise, naming what could not be satisfied (§13)
# --------------------------------------------------------------------------


def test_a_partner_off_the_neck_raises() -> None:
    # A chromatic second skipping two strings needs the partner three strings above
    # but only two semitones higher, which runs it below the nut. §9 resamples this
    # rather than settling for a nearer string.
    with pytest.raises(ValueError, match=r"the partner \d+ needs fret -?\d+"):
        generate(BASS6, params(context="chromatic", string_skip="2", interval=2))


def test_a_lower_note_off_the_neck_raises() -> None:
    # C6 sits above the last fret of the low string, so the ascent cannot start.
    with pytest.raises(ValueError, match=r"the journey's first note \d+ needs fret \d+"):
        generate(BASS6, params(root=84))


def test_a_profile_too_narrow_for_the_skip_raises() -> None:
    # A three-string instrument leaves no room to skip two strings and still have
    # a lower voice to climb: the partner would sit off the top of the neck, so §9
    # resamples rather than narrowing the skip it was asked for.
    narrow = InstrumentProfile("bass3", (23, 28, 33), BASS6.fret_count)
    with pytest.raises(ValueError, match=r"leaving no room for the lower voice to climb"):
        generate(narrow, params(string_skip="2"))


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
    spec = params(context="chromatic")
    del spec["scale_type"]
    assert generate(BASS6, spec).key is None


def test_an_unknown_identifier_lists_the_accepted_values() -> None:
    with pytest.raises(ValueError, match=r"unknown context 'modal'.*diatonic"):
        generate(BASS6, params(context="modal"))


def test_an_integer_string_skip_is_not_an_identifier() -> None:
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
        # unrealizable draw is an outcome of the sweep and not a failure. What is
        # asserted is that it named what could not be satisfied (§13).
        assert "needs fret" in str(error) or "partner" in str(error) or "string_skip" in str(error)
        return

    assert_central_invariant(score)
    assert_spelling_sounds_correctly(score)
    for lower, upper in beats_of(score):
        assert abs(upper.string - lower.string) == int(string_skip) + 1


@pytest.mark.parametrize("pattern", PATTERNS)
def test_invariant_holds_across_patterns(pattern: str) -> None:
    score = generate(BASS6, params(pattern=pattern))
    assert_central_invariant(score)
    assert_spelling_sounds_correctly(score)


@pytest.mark.parametrize("scale_type", sorted(theory.SCALES))
def test_invariant_holds_across_every_scale(scale_type: str) -> None:
    score = generate(BASS6, params(scale_type=scale_type, interval=5))
    assert_central_invariant(score)
    assert_spelling_sounds_correctly(score)
    assert score.key == theory.Key(9, scale_type)


@pytest.mark.parametrize("profile_name", sorted(PROFILES))
def test_invariant_holds_across_the_profiles(profile_name: str) -> None:
    profile = PROFILES[profile_name]
    assert_central_invariant(generate(profile, PARAMS))
    assert sorted(set(strings_of(generate(profile, PARAMS)))) == list(range(len(profile.tuning)))


# --------------------------------------------------------------------------
# Layout hints (spec §4.2)
# --------------------------------------------------------------------------


def test_layout_hints_report_the_pair_as_the_cell() -> None:
    _score, hints = _generate(BASS6, PARAMS)
    assert hints.cell == 2


def test_the_journey_names_its_apex_seam_and_offers_apex_levers() -> None:
    # The pairs turn around on the top pair of the ascending pass, played once, so
    # the seam is that pair's last note — the end of the ascending pairs the pass
    # sounds — and the apex levers are always legal now the journey is up-and-down.
    score, hints = _generate(BASS6, PARAMS)
    ascending_pairs = len(ascent_of(score))
    assert hints.seam == 2 * ascending_pairs - 1
    assert {Lever.APEX_REPEAT, Lever.APEX_OMIT} <= set(hints.levers)
    assert {Lever.ADD_ONE, Lever.DROP_ONE} <= set(hints.levers)
