"""Tests for the Score IR and the contract at the seam.

The three tests under "The written-duration contract" are the point of this
module. Decision #16 makes `Note.duration` the *written* value and derives
sounding time from `Tuplet.ratio`; `rhythm.py` and `lilypond/emit.py` sit on
opposite sides of that seam, so a drift between them would render every tuplet
on every sheet at the wrong note value. These tests are what keep the two
honest about which value they are handling.

The remainder pins the structural rules the annotations state but cannot
enforce: one level of nesting, and no Score that could not be engraved.
"""

from dataclasses import FrozenInstanceError
from fractions import Fraction
from typing import Any, cast

import pytest

from melete.instrument import PROFILES
from melete.score import (
    Attack,
    Hand,
    Measure,
    Note,
    Score,
    Tuplet,
    Voice,
    _split_writable,
    bar,
    notes,
    sounding_duration,
)
from melete.theory import Key

QUARTER = Fraction(1, 4)
EIGHTH = Fraction(1, 8)
SIXTEENTH = Fraction(1, 16)

BASS6 = PROFILES["bass6"]


def _n(duration: Fraction = QUARTER) -> Note:
    """A note that exists only to carry a duration."""
    return Note(pitch=60, string=0, fret=0, duration=duration, finger=None, accent=False)


def _q() -> Note:
    """A quarter note."""
    return _n(QUARTER)


def _half() -> Note:
    """A half note."""
    return _n(Fraction(1, 2))


def _triplet() -> Tuplet:
    """Three written eighths in the time of two — one sounding quarter."""
    return Tuplet(ratio=(3, 2), notes=[_n(EIGHTH), _n(EIGHTH), _n(EIGHTH)])


def _score(voice: Voice | None = None, **overrides: Any) -> Score:
    """A minimal valid Score, with any field overridable."""
    fields: dict[str, Any] = {
        "title": "C Ionian, positional",
        "instruction": "Keep the plucking hand even.",
        "instrument": BASS6,
        "time_signature": (4, 4),
        "tempo_range": (80, 100),
        "voice": [_n()] if voice is None else voice,
    }
    fields.update(overrides)
    return Score(**fields)


# --------------------------------------------------------------------------
# The written-duration contract (decision #16)
# --------------------------------------------------------------------------


def test_plain_notes_sound_as_written() -> None:
    assert sounding_duration([_n(QUARTER)] * 4) == Fraction(1)


def test_triplet_notes_are_written_eighths_sounding_a_quarter() -> None:
    """Written: three eighths = 3/8. Sounding: 3/8 * 2/3 = 1/4."""
    assert sounding_duration([_triplet()]) == QUARTER


def test_mixed_voice_sums_correctly() -> None:
    assert sounding_duration([_n(QUARTER), _triplet()]) == Fraction(1, 2)


def test_an_empty_voice_sounds_for_no_time() -> None:
    assert sounding_duration([]) == Fraction(0)


def test_written_duration_is_not_the_sounding_duration_inside_a_tuplet() -> None:
    """The contract stated as a difference, since that is where drift shows."""
    trip = _triplet()
    written = sum((note.duration for note in trip.notes), Fraction(0))
    assert written == Fraction(3, 8)
    assert sounding_duration([trip]) == Fraction(1, 4)
    assert sounding_duration([trip]) != written


def test_every_note_in_a_tuplet_keeps_a_representable_written_value() -> None:
    """Why written durations win: 1/12 is not a notehead (spec §6)."""
    for note in _triplet().notes:
        assert note.duration == EIGHTH
        assert note.duration.numerator == 1
        assert note.duration.denominator & (note.duration.denominator - 1) == 0


def test_a_quintuplet_of_sixteenths_sounds_a_quarter() -> None:
    """Five in the time of four: 5/16 * 4/5 = 1/4. Exact, because Fraction."""
    quint = Tuplet(ratio=(5, 4), notes=[_n(SIXTEENTH)] * 5)
    assert sounding_duration([quint]) == QUARTER


def test_a_tuplet_may_hold_mixed_written_durations() -> None:
    """Long-short inside a triplet (§8): 1/4 + 1/8 written, times 2/3."""
    swung = Tuplet(ratio=(3, 2), notes=[_n(QUARTER), _n(EIGHTH)])
    assert sounding_duration([swung]) == QUARTER


def test_sounding_duration_returns_a_fraction_not_a_float() -> None:
    """Exactness is the reason for Fraction; a float total would drift."""
    assert isinstance(sounding_duration([_triplet(), _n(QUARTER)]), Fraction)


