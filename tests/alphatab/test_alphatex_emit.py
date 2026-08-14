r"""Tests for the Score-to-alphaTex emitter (epic #46, Task 6).

Golden-file tests on the emitted **text** — the content-correctness gate.
Nothing here renders anything: like `lilypond/emit.py`, the emitter is specified
never to learn that a renderer binary exists (spec §4). Every token asserted was
confirmed against the installed `@coderline/alphatab` by Task 1's spike and
re-verified for this task by parsing probe alphaTex through the real
`AlphaTexImporter`; the goldens pin the exact text those tokens compose.

Two helpers are tested directly and first, the two places a wrong answer still
looks plausible on the page:

* `duration_token` — decision #16 enforced at the boundary. A sounding triplet
  eighth is `1/12` and has no notehead; the raise keeps the IR honest.
* `_alphatex_string` — alphaTex numbers strings with 1 as the *highest* and the
  IR indexes 0 as the *lowest*. Get it wrong and every fret lands on the wrong
  line while the tablature still reads as music.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import cast

import pytest

from melete import theory
from melete.alphatab import emit
from melete.alphatab.emit import (
    Cover,
    duration_token,
    emit_book,
    emit_score,
)
from melete.instrument import resolve_profile
from melete.score import Measure, Note, Score, Tuplet

GOLDEN = Path(__file__).parent / "golden"

_BASS6 = resolve_profile("bass6")


def _n(
    pitch: int,
    string: int,
    duration: Fraction,
    finger: int | None = None,
    *,
    accent: bool = False,
) -> Note:
    """A `Note` whose fret satisfies `pitch == tuning[string] + fret`.

    Deriving the fret keeps every fixture on the instrument invariant, so a note
    is never silently placed where the bass cannot play it.
    """
    return Note(
        pitch=pitch,
        string=string,
        fret=pitch - _BASS6.tuning[string],
        duration=duration,
        finger=finger,
        accent=accent,
    )


_QUARTER = Fraction(1, 4)
_EIGHTH = Fraction(1, 8)
_HALF = Fraction(1, 2)
_DOTTED_QUARTER = Fraction(3, 8)


#: A two-bar exercise in A harmonic minor, small enough to read whole and still
#: exercising every branch the note emitter has: an accent, a note with a finger
#: and one without, a triplet, a diatonic tone the signature spells (no glyph), a
#: chromatic tone forced explicitly (the raised seventh G#, which is also a tie
#: origin), a note split and tied across the barline, a dotted value, and both
#: the lowest and highest strings.
_SAMPLE_KEY = theory.Key(9, "harmonic_minor")


def sample_score(
    title: str = "A harmonic minor",
    instruction: str = "",
    key: theory.Key | None = _SAMPLE_KEY,
    params: dict[str, object] | None = None,
    *,
    repeat: bool = False,
) -> Score:
    """The fixed sample exercise the goldens pin."""
    return Score(
        title=title,
        instruction=instruction,
        instrument=_BASS6,
        time_signature=(4, 4),
        tempo_range=(80, 100),
        voice=[
            _n(33, 2, _QUARTER, finger=1, accent=True),  # A1, accented, fingered
            Tuplet(
                ratio=(3, 2),
                notes=[
                    _n(35, 2, _EIGHTH, finger=1),  # B1
                    _n(36, 2, _EIGHTH, finger=2),  # C2
                    _n(38, 3, _EIGHTH),  # D2, no finger
                ],
            ),
            _n(41, 3, _QUARTER, finger=4),  # F2, diatonic, spelled by the signature
            _n(44, 4, _HALF, finger=3),  # G#2, raised 7th (forced), overflows -> tied
            _n(40, 3, _DOTTED_QUARTER, finger=2),  # E2, dotted
            _n(48, 5, _EIGHTH),  # C3, highest string
            _n(23, 0, _QUARTER),  # B0, lowest string
        ],
        key=key,
        params=dict(params) if params is not None else {"root": 9, "scale_type": "harmonic_minor"},
        repeat=repeat,
    )


def dorian_score() -> Score:
    """One 4/4 bar of F# Dorian: a mode whose signature (`\\ks e`) spells it whole.

    Every tone is diatonic under the four-sharp signature, so not one accidental
    is forced — the golden then shows the signature doing all the spelling work.
    """
    return Score(
        title="F# Dorian",
        instruction="",
        instrument=_BASS6,
        time_signature=(4, 4),
        tempo_range=(72, 96),
        voice=[
            _n(42, 3, _QUARTER),  # F#2
            _n(44, 4, _QUARTER),  # G#2
            _n(45, 4, _QUARTER),  # A2
            _n(47, 4, _QUARTER),  # B2
        ],
        key=theory.Key(6, "dorian"),
        params={"root": 6, "scale_type": "dorian"},
    )


def chromatic_score() -> Score:
    """One 4/4 bar with no key: accidentals forced by direction, no signature.

    A keyless exercise (as the chromatic family produces) takes no `\\ks` and
    spells each altered tone explicitly — the empty-signature case of the same
    forced-accidental path.
    """
    return Score(
        title="chromatic",
        instruction="",
        instrument=_BASS6,
        time_signature=(4, 4),
        tempo_range=(60, 80),
        voice=[
            _n(36, 2, _QUARTER),  # C2, natural
            _n(37, 2, _QUARTER),  # C#2, forced sharp (ascending)
            _n(38, 3, _QUARTER),  # D2, natural
            _n(39, 3, _QUARTER),  # D#2, forced sharp
        ],
        key=None,
        params={"family": "chromatic"},
    )


# --------------------------------------------------------------------------
# duration_token — the written value, and only representable ones
# --------------------------------------------------------------------------


def test_plain_durations() -> None:
    assert duration_token(Fraction(1, 4)) == (4, 0)
    assert duration_token(Fraction(1, 8)) == (8, 0)
    assert duration_token(Fraction(1, 16)) == (16, 0)


def test_whole_and_short_ends_of_the_range() -> None:
    assert duration_token(Fraction(1, 1)) == (1, 0)
    assert duration_token(Fraction(1, 64)) == (64, 0)


def test_dotted_and_double_dotted_durations() -> None:
    assert duration_token(Fraction(3, 8)) == (4, 1)
    assert duration_token(Fraction(7, 16)) == (4, 2)


def test_unrepresentable_duration_raises() -> None:
    # A triplet eighth *sounds* 1/12 and there is no twelfth note. The IR stores
    # the written 1/8 and lets Tuplet.ratio scale it (decision #16); this raise
    # stops the other convention creeping back in.
    with pytest.raises(ValueError, match="1/12"):
        duration_token(Fraction(1, 12))


def test_triple_dot_is_not_silently_accepted() -> None:
    with pytest.raises(ValueError, match="15/16"):
        duration_token(Fraction(15, 16))


# --------------------------------------------------------------------------
# _alphatex_string — the reversed string convention
# --------------------------------------------------------------------------


def test_string_convention_is_reversed() -> None:
    # IR index 0 is the lowest string; alphaTex numbers from 1 as the highest.
    assert emit._alphatex_string(0, 6) == 6
    assert emit._alphatex_string(5, 6) == 1


def test_beat_effects_cover_tuplet_and_dots() -> None:
    # The beat-effect brace after a duration carries the tuplet ratio and dots.
    assert emit._beat_effects(0, None) == ""
    assert emit._beat_effects(1, None) == "{d}"
    assert emit._beat_effects(2, None) == "{dd}"
    assert emit._beat_effects(0, (3, 2)) == "{tu 3 2}"
    assert emit._beat_effects(2, (9, 4)) == "{tu 9 4 dd}"


def test_out_of_range_string_raises() -> None:
    with pytest.raises(ValueError, match="out of range"):
        emit._alphatex_string(6, 6)
    with pytest.raises(ValueError, match="out of range"):
        emit._alphatex_string(-1, 6)


# --------------------------------------------------------------------------
# _signature — the three cases, mirroring lilypond's _key_lines
# --------------------------------------------------------------------------


def test_no_key_takes_no_signature() -> None:
    assert emit._signature(None) == (None, {})


def test_symmetric_scale_takes_no_signature() -> None:
    # Whole-tone has no parent to inherit a signature from (tier 3, spec §10a).
    assert emit._signature(theory.Key(0, "whole_tone")) == (None, {})


def test_a_diatonic_mode_signs_with_its_own_collection() -> None:
    # Four sharps: the F-sharp Dorian collection is the same as E major's.
    name, signature = emit._signature(theory.Key(6, "dorian"))
    assert name == "e"
    assert signature == {"F": 1, "G": 1, "C": 1, "D": 1, "A": 0, "B": 0, "E": 0}


def test_a_parented_scale_signs_with_its_parent() -> None:
    # A harmonic minor prints A-minor's (empty) signature; the raised 7th is an
    # accidental, not part of the key.
    name, signature = emit._signature(theory.Key(9, "harmonic_minor"))
    assert name == "c"
    assert all(alteration == 0 for alteration in signature.values())


# --------------------------------------------------------------------------
# The single-note beat — the spike-confirmed string.fret + duration
# --------------------------------------------------------------------------


def test_single_note_emits_string_fret_and_duration() -> None:
    score = Score(
        title="one note",
        instruction="",
        instrument=_BASS6,
        time_signature=(4, 4),
        tempo_range=(80, 100),
        voice=[_n(48, 5, _QUARTER)],  # C3 on the highest string, fret 0
        key=theory.Key(0, "ionian"),
    )
    text = emit_score(score)
    assert "\\tuning(C3 G2 D2 A1 E1 B0)" in text
    assert f"\\instrument({emit.INSTRUMENT_BASS})" in text
    assert "\\clef bass" in text
    # C3 is IR string 5 (highest) -> alphaTex string 1, fret 0, quarter (.4).
    assert "0.1.4" in text


# --------------------------------------------------------------------------
# Nested tuplets flatten to a cumulative ratio (spike Q4)
# --------------------------------------------------------------------------


def test_nested_tuplet_flattens_to_the_cumulative_ratio() -> None:
    # `bar()` never produces a nested tuplet (families emit none, and its
    # sounding-time walk is flat), so the emitter is exercised on a Measure built
    # directly: an inner 3:2 inside an outer 3:2 makes the inner leaves 9:4.
    inner = Tuplet(ratio=(3, 2), notes=[_n(43, 4, _EIGHTH), _n(43, 4, _EIGHTH), _n(43, 4, _EIGHTH)])
    outer = Tuplet(
        ratio=(3, 2),
        notes=cast("list[Note]", [inner, _n(43, 4, _EIGHTH), _n(43, 4, _EIGHTH)]),
    )
    body = emit._measure_bodies([Measure(voice=[outer])], 6, None, {})[0]
    # Three inner leaves at the cumulative 9:4, two outer eighths at 3:2.
    assert body.count("{tu 9 4}") == 3
    assert body.count("{tu 3 2}") == 2


# --------------------------------------------------------------------------
# The golden files — the emitted text, byte for byte
# --------------------------------------------------------------------------


def test_exercise_matches_the_golden_file() -> None:
    assert emit_score(sample_score()) == (GOLDEN / "exercise.atex").read_text(encoding="utf-8")


def test_book_matches_the_golden_file() -> None:
    scores = [
        sample_score(instruction="Keep the fretting hand relaxed through the shift."),
        dorian_score(),
        chromatic_score(),
    ]
    cover = Cover(date="2026-08-12", instrument="bass6")
    assert emit_book(scores, cover) == (GOLDEN / "book.atex").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Spelling: the signature spells, the accidental forces (matching `forget`)
# --------------------------------------------------------------------------


def test_a_diatonic_tone_is_left_to_the_signature() -> None:
    # F natural in A harmonic minor is diatonic; nothing forces it. F2 is IR
    # string 3 -> alphaTex string 3, fret 3, quarter, fingered but with no `acc`.
    text = emit_score(sample_score())
    assert "3.3{lf 5}.4" in text
    assert "3.3{acc" not in text


def test_a_chromatic_tone_is_forced_explicitly() -> None:
    # The raised seventh G# is not in A minor's signature, so it is forced sharp.
    text = emit_score(sample_score())
    assert "acc #" in text


def test_the_book_gives_each_exercise_its_own_key() -> None:
    scores = [dorian_score(), chromatic_score()]
    text = emit_book(scores, Cover(date="2026-08-12", instrument="bass6"))
    assert "\\ks e" in text  # F# Dorian
    # The keyless exercise takes no signature of its own.
    assert text.count("\\ks ") == 1


def test_f_sharp_dorian_never_forces_a_flat() -> None:
    # Its notes are all diatonic under the sharp signature; not one flat glyph.
    text = emit_score(dorian_score())
    assert "acc b" not in text
    assert "\\ks e" in text


# --------------------------------------------------------------------------
# Ties across the barline (spike Q2)
# --------------------------------------------------------------------------


def test_a_note_crossing_the_barline_is_tied_onto_the_destination() -> None:
    text = emit_score(sample_score())
    # G#2 (IR string 4 -> alphaTex string 2) overflows bar 1 and continues in bar
    # 2 as a tie destination: '-' fret on the same string.
    assert f"{emit.TIE_FRET}.2." in text
    # The origin carries the forced accidental; the '-' destination carries none.
    assert f"{emit.TIE_FRET}.2.4{{" not in text


def test_the_barline_separates_the_two_measures() -> None:
    text = emit_score(sample_score())
    assert f" {emit.BAR_SEPARATOR} " in text


# --------------------------------------------------------------------------
# The exercise-level repeat (spec §5; melete#112)
# --------------------------------------------------------------------------


def test_a_score_that_does_not_repeat_emits_no_repeat_tokens() -> None:
    text = emit_score(sample_score())
    assert emit.REPEAT_OPEN not in text
    assert emit.REPEAT_CLOSE not in text


def test_a_repeated_exercise_opens_the_repeat_before_the_first_note() -> None:
    # `\ro` leads the first bar: it must sit ahead of the first beat token so the
    # repeat brackets the whole exercise (spike-confirmed: an opener at the start
    # of the bar sets the master bar's isRepeatStart).
    text = emit_score(sample_score(repeat=True))
    open_at = text.index(emit.REPEAT_OPEN)
    # The first note token is A1 on IR string 2 -> alphaTex string 4, fret 0.
    first_note_at = text.index("0.4{lf 2 ac}.4")
    assert open_at < first_note_at


def test_a_repeated_exercise_closes_the_repeat() -> None:
    # `\rc 2` closes the repeat on the last bar (two passes). The spike showed it
    # must LEAD the last bar rather than trail it — a trailing close spawns a
    # spurious empty master bar — so we assert containment, not a suffix.
    text = emit_score(sample_score(repeat=True))
    assert emit.REPEAT_CLOSE in text


def test_the_repeat_close_leads_the_last_bar_not_a_new_empty_one() -> None:
    # A trailing `\rc 2` makes alphaTab open an extra empty bar (spike finding).
    # Placing the close ahead of the last bar's beats keeps the bar count right,
    # so the close must appear after the final barline and before that bar's
    # first beat, never at the very end of the document.
    text = emit_score(sample_score(repeat=True)).rstrip("\n")
    last_barline = text.rindex(f" {emit.BAR_SEPARATOR} ")
    close_at = text.rindex(emit.REPEAT_CLOSE)
    assert close_at > last_barline
    assert not text.endswith(emit.REPEAT_CLOSE)


def test_a_single_bar_exercise_carries_both_repeat_tokens() -> None:
    # When the exercise is one bar, the open and close ride the same bar; both
    # tokens must still appear (spike-confirmed: one master bar with both
    # isRepeatStart and repeatCount set).
    score = Score(
        title="one bar",
        instruction="",
        instrument=_BASS6,
        time_signature=(4, 4),
        tempo_range=(80, 100),
        voice=[_n(48, 5, _QUARTER) for _ in range(4)],
        key=None,
        repeat=True,
    )
    text = emit_score(score)
    assert emit.REPEAT_OPEN in text
    assert emit.REPEAT_CLOSE in text


# --------------------------------------------------------------------------
# emit_book structure
# --------------------------------------------------------------------------


def test_the_book_carries_the_session_title_and_subtitle() -> None:
    text = emit_book([sample_score()], Cover(date="2026-08-12", instrument="bass6"))
    assert f'\\title "{emit.SESSION_TITLE}"' in text
    assert '\\subtitle "2026-08-12 - bass6"' in text


def test_each_exercise_is_a_numbered_section() -> None:
    text = emit_book([dorian_score(), chromatic_score()], Cover(date="2026-08-12", instrument="b"))
    assert '\\section "1. F# Dorian"' in text
    assert '\\section "2. chromatic"' in text


def test_emit_score_has_no_section_marker() -> None:
    assert "\\section" not in emit_score(sample_score())


def test_the_book_lays_out_one_system_per_exercise() -> None:
    # Each exercise its own system, so the `\section` titles can't overprint
    # (melete#138): the `\track` systemslayout carries one bar count per exercise,
    # in order. sample_score is 2 bars; dorian and chromatic are 1 bar each — all
    # within one system (<= BARS_PER_SYSTEM), so none of them wrap.
    text = emit_book(
        [sample_score(), dorian_score(), chromatic_score()],
        Cover(date="2026-08-12", instrument="bass6"),
    )
    assert '\\track "" { systemslayout 2 1 1 }' in text


def _n_bar_score(n_bars: int, title: str = "journey") -> Score:
    """An `n_bars`-bar 4/4 exercise: `4 * n_bars` quarter notes, one per beat.

    A journey longer than a single system, so its systemslayout has to wrap. The
    quarters divide the 4/4 bars evenly, so `bar()` yields exactly `n_bars` bars.
    """
    return Score(
        title=title,
        instruction="",
        instrument=_BASS6,
        time_signature=(4, 4),
        tempo_range=(80, 100),
        voice=[_n(33, 2, _QUARTER) for _ in range(4 * n_bars)],
        key=None,
        params={"family": "chromatic"},
    )


def test_a_long_exercise_wraps_into_evenly_split_systems() -> None:
    # A journey longer than one system is split into k = ceil(bars/BARS_PER_SYSTEM)
    # systems, each as even as possible (melete#181): 6 bars -> `3 3`, not `4 2`, so
    # alphaTab spaces the exercise evenly instead of cramming a full system then a
    # short one — and never leaves a lonely 1-bar line.
    text = emit_book([_n_bar_score(6)], Cover(date="2026-08-12", instrument="bass6"))
    assert '\\track "" { systemslayout 3 3 }' in text


def test_each_exercise_wraps_but_still_starts_a_fresh_system() -> None:
    # Each exercise's own bars are wrapped, and every exercise still begins a new
    # system at its boundary so `\section` titles never overprint (the melete#138
    # goal, preserved): a 6-bar then a 2-bar exercise emit `3 3 2` under the even
    # split (melete#181), the per-exercise chunk lists concatenated in order — never
    # fusing across the boundary.
    text = emit_book(
        [_n_bar_score(6, "a"), _n_bar_score(2, "b")],
        Cover(date="2026-08-12", instrument="bass6"),
    )
    assert '\\track "" { systemslayout 3 3 2 }' in text


@pytest.mark.parametrize(
    ("bar_count", "expected"),
    [
        (1, [1]),
        (2, [2]),
        (4, [4]),
        (5, [3, 2]),
        (6, [3, 3]),
        (8, [4, 4]),
        (9, [3, 3, 3]),
        (10, [4, 3, 3]),
        (13, [4, 3, 3, 3]),
        (14, [4, 4, 3, 3]),
    ],
)
def test_wrap_into_systems_distributes_evenly(bar_count: int, expected: list[int]) -> None:
    # melete#181: k = ceil(bars/BARS_PER_SYSTEM) systems, `bars` spread as evenly as
    # possible with the ceil-sized (larger) systems first. 9 -> [3, 3, 3], not the
    # old [4, 4, 1]; 10 -> [4, 3, 3]; 14 -> [4, 4, 3, 3].
    assert emit._wrap_into_systems(bar_count) == expected


@pytest.mark.parametrize("bar_count", range(2, 41))
def test_wrap_into_systems_never_leaves_a_lonely_one_bar_line(bar_count: int) -> None:
    # The whole point of melete#181: a 1-bar system reads as orphaned, so for any
    # exercise of two or more bars no system is ever a single bar. (A genuine 1-bar
    # exercise, bar_count == 1, is the only unavoidable [1] and is excluded here.)
    chunks = emit._wrap_into_systems(bar_count)
    assert 1 not in chunks
    assert sum(chunks) == bar_count
    assert all(1 <= chunk <= emit.BARS_PER_SYSTEM for chunk in chunks)


def test_wrap_into_systems_of_a_single_bar_is_the_only_one_bar_line() -> None:
    # A genuine 1-bar exercise is the one unavoidable [1]: k >= 1 systems means the
    # list is never empty.
    assert emit._wrap_into_systems(1) == [1]


def test_the_systems_layout_precedes_the_bar_stream() -> None:
    # The directive is track metadata and must lead the bars, not sit among them,
    # so it configures the track before any beat is read.
    text = emit_book([sample_score()], Cover(date="2026-08-12", instrument="bass6"))
    assert text.index("systemslayout") < text.index("\\section")


def test_emit_score_has_no_systems_layout() -> None:
    # A single exercise is one section; nothing can overprint, so no layout
    # directive is emitted (melete#138 is a book-only concern).
    assert "systemslayout" not in emit_score(sample_score())


def test_a_book_with_no_exercises_is_a_hard_error() -> None:
    with pytest.raises(ValueError, match="at least one exercise"):
        emit_book([], Cover(date="2026-08-12", instrument="bass6"))


def test_instruction_never_reaches_the_output() -> None:
    # Cover-page prose only (spec §12, decision #10): it is not in the alphaTex.
    marker = "Keep the fretting hand relaxed through the shift."
    assert marker not in emit_book([sample_score(instruction=marker)], Cover("2026-08-12", "bass6"))
