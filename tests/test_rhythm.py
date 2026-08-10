"""Tests for the rhythm modifier (spec §8, §14, decision #16).

Two assertions carry this module. The first is that every written duration it
produces is a **representable notehead** — a plain, dotted or double-dotted
power of two — because `Note.duration` is what gets engraved and there is no
twelfth note to engrave. The second is that a `note_value_pattern`
**redistributes** time rather than adding or removing any: `long_short` and
`straight` must sound for exactly as long. If that drifts, the exercise no
longer fits the cycle length that §7's `max_notes` gate and §14's duration
test both reason about.

The rest pins the four axes of §8 and the errors §13 requires to be loud.
"""

from dataclasses import replace
from fractions import Fraction
from typing import Any

import pytest

from melete import rhythm, vocabulary
from melete.instrument import PROFILES
from melete.score import Note, Score, Tuplet, Voice, sounding_duration

BASS6 = PROFILES["bass6"]

#: Real elapsed time of one note at each subdivision (decision #16). Stated
#: independently of `rhythm.SUBDIVISIONS` so the cycle-length test compares
#: the implementation against a second source rather than against itself.
SOUNDING = {
    "quarter": Fraction(1, 4),
    "eighth": Fraction(1, 8),
    "sixteenth": Fraction(1, 16),
    "triplet_eighth": Fraction(1, 12),
    "sextuplet": Fraction(1, 24),
    "quintuplet": Fraction(1, 20),
}

SUBDIVISIONS = sorted(SOUNDING)
NOTE_VALUE_PATTERNS = sorted(vocabulary.AXES["note_value_pattern"])

#: A notehead is a power of two, optionally dotted (x3/2) or double-dotted
#: (x7/4). Dividing the numerator out of a written duration must therefore
#: leave one of these denominators, and nothing else is engravable.
NOTE_VALUES = (1, 2, 4, 8, 16, 32, 64, 128, 256)


def _note(index: int) -> Note:
    """A note carrying a distinct pitch and position, so identity is checkable."""
    return Note(
        pitch=36 + index,
        string=index % 6,
        fret=index,
        duration=Fraction(1, 4),
        finger=1 + index % 4,
        accent=False,
    )


def _score(count: int = 8, voice: Voice | None = None) -> Score:
    """A score whose voice is `count` plain notes, standing in for a family."""
    return Score(
        title="C Ionian, positional",
        instruction="Keep the plucking hand even.",
        instrument=BASS6,
        time_signature=(4, 4),
        tempo_range=(80, 100),
        voice=[_note(index) for index in range(count)] if voice is None else voice,
        params={"family": "scales", "root": 0},
    )


def _params(**overrides: Any) -> dict[str, Any]:
    """The four axes of §8, with any of them overridable."""
    params: dict[str, Any] = {
        "subdivision": "eighth",
        "time_signature": "4_4",
        "accent_pattern": "none",
        "note_value_pattern": "straight",
    }
    params.update(overrides)
    return params


def _notes(voice: Voice) -> list[Note]:
    """Every note of `voice` in order, tuplet grouping discarded."""
    flat: list[Note] = []
    for item in voice:
        if isinstance(item, Tuplet):
            flat.extend(item.notes)
        else:
            flat.append(item)
    return flat


def _durations(score: Score) -> list[Fraction]:
    return [note.duration for note in _notes(score.voice)]


# --------------------------------------------------------------------------
# The written-duration contract (decision #16)
# --------------------------------------------------------------------------


def test_triplet_eighths_produce_a_tuplet_of_written_eighths() -> None:
    """Three written eighths under a (3, 2) ratio, sounding one quarter."""
    out = rhythm.apply(_score(6), _params(subdivision="triplet_eighth"))

    first = out.voice[0]
    assert isinstance(first, Tuplet)
    assert first.ratio == (3, 2)
    assert [note.duration for note in first.notes] == [Fraction(1, 8)] * 3
    assert sounding_duration([first]) == Fraction(1, 4)