def test_a_full_bar_of_triplet_eighths_sounds_as_written_quarters_would() -> None:
    """Four triplets fill 4/4 exactly, which is what the §9 length gate reads."""
    assert sounding_duration([_triplet() for _ in range(4)]) == Fraction(1)


# --------------------------------------------------------------------------
# Tuplet nesting — invariant lifted (melete#87, epic #1 §4 correction)
# --------------------------------------------------------------------------


def test_tuplet_may_contain_a_tuplet() -> None:
    """The one-level rule was LilyPond-imposed; the port lifts it (melete#87)."""
    inner = _triplet()
    outer = Tuplet(ratio=(3, 2), notes=cast("list[Note]", [inner, _n(EIGHTH), _n(EIGHTH)]))
    assert outer.notes[0] is inner


# --------------------------------------------------------------------------
# Measure — one bar's voice (melete#87)
# --------------------------------------------------------------------------


def test_measure_wraps_a_voice() -> None:
    """A Measure holds one bar's flat voice; notes() reads through it."""
    voice: Voice = [_n(), _n()]
    measure = Measure(voice=voice)
    assert measure.voice == voice
    assert list(notes(measure.voice)) == voice


def test_measure_is_frozen_like_a_score() -> None:
    """Shallow-frozen: the voice field cannot be rebound."""
    measure = Measure(voice=[_n()])
    with pytest.raises(FrozenInstanceError):
        cast("Any", measure).voice = [_n(), _n()]


def test_a_tuplet_naming_the_offending_element_rejects_any_foreign_type() -> None:
    with pytest.raises(TypeError, match="element 1"):
        Tuplet(ratio=(3, 2), notes=cast("list[Note]", [_n(), "rest", _n()]))


def test_a_voice_holding_something_other_than_notes_and_tuplets_is_rejected() -> None:
    with pytest.raises(TypeError, match="element 0"):
        _score(voice=cast("Voice", [[_n()]]))


def test_a_voice_of_notes_and_tuplets_is_accepted() -> None:
    score = _score(voice=[_n(), _triplet(), _n()])
    assert len(score.voice) == 3


# --------------------------------------------------------------------------
# Note
# --------------------------------------------------------------------------


def test_note_tied_defaults_false_and_can_be_set() -> None:
    """`tied` is additive: it defaults False and round-trips when set (melete#87)."""
    assert _n().tied is False
    tied = Note(pitch=60, string=0, fret=0, duration=QUARTER, finger=None, accent=False, tied=True)
    assert tied.tied is True


# --------------------------------------------------------------------------
# Hand and Attack — two orthogonal Note fields for tapping (epic #67, §4)
# --------------------------------------------------------------------------


def test_hand_has_exactly_left_and_right() -> None:
    """The hand count is bounded at two on purpose (spec §11 decision 2)."""
    assert {member.name for member in Hand} == {"LEFT", "RIGHT"}


def test_attack_has_tapped_plucked_and_slurred() -> None:
    """The v1 articulation vocabulary (spec §4)."""
    assert {member.name for member in Attack} == {"TAPPED", "PLUCKED", "SLURRED"}


def test_a_default_note_is_left_and_plucked() -> None:
    """The defaults preserve every existing family and golden file (spec §4)."""
    note = _n()
    assert note.hand is Hand.LEFT
    assert note.attack is Attack.PLUCKED


def test_a_note_can_carry_a_right_hand_tap() -> None:
    """`hand` and `attack` vary independently — either hand can tap (spec §4)."""
    note = Note(
        pitch=60,
        string=0,
        fret=0,
        duration=QUARTER,
        finger=None,
        accent=False,
        hand=Hand.RIGHT,
        attack=Attack.TAPPED,
    )
    assert note.hand is Hand.RIGHT
    assert note.attack is Attack.TAPPED


def test_hand_and_attack_round_trip_every_combination() -> None:
    """Orthogonal fields: any hand pairs with any attack (spec §4)."""
    for hand in Hand:
        for attack in Attack:
            note = Note(
                pitch=60,
                string=0,
                fret=0,
                duration=QUARTER,
                finger=None,
                accent=False,
                hand=hand,
                attack=attack,
            )
            assert note.hand is hand
            assert note.attack is attack


def test_a_note_stores_both_pitch_and_position() -> None:
    """Decision #5: position is musical information, not a rendering detail."""
    note = Note(pitch=60, string=5, fret=12, duration=QUARTER, finger=3, accent=True)
    assert note.pitch == BASS6.tuning[note.string] + note.fret
    assert note.finger == 3
    assert note.accent is True


