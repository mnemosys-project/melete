"""Tests for the Score-to-LilyPond emitter (spec §14).

Golden-file tests on the emitted **text**. Nothing here renders anything: the
emitter is specified never to learn that a binary exists, and `render` is the
only module that does (spec §4).

Two units are tested directly and first, because they are the two places where
a wrong answer still looks entirely plausible on the page:

* `duration_token` — decision #16 enforced at the boundary. A sounding triplet
  eighth is `1/12` and has no notehead; the raise is what makes storing
  sounding durations impossible and therefore what keeps the IR honest.
* `lily_string_number` — LilyPond numbers strings with 1 as the *highest* and
  the IR indexes 0 as the *lowest*. Get it wrong and every fret number lands on
  the wrong line while the tablature still reads as music.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from melete.instrument import resolve_profile
from melete.lilypond.emit import (
    Cover,
    duration_token,
    emit_book,
    emit_score,
    lily_string_number,
)
from melete.score import Note, Score, Tuplet

GOLDEN = Path(__file__).parent / "golden"

# The sample exercise: G minor pentatonic on a six-string bass, one accented
# note, fingerings on most, a triplet, and a dotted low B on the sixth string.
# It is small enough to read as a whole and still exercises every branch the
# note emitter has — accent, fingering, no fingering, tuplet, dotted value,
# both octave directions, and the lowest and highest strings.
_PARAMS: dict[str, object] = {
    "family": "scales",
    "root": 7,
    "scale_type": "minor_pentatonic",
    "traversal": "positional",
    "direction": "up",
    "subdivision": "eighth",
    "range_octaves": 2,
}


def sample_score(
    instruction: str = "",
    params: dict[str, object] | None = None,
    title: str = "G minor pentatonic",
) -> Score:
    """One exercise, fixed, for the golden files to pin."""
    eighth = Fraction(1, 8)
    return Score(
        title=title,
        instruction=instruction,
        instrument=resolve_profile("bass6"),
        time_signature=(4, 4),
        tempo_range=(80, 100),
        voice=[
            Note(pitch=43, string=4, fret=0, duration=Fraction(1, 4), finger=None, accent=True),
            Note(pitch=46, string=4, fret=3, duration=eighth, finger=3, accent=False),
            Note(pitch=48, string=4, fret=5, duration=eighth, finger=4, accent=False),
            Tuplet(
                ratio=(3, 2),
                notes=[
                    Note(pitch=50, string=4, fret=7, duration=eighth, finger=1, accent=False),
                    Note(pitch=53, string=4, fret=10, duration=eighth, finger=4, accent=False),
                    Note(pitch=55, string=4, fret=12, duration=eighth, finger=1, accent=False),
                ],
            ),
            Note(pitch=38, string=3, fret=0, duration=eighth, finger=None, accent=False),
            Note(pitch=35, string=2, fret=2, duration=eighth, finger=2, accent=False),
            Note(pitch=33, string=2, fret=0, duration=eighth, finger=None, accent=False),
            Note(pitch=28, string=1, fret=0, duration=eighth, finger=None, accent=False),
            Note(pitch=23, string=0, fret=0, duration=Fraction(3, 8), finger=None, accent=True),
        ],
        params=dict(params) if params is not None else dict(_PARAMS),
    )


# --------------------------------------------------------------------------
# duration_token — the written value, and only representable ones
# --------------------------------------------------------------------------


def test_plain_durations() -> None:
    assert duration_token(Fraction(1, 4)) == "4"
    assert duration_token(Fraction(1, 8)) == "8"
    assert duration_token(Fraction(1, 16)) == "16"


def test_whole_and_breve_ends_of_the_range() -> None:
    assert duration_token(Fraction(1, 1)) == "1"
    assert duration_token(Fraction(1, 64)) == "64"


def test_dotted_durations() -> None:
    assert duration_token(Fraction(3, 8)) == "4."
    assert duration_token(Fraction(7, 16)) == "4.."


def test_unrepresentable_duration_raises() -> None:
    # A triplet eighth *sounds* 1/12 and there is no twelfth note. The IR
    # stores the written 1/8 and lets Tuplet.ratio do the scaling (decision
    # #16); this raise is what stops the other convention creeping back in.
    with pytest.raises(ValueError, match="1/12"):
        duration_token(Fraction(1, 12))


def test_triple_dot_is_not_silently_accepted() -> None:
    # 15/16 is a triple-dotted half. LilyPond can engrave it, but nothing in
    # the pipeline produces one, and quietly widening the accepted set is how
    # an unwritable duration eventually slips through.
    with pytest.raises(ValueError, match="15/16"):
        duration_token(Fraction(15, 16))


def test_zero_and_negative_durations_raise() -> None:
    with pytest.raises(ValueError, match="0"):
        duration_token(Fraction(0))
    with pytest.raises(ValueError, match="-1/4"):
        duration_token(Fraction(-1, 4))


# --------------------------------------------------------------------------
# lily_string_number — the off-by-one that would engrave the wrong lines
# --------------------------------------------------------------------------


def test_string_index_maps_to_lilypond_string_number() -> None:
    # bass6: IR index 5 (highest, the C string) is LilyPond string 1.
    assert lily_string_number(index=5, string_count=6) == 1
    assert lily_string_number(index=0, string_count=6) == 6


def test_the_mapping_is_not_the_identity_anywhere_in_the_middle() -> None:
    assert [lily_string_number(index, 4) for index in range(4)] == [4, 3, 2, 1]


def test_an_index_the_instrument_has_no_string_for_raises() -> None:
    with pytest.raises(ValueError, match="4"):
        lily_string_number(index=4, string_count=4)
    with pytest.raises(ValueError, match="-1"):
        lily_string_number(index=-1, string_count=4)


# --------------------------------------------------------------------------
# The golden files — the emitted text, byte for byte
# --------------------------------------------------------------------------


@pytest.mark.parametrize("staves", ["both", "tab", "notation"])
def test_emitted_source_matches_the_golden_file(staves: str) -> None:
    assert emit_score(sample_score(), staves=staves) == (GOLDEN / f"{staves}.ly").read_text(
        encoding="utf-8"
    )


def test_book_matches_the_golden_file() -> None:
    scores = [
        sample_score(instruction="Keep the plucking hand even through the string crossings."),
        sample_score(
            params={
                "family": "arpeggios",
                "root": 2,
                "quality": "min7",
                "inversion": "first",
                "pattern": "broken",
                "start_fret": 5,
            },
            title="D minor 7th",
        ),
    ]
    cover = Cover(date="2026-08-09", instrument="bass6")
    assert emit_book(scores, cover) == (GOLDEN / "book.ly").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# The staff-mode branch (spec §10)
# --------------------------------------------------------------------------


def test_tab_only_mode_enables_full_rhythm_notation() -> None:
    # §10: TabStaff suppresses stems and beams by default, assuming a notation
    # staff above supplies the rhythm. With no staff above there is nothing to
    # read the rhythm from, so tab-only mode must ask for it explicitly.
    assert r"\tabFullNotation" in emit_score(sample_score(), staves="tab")


def test_both_mode_does_not_enable_it() -> None:
    # Plain tablature is correct when a notation staff carries the rhythm.
    assert r"\tabFullNotation" not in emit_score(sample_score(), staves="both")


def test_each_mode_emits_exactly_the_staves_it_names() -> None:
    both = emit_score(sample_score(), staves="both")
    assert r"\new Staff" in both
    assert r"\new TabStaff" in both

    tab = emit_score(sample_score(), staves="tab")
    assert r"\new Staff" not in tab
    assert r"\new TabStaff" in tab

    notation = emit_score(sample_score(), staves="notation")
    assert r"\new Staff" in notation
    assert r"\new TabStaff" not in notation


def test_an_unknown_staff_mode_names_the_accepted_values() -> None:
    # §13: never a silent fallback to a default for a misspelled key.
    with pytest.raises(ValueError, match="tablature") as exc:
        emit_score(sample_score(), staves="tablature")
    assert "both" in str(exc.value)


# --------------------------------------------------------------------------
# The notation conventions (spec §7, §10, §12)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("staves", ["both", "tab", "notation"])
def test_no_key_signature_and_explicit_accidentals(staves: str) -> None:
    # §10, decision #9: modal exercises must not imply a tonal centre, so
    # every altered tone prints its own accidental.
    assert r"\accidentalStyle forget" in emit_score(sample_score(), staves=staves)
    assert r"\key " not in emit_score(sample_score(), staves=staves)


@pytest.mark.parametrize("staves", ["both", "tab", "notation"])
def test_exercise_ends_with_a_final_barline(staves: str) -> None:
    # §7: the short final measure is accepted and closed, never padded with
    # rests — a player would read rests as musical content.
    out = emit_score(sample_score(), staves=staves)
    assert r'\bar "|."' in out


def test_instruction_never_reaches_an_exercise_page() -> None:
    # §12, decision #10: instructional prose lives on the cover page only.
    score = sample_score(instruction="Keep the plucking hand even.")
    for staves in ("both", "tab", "notation"):
        assert "plucking" not in emit_score(score, staves=staves)


def test_the_title_does_reach_the_page() -> None:
    assert "G minor pentatonic" in emit_score(sample_score(), staves="both")


def test_the_time_signature_and_tempo_range_are_engraved() -> None:
    out = emit_score(sample_score(), staves="both")
    assert r"\time 4/4" in out
    assert r"\tempo 4 = 80 - 100" in out


# --------------------------------------------------------------------------
# Notes, strings and tuplets
# --------------------------------------------------------------------------


def test_string_numbers_are_lilypond_numbers_not_ir_indices() -> None:
    out = emit_score(sample_score(), staves="tab")
    # The low B is IR string 0 and prints as LilyPond string 6; the open G is
    # IR string 4 and prints as string 2.
    assert r"b,,4.\6" in out
    assert r"g4\2" in out
    assert r"\0" not in out


def test_tunings_are_declared_at_written_pitch_low_string_first() -> None:
    # Bass guitar is written an octave above its sound, under \clef "bass_8".
    # The tuning must be declared the same way or every fret number is wrong.
    out = emit_score(sample_score(), staves="tab")
    assert r"stringTunings = \stringTuning <b,, e, a, d g c'>" in out


def test_the_notation_staff_uses_the_octave_transposing_bass_clef() -> None:
    assert r'\clef "bass_8"' in emit_score(sample_score(), staves="notation")


def test_fingerings_and_accents_are_engraved() -> None:
    out = emit_score(sample_score(), staves="notation")
    assert r"bes8\2-3" in out  # third finger
    assert r"g4\2->" in out  # accent, no fingering


def test_a_tuplet_uses_its_ratio_directly() -> None:
    assert r"\tuplet 3/2 {" in emit_score(sample_score(), staves="notation")


def test_a_dotted_written_value_reaches_the_page() -> None:
    assert r"b,,4.\6" in emit_score(sample_score(), staves="notation")


def test_pitches_carry_octave_marks_in_both_directions() -> None:
    out = emit_score(sample_score(), staves="notation")
    assert "c'8" in out  # above the reference octave
    assert r"a,8" in out  # below it
    assert " d8" in out  # in it, unmarked


# --------------------------------------------------------------------------
# The cover page (spec §12)
# --------------------------------------------------------------------------


def _cover_of(*scores: Score) -> str:
    return emit_book(list(scores), Cover(date="2026-08-09", instrument="bass6"))


def test_the_cover_is_a_bookpart_inside_the_same_book() -> None:
    # §12: one document from one render call, with no text-to-PDF dependency.
    out = _cover_of(sample_score())
    assert out.count(r"\book {") == 1
    assert out.count(r"\bookpart {") == 2
    assert out.index(r"\markup") < out.index(r"\score {")


def test_the_cover_carries_the_date_and_the_instrument() -> None:
    out = _cover_of(sample_score())
    assert "2026-08-09" in out
    assert "bass6" in out


def test_a_cover_entry_is_the_params_rendered_through_the_vocabulary() -> None:
    out = _cover_of(sample_score())
    assert "1. G minor pentatonic, scales, positional, ascending, eighths" in out
    assert "range octaves 2" in out  # a range axis has no display name to look up
    assert "80-100 bpm" in out


def test_a_cover_entry_carries_the_instruction_when_there_is_one() -> None:
    out = _cover_of(sample_score(instruction="Keep the plucking hand even."))
    assert r"\italic" in out
    assert "Keep the plucking hand even." in out


def test_entries_are_numbered_in_order() -> None:
    out = _cover_of(sample_score(), sample_score(), sample_score())
    assert out.index("1. ") < out.index("2. ") < out.index("3. ")


def test_a_chord_quality_reads_as_prose_too() -> None:
    out = _cover_of(sample_score(params={"root": 2, "quality": "min7"}))
    assert "1. D minor 7th, 80-100 bpm" in out


def test_an_exercise_with_no_tonal_root_still_gets_an_entry() -> None:
    out = _cover_of(sample_score(params={"family": "chromatic", "shift": "fret_per_cycle"}))
    assert "1. chromatic, up one fret per cycle, 80-100 bpm" in out


def test_a_scale_type_without_a_root_is_still_named() -> None:
    out = _cover_of(sample_score(params={"scale_type": "dorian"}))
    assert "1. Dorian, 80-100 bpm" in out


def test_quotes_in_prose_are_escaped_for_lilypond() -> None:
    out = _cover_of(sample_score(instruction='Say "one" per beat.'))
    assert r"\"one\"" in out


def test_an_unknown_value_on_a_known_axis_is_a_hard_error() -> None:
    # §13: the registry is the enumerated set, and a cover page printing a raw
    # identifier would be exactly the silent failure it exists to prevent.
    with pytest.raises(KeyError, match="lydian_b9"):
        _cover_of(sample_score(params={"scale_type": "lydian_b9"}))


def test_a_root_that_is_not_a_pitch_integer_is_a_hard_error() -> None:
    with pytest.raises(TypeError, match="root"):
        _cover_of(sample_score(params={"root": "G"}))


def test_a_root_outside_the_octave_is_a_hard_error() -> None:
    with pytest.raises(ValueError, match="12"):
        _cover_of(sample_score(params={"root": 12}))


def test_a_book_with_no_exercises_is_a_hard_error() -> None:
    with pytest.raises(ValueError, match="no exercises"):
        emit_book([], Cover(date="2026-08-09", instrument="bass6"))


def test_the_book_honours_the_staff_mode() -> None:
    scores = [sample_score()]
    cover = Cover(date="2026-08-09", instrument="bass6")
    assert r"\tabFullNotation" in emit_book(scores, cover, staves="tab")
    assert r"\tabFullNotation" not in emit_book(scores, cover)