@pytest.mark.parametrize("subdivision", SUBDIVISIONS)
@pytest.mark.parametrize("note_value_pattern", NOTE_VALUE_PATTERNS)
def test_every_written_duration_is_a_representable_notehead(
    subdivision: str,
    note_value_pattern: str,
) -> None:
    out = rhythm.apply(
        _score(9),
        _params(subdivision=subdivision, note_value_pattern=note_value_pattern),
    )

    for duration in _durations(out):
        assert duration.numerator in (1, 3, 7)  # plain, dotted, double-dotted
        assert (duration / duration.numerator).denominator in NOTE_VALUES


@pytest.mark.parametrize("subdivision", SUBDIVISIONS)
def test_sounding_duration_equals_the_cycle_length(subdivision: str) -> None:
    """§14: the voice sounds for exactly one note per note, at the subdivision."""
    out = rhythm.apply(_score(12), _params(subdivision=subdivision))

    note_count = len(_notes(out.voice))
    assert note_count == 12
    assert sounding_duration(out.voice) == note_count * SOUNDING[subdivision]


@pytest.mark.parametrize("subdivision", SUBDIVISIONS)
@pytest.mark.parametrize("count", [8, 9])
def test_a_note_value_pattern_preserves_total_sounding_duration(
    subdivision: str,
    count: int,
) -> None:
    """The assertion that matters: swing redistributes time, never adds it."""
    straight = rhythm.apply(_score(count), _params(subdivision=subdivision))
    long_short = rhythm.apply(
        _score(count),
        _params(subdivision=subdivision, note_value_pattern="long_short"),
    )
    short_long = rhythm.apply(
        _score(count),
        _params(subdivision=subdivision, note_value_pattern="short_long"),
    )

    total = sounding_duration(straight.voice)
    assert sounding_duration(long_short.voice) == total
    assert sounding_duration(short_long.voice) == total
    assert total == count * SOUNDING[subdivision]


@pytest.mark.parametrize("subdivision", ["triplet_eighth", "sextuplet", "quintuplet"])
def test_each_tuplet_still_holds_its_nominal_written_value(subdivision: str) -> None:
    """A swung tuplet is still three-in-the-time-of-two, not seven-eighths of it."""
    straight = rhythm.apply(_score(12), _params(subdivision=subdivision))
    swung = rhythm.apply(
        _score(12),
        _params(subdivision=subdivision, note_value_pattern="long_short"),
    )

    for plain, swing in zip(straight.voice, swung.voice, strict=True):
        assert sounding_duration([plain]) == sounding_duration([swing])


# --------------------------------------------------------------------------
# §8: subdivision
# --------------------------------------------------------------------------


def test_the_subdivision_table_covers_the_registry_exactly() -> None:
    assert sorted(rhythm.SUBDIVISIONS) == vocabulary.accepted("subdivision")


@pytest.mark.parametrize(("subdivision", "written"), [("quarter", 4), ("sixteenth", 16)])
def test_a_plain_subdivision_is_not_wrapped_in_a_tuplet(subdivision: str, written: int) -> None:
    out = rhythm.apply(_score(4), _params(subdivision=subdivision))

    assert all(isinstance(item, Note) for item in out.voice)
    assert _durations(out) == [Fraction(1, written)] * 4


def test_a_tuplet_subdivision_groups_by_its_numerator() -> None:
    out = rhythm.apply(_score(12), _params(subdivision="sextuplet"))

    assert len(out.voice) == 2
    assert all(isinstance(item, Tuplet) and item.ratio == (6, 4) for item in out.voice)