@pytest.mark.parametrize("finger", [1, 2, 3, 4, None])
def test_every_left_hand_finger_and_none_is_accepted(finger: int | None) -> None:
    assert Note(60, 0, 0, QUARTER, finger, accent=False).finger == finger


@pytest.mark.parametrize("finger", [0, 5, -1])
def test_a_finger_outside_one_to_four_is_rejected(finger: int) -> None:
    with pytest.raises(ValueError, match="finger must be 1-4"):
        Note(60, 0, 0, QUARTER, finger, accent=False)


@pytest.mark.parametrize("duration", [Fraction(0), Fraction(-1, 4)])
def test_a_note_without_positive_duration_is_rejected(duration: Fraction) -> None:
    with pytest.raises(ValueError, match="duration must be positive"):
        _n(duration)


def test_a_negative_string_index_is_rejected_rather_than_addressing_from_the_top() -> None:
    """Python would index the tuning from the high string and look correct."""
    with pytest.raises(ValueError, match="string index"):
        Note(60, -1, 0, QUARTER, None, accent=False)


def test_a_negative_fret_is_rejected() -> None:
    with pytest.raises(ValueError, match="fret must be at least 0"):
        Note(60, 0, -1, QUARTER, None, accent=False)


def test_fret_zero_is_the_open_string_and_is_accepted() -> None:
    assert Note(28, 0, 0, QUARTER, None, accent=False).fret == 0


# --------------------------------------------------------------------------
# Tuplet
# --------------------------------------------------------------------------


def test_a_tuplet_records_its_ratio_verbatim() -> None:
    """(3, 2) reads as three in the time of two, and maps to \\tuplet 3/2."""
    assert _triplet().ratio == (3, 2)


@pytest.mark.parametrize("ratio", [(0, 2), (3, 0), (-3, 2)])
def test_a_non_positive_tuplet_ratio_is_rejected(ratio: tuple[int, int]) -> None:
    with pytest.raises(ValueError, match="two positive integers"):
        Tuplet(ratio=ratio, notes=[_n(EIGHTH)])


def test_an_empty_tuplet_is_rejected() -> None:
    """`\\tuplet 3/2 { }` is not engravable, and sounds for no time."""
    with pytest.raises(ValueError, match="at least one note"):
        Tuplet(ratio=(3, 2), notes=[])


# --------------------------------------------------------------------------
# Score
# --------------------------------------------------------------------------


def test_a_score_carries_the_parameters_that_produced_it() -> None:
    """Spec §6: params travels inside the Score for the session log."""
    params = {"root": "d", "scale_type": "dorian"}
    assert _score(params=params).params == params


def test_params_defaults_to_a_fresh_dictionary_per_score() -> None:
    """default_factory, not a shared mutable default."""
    first, second = _score(), _score()
    assert first.params == {}
    assert first.params is not second.params


def test_the_instruction_may_be_empty_when_a_family_supplies_no_cue() -> None:
    assert _score(instruction="").instruction == ""


def test_the_instrument_profile_travels_with_the_score() -> None:
    assert _score().instrument is BASS6


@pytest.mark.parametrize("time_signature", [(0, 4), (4, 0), (-4, 4)])
def test_a_non_positive_time_signature_is_rejected(time_signature: tuple[int, int]) -> None:
    with pytest.raises(ValueError, match="two positive integers"):
        _score(time_signature=time_signature)


def test_a_time_signature_denominator_that_is_not_a_note_value_is_rejected() -> None:
    """The lower number names a note value, and there is no third note."""
    with pytest.raises(ValueError, match="power of two"):
        _score(time_signature=(4, 3))


@pytest.mark.parametrize("time_signature", [(4, 4), (3, 4), (5, 4), (6, 8), (7, 8), (12, 8)])
def test_every_time_signature_in_the_rhythm_axis_is_accepted(
    time_signature: tuple[int, int],
) -> None:
    """Spec §8 enumerates exactly these."""
    assert _score(time_signature=time_signature).time_signature == time_signature


@pytest.mark.parametrize("tempo_range", [(0, 100), (-80, 100)])
def test_a_non_positive_tempo_is_rejected(tempo_range: tuple[int, int]) -> None:
    with pytest.raises(ValueError, match="tempo must be positive"):
        _score(tempo_range=tempo_range)


def test_a_tempo_range_running_backwards_is_rejected() -> None:
    with pytest.raises(ValueError, match="slowest to fastest"):
        _score(tempo_range=(100, 80))


def test_a_single_tempo_expressed_as_an_equal_range_is_accepted() -> None:
    assert _score(tempo_range=(90, 90)).tempo_range == (90, 90)


