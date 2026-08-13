"""Tests for the rhythm modifier (spec §8, §14, decision #16).

Two assertions carry this module. The first is that every written duration it
produces is a **representable notehead** — a plain, dotted or double-dotted
power of two — because `Note.duration` is what gets engraved and there is no
twelfth note to engrave. The second is that a `note_value_pattern`
**redistributes** time rather than adding or removing any: `long_short` and
`straight` must sound for exactly as long. If that drifts, the exercise no
longer fits the cycle length that §7's `max_notes` gate and §14's duration
test both reason about.

`restamp` (#118) is handed the subdivision by the layout fitter rather than
sampling one, so these tests pass the subdivision directly. The meter it tiles
into is the fitter's job and is tested in `test_pipeline.py`; the rest — the
subdivision table, the accents, the note-value patterns and the grouping — is
here, where a voice can be restamped without the machinery around it.
"""

from dataclasses import replace
from fractions import Fraction

import pytest

from melete import rhythm, vocabulary
from melete.score import Note, Tuplet, Voice, sounding_duration

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


def _voice(count: int = 8) -> Voice:
    """A voice of `count` plain notes, standing in for a family's output."""
    return [_note(index) for index in range(count)]


def _notes(voice: Voice) -> list[Note]:
    """Every note of `voice` in order, tuplet grouping discarded."""
    flat: list[Note] = []
    for item in voice:
        if isinstance(item, Tuplet):
            flat.extend(item.notes)
        else:
            flat.append(item)
    return flat


def _durations(voice: Voice) -> list[Fraction]:
    return [note.duration for note in _notes(voice)]


# --------------------------------------------------------------------------
# The written-duration contract (decision #16)
# --------------------------------------------------------------------------


def test_triplet_eighths_produce_a_tuplet_of_written_eighths() -> None:
    """Three written eighths under a (3, 2) ratio, sounding one quarter."""
    out = rhythm.restamp(_voice(6), "triplet_eighth")

    first = out[0]
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
    out = rhythm.restamp(_voice(9), subdivision, note_value_pattern=note_value_pattern)

    for duration in _durations(out):
        assert duration.numerator in (1, 3, 7)  # plain, dotted, double-dotted
        assert (duration / duration.numerator).denominator in NOTE_VALUES


@pytest.mark.parametrize("subdivision", SUBDIVISIONS)
def test_sounding_duration_equals_the_cycle_length(subdivision: str) -> None:
    """§14: the voice sounds for exactly one note per note, at the subdivision."""
    out = rhythm.restamp(_voice(12), subdivision)

    note_count = len(_notes(out))
    assert note_count == 12
    assert sounding_duration(out) == note_count * SOUNDING[subdivision]


@pytest.mark.parametrize("subdivision", SUBDIVISIONS)
@pytest.mark.parametrize("count", [8, 9])
def test_a_note_value_pattern_preserves_total_sounding_duration(
    subdivision: str,
    count: int,
) -> None:
    """The assertion that matters: swing redistributes time, never adds it."""
    straight = rhythm.restamp(_voice(count), subdivision)
    long_short = rhythm.restamp(_voice(count), subdivision, note_value_pattern="long_short")
    short_long = rhythm.restamp(_voice(count), subdivision, note_value_pattern="short_long")

    total = sounding_duration(straight)
    assert sounding_duration(long_short) == total
    assert sounding_duration(short_long) == total
    assert total == count * SOUNDING[subdivision]


@pytest.mark.parametrize("subdivision", ["triplet_eighth", "sextuplet", "quintuplet"])
def test_each_tuplet_still_holds_its_nominal_written_value(subdivision: str) -> None:
    """A swung tuplet is still three-in-the-time-of-two, not seven-eighths of it."""
    straight = rhythm.restamp(_voice(12), subdivision)
    swung = rhythm.restamp(_voice(12), subdivision, note_value_pattern="long_short")

    for plain, swing in zip(straight, swung, strict=True):
        assert sounding_duration([plain]) == sounding_duration([swing])


# --------------------------------------------------------------------------
# §8: subdivision
# --------------------------------------------------------------------------


def test_the_subdivision_table_covers_the_registry_exactly() -> None:
    assert sorted(rhythm.SUBDIVISIONS) == vocabulary.accepted("subdivision")


@pytest.mark.parametrize(("subdivision", "written"), [("quarter", 4), ("sixteenth", 16)])
def test_a_plain_subdivision_is_not_wrapped_in_a_tuplet(subdivision: str, written: int) -> None:
    out = rhythm.restamp(_voice(4), subdivision)

    assert all(isinstance(item, Note) for item in out)
    assert _durations(out) == [Fraction(1, written)] * 4


def test_a_tuplet_subdivision_groups_by_its_numerator() -> None:
    out = rhythm.restamp(_voice(12), "sextuplet")

    assert len(out) == 2
    assert all(isinstance(item, Tuplet) and item.ratio == (6, 4) for item in out)


def test_a_short_final_group_stays_a_tuplet() -> None:
    """Seven notes at triplet eighths is 3 + 3 + 1, and the last note is still 1/12."""
    out = rhythm.restamp(_voice(7), "triplet_eighth")

    assert [len(item.notes) for item in out if isinstance(item, Tuplet)] == [3, 3, 1]
    assert sounding_duration(out) == 7 * Fraction(1, 12)