def test_a_short_final_group_stays_a_tuplet() -> None:
    """Seven notes at triplet eighths is 3 + 3 + 1, and the last note is still 1/12."""
    out = rhythm.apply(_score(7), _params(subdivision="triplet_eighth"))

    assert [len(item.notes) for item in out.voice if isinstance(item, Tuplet)] == [3, 3, 1]
    assert sounding_duration(out.voice) == 7 * Fraction(1, 12)


def test_an_input_tuplet_is_regrouped_rather_than_nested() -> None:
    """Rhythm owns the grouping; whatever a family sent arrives flattened."""
    incoming: Voice = [
        Tuplet(ratio=(3, 2), notes=[_note(0), _note(1), _note(2)]),
        _note(3),
    ]
    out = rhythm.apply(_score(voice=incoming), _params(subdivision="eighth"))

    assert out.voice == [replace(_note(index), duration=Fraction(1, 8)) for index in range(4)]


# --------------------------------------------------------------------------
# §8: time_signature
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("identifier", "meter"),
    [
        ("4_4", (4, 4)),
        ("3_4", (3, 4)),
        ("5_4", (5, 4)),
        ("6_8", (6, 8)),
        ("7_8", (7, 8)),
        ("12_8", (12, 8)),
    ],
)
def test_the_time_signature_identifier_becomes_the_score_meter(
    identifier: str,
    meter: tuple[int, int],
) -> None:
    out = rhythm.apply(_score(4), _params(time_signature=identifier))

    assert out.time_signature == meter


# --------------------------------------------------------------------------
# §8: accent_pattern
# --------------------------------------------------------------------------


def test_no_accent_pattern_accents_nothing() -> None:
    out = rhythm.apply(_score(9), _params(accent_pattern="none"))

    assert [note.accent for note in _notes(out.voice)] == [False] * 9


def test_accent_every_3() -> None:
    out = rhythm.apply(_score(9), _params(accent_pattern="every_3"))

    accents = [note.accent for note in _notes(out.voice)]
    assert accents[::3] == [True] * len(accents[::3])
    assert accents == [True, False, False] * 3


def test_accent_every_5() -> None:
    out = rhythm.apply(_score(11), _params(accent_pattern="every_5"))

    accents = [note.accent for note in _notes(out.voice)]
    assert [index for index, accent in enumerate(accents) if accent] == [0, 5, 10]


def test_a_displaced_accent_falls_one_note_after_the_group() -> None:
    out = rhythm.apply(_score(9), _params(accent_pattern="displaced"))

    accents = [note.accent for note in _notes(out.voice)]
    assert [index for index, accent in enumerate(accents) if accent] == [1, 5]


def test_accents_are_indexed_across_tuplet_boundaries() -> None:
    """The accent runs over the notes, not over the groups they were packed into."""
    out = rhythm.apply(_score(9), _params(subdivision="sextuplet", accent_pattern="every_3"))

    assert [note.accent for note in _notes(out.voice)] == [True, False, False] * 3


def test_an_incoming_accent_is_replaced_not_merged() -> None:
    accented: Voice = [replace(_note(index), accent=True) for index in range(4)]
    out = rhythm.apply(_score(voice=accented), _params(accent_pattern="none"))

    assert [note.accent for note in _notes(out.voice)] == [False] * 4


# --------------------------------------------------------------------------
# §8: note_value_pattern
# --------------------------------------------------------------------------


def test_long_short_alternates_written_durations() -> None:
    out = rhythm.apply(_score(8), _params(subdivision="eighth", note_value_pattern="long_short"))

    durations = _durations(out)
    assert durations[0] > durations[1]
    assert durations[0::2] == [durations[0]] * len(durations[0::2])
    assert durations == [Fraction(3, 16), Fraction(1, 16)] * 4


def test_short_long_is_the_mirror_of_long_short() -> None:
    long_short = rhythm.apply(_score(8), _params(note_value_pattern="long_short"))
    short_long = rhythm.apply(_score(8), _params(note_value_pattern="short_long"))

    assert _durations(short_long)[:2] == list(reversed(_durations(long_short)[:2]))
    assert _durations(short_long) == list(reversed(_durations(long_short)))