def test_an_empty_voice_is_accepted() -> None:
    """The IR does not decide what counts as an exercise; §9's gate does."""
    assert _score(voice=[]).voice == []


# --------------------------------------------------------------------------
# The key (spec §10a)
# --------------------------------------------------------------------------


def test_a_score_carries_a_key() -> None:
    assert _score(key=Key(6, "dorian")).key == Key(6, "dorian")


def test_key_is_optional_because_chromatic_exercises_have_none() -> None:
    """`None` is a value — no tonal center — and not a missing field."""
    assert _score(key=None).key is None


def test_a_score_that_states_no_key_has_none() -> None:
    assert _score().key is None


@pytest.mark.parametrize("tonic", [0, 6, 11])
def test_every_pitch_class_is_an_accepted_tonic(tonic: int) -> None:
    assert _score(key=Key(tonic, "ionian")).key == Key(tonic, "ionian")


@pytest.mark.parametrize("tonic", [12, -1, 60])
def test_an_out_of_range_tonic_is_rejected(tonic: int) -> None:
    """A tonic is a pitch class, not an absolute pitch: 60 is not middle C."""
    with pytest.raises(ValueError, match="tonic"):
        _score(key=Key(tonic, "dorian"))


def test_an_unknown_scale_type_in_a_key_is_rejected() -> None:
    with pytest.raises(KeyError, match="dorain"):
        _score(key=Key(0, "dorain"))


def test_the_rejected_scale_type_is_named_alongside_what_is_accepted() -> None:
    """§13: an error names the value and the values it could have been."""
    with pytest.raises(KeyError) as raised:
        _score(key=Key(0, "dorain"))
    assert "dorian" in str(raised.value)


# --------------------------------------------------------------------------
# The exercise-level repeat (spec §5)
# --------------------------------------------------------------------------


def test_a_score_does_not_repeat_by_default() -> None:
    """A repeat is opt-in: an exercise plays once unless a family asks for it."""
    assert _score().repeat is False


def test_a_score_can_be_marked_to_repeat() -> None:
    """The whole exercise wraps in a repeat when the family sets the flag."""
    assert _score(repeat=True).repeat is True


# --------------------------------------------------------------------------
# Frozen shallowly, and not hashable
# --------------------------------------------------------------------------


def _rebind(target: object, field_name: str, value: object) -> None:
    """Assign through the runtime, which is where frozen-ness is enforced.

    Written as an assignment the type checkers would reject the statement
    outright, and a silenced error proves nothing about what happens when the
    code actually runs.
    """
    setattr(target, field_name, value)


def test_a_note_cannot_be_rebound() -> None:
    with pytest.raises(FrozenInstanceError):
        _rebind(_n(), "duration", EIGHTH)


def test_a_tuplet_cannot_be_rebound() -> None:
    with pytest.raises(FrozenInstanceError):
        _rebind(_triplet(), "ratio", (5, 4))


def test_a_score_cannot_be_rebound() -> None:
    with pytest.raises(FrozenInstanceError):
        _rebind(_score(), "title", "other")


def test_a_note_is_hashable_being_made_of_scalars() -> None:
    assert hash(_n()) == hash(_n())


def test_a_tuplet_is_not_hashable_and_nothing_needs_it_to_be() -> None:
    """§6 specifies a list; hashing is not loosened to work around that."""
    with pytest.raises(TypeError):
        hash(_triplet())


def test_a_score_is_not_hashable_and_nothing_needs_it_to_be() -> None:
    with pytest.raises(TypeError):
        hash(_score())


def test_freezing_is_shallow_so_contents_stay_mutable() -> None:
    """Stated as a test so no caller mistakes frozen for deeply immutable."""
    score = _score()
    score.params["root"] = "d"
    assert score.params == {"root": "d"}


# --------------------------------------------------------------------------
# Equality
# --------------------------------------------------------------------------


def test_two_notes_with_the_same_fields_are_equal() -> None:
    assert _n() == _n()


def test_notes_differing_only_in_written_duration_are_not_equal() -> None:
    assert _n(QUARTER) != _n(EIGHTH)


def test_two_scores_with_the_same_fields_are_equal() -> None:
    assert _score() == _score()


# --------------------------------------------------------------------------
# The barring pass (melete#88)
# --------------------------------------------------------------------------


def test_bar_exact_fit_is_one_measure() -> None:
    """Four quarters fill 4/4 exactly: one measure, every note untied."""
    measures = bar([_q(), _q(), _q(), _q()], (4, 4))
    assert len(measures) == 1
    assert len(measures[0].voice) == 4
    for note in measures[0].voice:
        assert isinstance(note, Note)
        assert not note.tied


