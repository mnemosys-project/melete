"""Shared assertions for the family tests (spec §14).

Every family is tested the same way, because every family makes the same
promise: it decides both *which* note to play and *where* to play it, and the
two must agree. `assert_central_invariant` is that agreement, and it is the
single assertion most likely to catch a fretboard-positioning bug — a family
that transposes a shape without moving it on the neck produces a Score that is
internally inconsistent and engraves as notation and tablature that disagree.

It lives in a `conftest.py` so every family test module can import it by name
without a package import path, and so the assertion has exactly one spelling
across `chromatic`, `scales`, `arpeggios` and `intervals` (tasks B5-B8).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from melete.score import Tuplet

if TYPE_CHECKING:
    from melete.score import Note, Score


def notes_of(score: Score) -> list[Note]:
    """Every note in `score` in playing order, tuplets flattened.

    Spec §6 allows exactly one level of nesting, so flattening is one pass and
    never recursion.
    """
    flat: list[Note] = []
    for item in score.voice:
        flat.extend(item.notes if isinstance(item, Tuplet) else [item])
    return flat


def assert_central_invariant(score: Score) -> None:
    """Spec §14: `pitch == tuning[string] + fret`, for every note.

    The string index is checked *before* the invariant it indexes with: a
    negative index would otherwise address the tuning from the top and satisfy
    the arithmetic while naming the wrong string.
    """
    profile = score.instrument
    for index, note in enumerate(notes_of(score)):
        where = f"note {index} of {score.title!r} on {profile.name!r}"

        assert 0 <= note.string < len(profile.tuning), (
            f"{where}: string {note.string} is outside 0-{len(profile.tuning) - 1}"
        )
        assert 0 <= note.fret <= profile.fret_count, (
            f"{where}: fret {note.fret} is outside 0-{profile.fret_count}"
        )
        assert note.pitch == profile.tuning[note.string] + note.fret, (
            f"{where}: pitch {note.pitch} != string {note.string} "
            f"({profile.tuning[note.string]}) + fret {note.fret}"
        )