def test_straight_leaves_every_note_at_the_subdivision() -> None:
    out = rhythm.apply(_score(8), _params(subdivision="eighth"))

    assert _durations(out) == [Fraction(1, 8)] * 8


def test_an_unpaired_final_note_keeps_the_straight_value() -> None:
    """A pair needs two notes; the leftover is the only value that adds no time."""
    out = rhythm.apply(_score(5), _params(subdivision="eighth", note_value_pattern="long_short"))

    assert _durations(out) == [
        Fraction(3, 16),
        Fraction(1, 16),
        Fraction(3, 16),
        Fraction(1, 16),
        Fraction(1, 8),
    ]


def test_the_pairing_restarts_inside_each_tuplet() -> None:
    """Odd groups leave their own leftover, so each tuplet keeps its nominal value."""
    out = rhythm.apply(
        _score(6),
        _params(subdivision="triplet_eighth", note_value_pattern="long_short"),
    )

    assert _durations(out) == [Fraction(3, 16), Fraction(1, 16), Fraction(1, 8)] * 2


# --------------------------------------------------------------------------
# What the modifier carries through
# --------------------------------------------------------------------------


def test_pitch_position_and_fingering_survive_untouched() -> None:
    out = rhythm.apply(_score(6), _params(subdivision="sixteenth", accent_pattern="every_3"))

    for index, note in enumerate(_notes(out.voice)):
        assert (note.pitch, note.string, note.fret, note.finger) == (
            36 + index,
            index % 6,
            index,
            1 + index % 4,
        )


def test_the_rhythm_axes_join_the_params_the_session_log_records() -> None:
    out = rhythm.apply(_score(4), _params(subdivision="triplet_eighth", accent_pattern="every_3"))

    assert out.params == {
        "family": "scales",
        "root": 0,
        "subdivision": "triplet_eighth",
        "time_signature": "4_4",
        "accent_pattern": "every_3",
        "note_value_pattern": "straight",
    }


def test_the_incoming_score_is_left_alone() -> None:
    score = _score(4)
    before = list(score.voice)

    rhythm.apply(score, _params(subdivision="sixteenth"))

    assert score.voice == before
    assert score.params == {"family": "scales", "root": 0}


def test_the_title_instruction_instrument_and_tempo_are_untouched() -> None:
    score = _score(4)
    out = rhythm.apply(score, _params())

    assert (out.title, out.instruction, out.instrument, out.tempo_range) == (
        score.title,
        score.instruction,
        score.instrument,
        score.tempo_range,
    )


# --------------------------------------------------------------------------
# §13: loud failures, never a silent fallback
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "axis",
    ["subdivision", "time_signature", "accent_pattern", "note_value_pattern"],
)
def test_a_missing_axis_names_the_axis_and_its_accepted_values(axis: str) -> None:
    params = _params()
    del params[axis]

    with pytest.raises(ValueError, match=axis) as raised:
        rhythm.apply(_score(4), params)

    assert str(vocabulary.accepted(axis)) in str(raised.value)


def test_an_unknown_value_names_the_accepted_values() -> None:
    with pytest.raises(ValueError, match="swung") as raised:
        rhythm.apply(_score(4), _params(subdivision="swung"))

    assert str(vocabulary.accepted("subdivision")) in str(raised.value)


def test_a_time_signature_tuple_is_rejected_in_favour_of_the_identifier() -> None:
    """§13's registry is the vocabulary; the slash lives in the display name only."""
    with pytest.raises(ValueError, match="time_signature"):
        rhythm.apply(_score(4), _params(time_signature=(4, 4)))


def test_an_empty_voice_is_an_error_rather_than_an_empty_exercise() -> None:
    with pytest.raises(ValueError, match="no notes"):
        rhythm.apply(_score(voice=[]), _params())
