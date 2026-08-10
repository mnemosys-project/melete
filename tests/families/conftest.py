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

`assert_spelling_sounds_correctly` is its direct analogue for §10a. A family
that omits its `Key` still produces a Score that engraves, and every note is
still spelled *something* — by the tier 3 direction rule, quietly. That is the
same class of failure as a wrong fret: two staves that disagree with nothing
raising. Both assertions are therefore called from every family test module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from melete import theory
from melete.score import Tuplet

if TYPE_CHECKING:
    from melete.score import Note, Score

#: The pitch class each letter names before any accidental is applied.
NATURALS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

_OCTAVE = len(theory.PITCH_CLASSES)


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


def assert_spelling_sounds_correctly(score: Score) -> None:
    """Spec §10a: every note as written must sound the pitch it names.

    The analogue of the central invariant on the notation side: there, position
    and pitch must agree; here, letter-plus-alteration and pitch must agree.
    Spelled through `score.key`, so it runs over whatever spelling this family's
    readers would actually be handed, including the notes a key does not
    contain — a blue note, or a chord tone outside the implied parent — where
    the fallback is the part most likely to be wrong.

    What it does *not* check is that the key is the right one: G♭ sounds pitch
    class 6 exactly as F♯ does, which is why the wrong-key defect was silent in
    the first place. Each family therefore states its `Key` in its own test,
    and §14's key-signature tests check what gets engraved.
    """
    notes = notes_of(score)
    spelled = theory.spell(score.key, [note.pitch for note in notes])
    for index, (note, name) in enumerate(zip(notes, spelled, strict=True)):
        sounded = (NATURALS[name.letter] + name.alteration) % _OCTAVE
        assert sounded == note.pitch % _OCTAVE, (
            f"note {index} of {score.title!r}: {name.letter}{name.alteration:+d} "
            f"does not sound pitch {note.pitch}"
        )