def test_an_input_tuplet_is_regrouped_rather_than_nested() -> None:
    """Rhythm owns the grouping; whatever a family sent arrives flattened."""
    incoming: Voice = [
        Tuplet(ratio=(3, 2), notes=[_note(0), _note(1), _note(2)]),
        _note(3),
    ]
    out = rhythm.restamp(incoming, "eighth")

    assert out == [replace(_note(index), duration=Fraction(1, 8)) for index in range(4)]


# --------------------------------------------------------------------------
# §8: accent_pattern
# --------------------------------------------------------------------------


def test_no_accent_pattern_accents_nothing() -> None:
    out = rhythm.restamp(_voice(9), "eighth", accent_pattern="none")

    assert [note.accent for note in _notes(out)] == [False] * 9


def test_accent_every_3() -> None:
    out = rhythm.restamp(_voice(9), "eighth", accent_pattern="every_3")

    accents = [note.accent for note in _notes(out)]
    assert accents[::3] == [True] * len(accents[::3])
    assert accents == [True, False, False] * 3


def test_accent_every_5() -> None:
    out = rhythm.restamp(_voice(11), "eighth", accent_pattern="every_5")

    accents = [note.accent for note in _notes(out)]
    assert [index for index, accent in enumerate(accents) if accent] == [0, 5, 10]


def test_a_displaced_accent_falls_one_note_after_the_group() -> None:
    out = rhythm.restamp(_voice(9), "eighth", accent_pattern="displaced")

    accents = [note.accent for note in _notes(out)]
    assert [index for index, accent in enumerate(accents) if accent] == [1, 5]


def test_accents_are_indexed_across_tuplet_boundaries() -> None:
    """The accent runs over the notes, not over the groups they were packed into."""
    out = rhythm.restamp(_voice(9), "sextuplet", accent_pattern="every_3")

    assert [note.accent for note in _notes(out)] == [True, False, False] * 3


def test_an_incoming_accent_is_replaced_not_merged() -> None:
    accented: Voice = [replace(_note(index), accent=True) for index in range(4)]
    out = rhythm.restamp(accented, "eighth", accent_pattern="none")

    assert [note.accent for note in _notes(out)] == [False] * 4


# --------------------------------------------------------------------------
# §8: note_value_pattern
# --------------------------------------------------------------------------


def test_long_short_alternates_written_durations() -> None:
    out = rhythm.restamp(_voice(8), "eighth", note_value_pattern="long_short")

    durations = _durations(out)
    assert durations[0] > durations[1]
    assert durations[0::2] == [durations[0]] * len(durations[0::2])
    assert durations == [Fraction(3, 16), Fraction(1, 16)] * 4


def test_short_long_is_the_mirror_of_long_short() -> None:
    long_short = rhythm.restamp(_voice(8), "eighth", note_value_pattern="long_short")
    short_long = rhythm.restamp(_voice(8), "eighth", note_value_pattern="short_long")

    assert _durations(short_long)[:2] == list(reversed(_durations(long_short)[:2]))
    assert _durations(short_long) == list(reversed(_durations(long_short)))


def test_straight_leaves_every_note_at_the_subdivision() -> None:
    out = rhythm.restamp(_voice(8), "eighth")

    assert _durations(out) == [Fraction(1, 8)] * 8


def test_an_unpaired_final_note_keeps_the_straight_value() -> None:
    """A pair needs two notes; the leftover is the only value that adds no time."""
    out = rhythm.restamp(_voice(5), "eighth", note_value_pattern="long_short")

    assert _durations(out) == [
        Fraction(3, 16),
        Fraction(1, 16),
        Fraction(3, 16),
        Fraction(1, 16),
        Fraction(1, 8),
    ]


def test_the_pairing_restarts_inside_each_tuplet() -> None:
    """Odd groups leave their own leftover, so each tuplet keeps its nominal value."""
    out = rhythm.restamp(_voice(6), "triplet_eighth", note_value_pattern="long_short")

    assert _durations(out) == [Fraction(3, 16), Fraction(1, 16), Fraction(1, 8)] * 2


# --------------------------------------------------------------------------
# What the modifier carries through
# --------------------------------------------------------------------------


def test_pitch_position_and_fingering_survive_untouched() -> None:
    out = rhythm.restamp(_voice(6), "sixteenth", accent_pattern="every_3")

    for index, note in enumerate(_notes(out)):
        assert (note.pitch, note.string, note.fret, note.finger) == (
            36 + index,
            index % 6,
            index,
            1 + index % 4,
        )


def test_the_incoming_voice_is_left_alone() -> None:
    """`restamp` rebuilds each note with `replace`, so the input is never mutated."""
    voice = _voice(4)
    before = list(voice)

    rhythm.restamp(voice, "sixteenth")

    assert voice == before
    assert _durations(voice) == [Fraction(1, 4)] * 4


# --------------------------------------------------------------------------
# §13: an empty voice is a loud failure, never a silent empty exercise
# --------------------------------------------------------------------------


def test_an_empty_voice_is_an_error_rather_than_an_empty_exercise() -> None:
    with pytest.raises(ValueError, match="empty voice"):
        rhythm.restamp([], "eighth")