def test_bar_splits_and_ties_across_the_barline() -> None:
    """A half note overflowing 4/4 splits into a tied quarter and a quarter."""
    measures = bar([_q(), _q(), _q(), _half()], (4, 4))
    assert len(measures) == 2

    tail = measures[0].voice[-1]
    head = measures[1].voice[0]
    assert isinstance(tail, Note)
    assert isinstance(head, Note)

    assert tail.duration == QUARTER
    assert tail.tied is True

    assert head.duration == QUARTER
    assert head.tied is False  # the original half note was untied
    assert head.pitch == tail.pitch


def test_bar_a_split_preserves_position_and_moves_the_accent_to_the_first_piece() -> None:
    """`string`/`fret`/`finger` ride every piece; `accent` rides only the first."""
    accented = Note(pitch=64, string=2, fret=5, duration=Fraction(1, 2), finger=3, accent=True)
    measures = bar([_q(), _q(), _q(), accented], (4, 4))

    tail = measures[0].voice[-1]
    head = measures[1].voice[0]
    assert isinstance(tail, Note)
    assert isinstance(head, Note)

    for piece in (tail, head):
        assert piece.string == 2
        assert piece.fret == 5
        assert piece.finger == 3

    assert tail.accent is True  # the accent stays on the sounded attack
    assert head.accent is False


def test_bar_short_final_measure_is_not_padded() -> None:
    """Spec §7: the last measure closes under-full rather than being padded."""
    measures = bar([_q(), _q(), _q()], (4, 4))
    assert len(measures) == 1
    assert sounding_duration(measures[0].voice) == Fraction(3, 4)


def test_bar_spans_a_note_across_more_than_one_full_bar() -> None:
    """A 9/4 note fills two whole bars (tied) and leaves a quarter in a third."""
    measures = bar([_n(Fraction(9, 4))], (4, 4))
    assert len(measures) == 3

    first = measures[0].voice[0]
    second = measures[1].voice[0]
    last = measures[2].voice[0]
    assert isinstance(first, Note)
    assert isinstance(second, Note)
    assert isinstance(last, Note)

    assert (first.duration, first.tied) == (Fraction(1), True)
    assert (second.duration, second.tied) == (Fraction(1), True)
    assert (last.duration, last.tied) == (QUARTER, False)


def test_bar_a_tuplet_that_fits_passes_through_whole() -> None:
    """Four triplets sound four quarters and fill 4/4 as intact tuplets."""
    triplets = [_triplet() for _ in range(4)]
    measures = bar(list(triplets), (4, 4))
    assert len(measures) == 1
    assert measures[0].voice == triplets
    assert all(isinstance(item, Tuplet) for item in measures[0].voice)


def test_bar_does_not_descend_into_a_tuplet() -> None:
    """A Tuplet (the voice's nested form) is placed whole, never flattened."""
    trip = _triplet()
    measures = bar([_q(), trip, _q()], (4, 4))
    assert len(measures) == 1
    assert measures[0].voice[1] is trip  # the same object, not its eighths


def test_bar_a_tuplet_that_would_cross_a_barline_is_rejected() -> None:
    """A tuplet is indivisible; one straddling a barline is an error, not a split."""
    with pytest.raises(ValueError, match="cross a barline"):
        bar([_q(), _q(), _q(), _n(EIGHTH), _triplet()], (4, 4))


def test_bar_of_an_empty_voice_is_no_measures() -> None:
    assert bar([], (4, 4)) == []


# --------------------------------------------------------------------------
# Writable-duration decomposition (melete#88) — mirrors emit.py's writable set
# --------------------------------------------------------------------------


def test_split_writable_leaves_a_single_writable_value_alone() -> None:
    assert _split_writable(QUARTER) == [QUARTER]
    assert _split_writable(Fraction(1)) == [Fraction(1)]
    assert _split_writable(Fraction(3, 4)) == [Fraction(3, 4)]  # a dotted half


def test_split_writable_decomposes_a_remainder_into_the_fewest_tied_pieces() -> None:
    """5/8 is not one note value: largest-first gives 1/2 + 1/8."""
    assert _split_writable(Fraction(5, 8)) == [Fraction(1, 2), Fraction(1, 8)]


def test_split_writable_rejects_a_non_dyadic_duration() -> None:
    """A sounding tuplet value like 1/12 has no notehead and is not split."""
    with pytest.raises(ValueError, match="dyadic"):
        _split_writable(Fraction(1, 3))
