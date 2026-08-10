r"""The Score IR — the seam between the families and the emitter (spec §4, §6).

A family produces a `Score`; `lilypond/emit.py` consumes one. Neither imports
the other, so a family never learns that LilyPond exists and the emitter never
learns what a Dorian mode is. Everything here is pure data: this module knows
how to *describe* an exercise and nothing else. It holds no fretboard logic —
`instrument` owns that — and no rendering logic whatsoever.

## Durations are always the WRITTEN value (decision #16)

**`Note.duration` is the value that gets engraved. `Tuplet.ratio` supplies the
scaling. Sounding time is derived, never stored.**

    sounding(note) = note.duration * ratio[1] / ratio[0]     # inside a Tuplet
    sounding(note) = note.duration                           # otherwise

A triplet of eighths is therefore three `Note`s of duration `1/8` inside a
`Tuplet` with ratio `(3, 2)`, and it sounds a quarter note in total.

This is the contract at this seam, and it is stated here — rather than left to
be inferred — because `rhythm.py` and `lilypond/emit.py` sit on opposite sides
of it. Written against different assumptions, every tuplet on every sheet would
render at the wrong note value.

Written durations are the correct choice rather than an arbitrary one: sounding
durations inside a tuplet are not representable as noteheads at all. A triplet
eighth is `1/12`, and there is no twelfth note. Storing sounding time would
force the emitter to invert the ratio to recover something writable, pushing
arithmetic and a new failure mode into the one module deliberately kept free of
both.

Anything needing real elapsed time — measure math, tempo estimates, the length
gate of §9 — goes through `sounding_duration`, which is the single shared
implementation of the formula above. There is deliberately no second one.

## One level of nesting, no more (spec §6)

A `Voice` is a flat sequence with `Tuplet` as the single nested form, mapping
directly onto LilyPond's `\tuplet 3/2 { ... }`. A `Tuplet` holds `Note`s and
never another `Tuplet`. Both halves of that rule are checked at construction,
because the type annotations that state them are erased before any family runs.

**Measures are not modelled.** Durations imply barlines and LilyPond inserts
them, so grouping against the meter — fives over 4/4 — needs no bar-splitting
logic anywhere in the pipeline. §7's short final measure follows from the same
stance and is closed by the emitter, not padded with rests here.

## Frozen shallowly, and not hashable

`Tuplet.notes` is a list and `Score.params` is a dict, exactly as §6 specifies.
`frozen=True` therefore stops those fields being *rebound* without freezing
their contents, and the generated `__hash__` raises `TypeError` on both types.
That is left alone deliberately: nothing in the pipeline keys a dict by a score
or builds a set of them, and loosening `frozen` or `eq` to make hashing work
would trade a real guarantee for one nothing needs. `Note` is hashable, being
made of scalars.
"""

from dataclasses import dataclass, field
from fractions import Fraction
from typing import TYPE_CHECKING

from melete import theory

if TYPE_CHECKING:
    from collections.abc import Iterable

    from melete.instrument import InstrumentProfile

#: Left hand, index finger through little finger (spec §6).
FINGERS = range(1, 5)

#: The pitch classes a key's tonic can name (spec §10a). Taken from `theory`'s
#: table rather than written as a second literal twelve.
TONICS = range(len(theory.PITCH_CLASSES))


def _first_foreign(items: Iterable[object], allowed: tuple[type, ...]) -> tuple[int, object] | None:
    """The first element that is not one of `allowed`, with its index."""
    for index, item in enumerate(items):
        if not isinstance(item, allowed):
            return index, item
    return None


@dataclass(frozen=True)
class Note:
    """One sounded note: which pitch, where on the neck, and for how long.

    Pitch and position are *both* stored and neither is derived at render time.
    A family decides which note to play and where to play it, because fretboard
    position is musical information rather than a rendering detail — that is
    the entire justification for a hand-rolled IR (decision #5). `instrument`
    holds the invariant relating the two: `pitch == tuning[string] + fret`.

    `finger` is first class because in chromatic permutation work the fingering
    *is* the exercise, and LilyPond renders fingering marks natively.
    """

    pitch: int  # absolute semitones, C4 = 60
    string: int  # index into the profile's tuning, 0 = lowest
    fret: int  # 0 = open
    duration: Fraction  # WRITTEN value; 1 = whole note, 1/4 = quarter
    finger: int | None  # left hand, 1-4; None = unspecified
    accent: bool

    def __post_init__(self) -> None:
        if self.duration <= 0:
            msg = f"note duration must be positive, got {self.duration}; a note occupies time"
            raise ValueError(msg)

        if self.string < 0:
            msg = (
                f"string index must be at least 0, got {self.string}. Index 0 is the "
                f"lowest string; a negative index would address the tuning from the "
                f"top and engrave plausible tablature for the wrong strings."
            )
            raise ValueError(msg)

        if self.fret < 0:
            msg = f"fret must be at least 0, got {self.fret}; fret 0 is the open string"
            raise ValueError(msg)

        if self.finger is not None and self.finger not in FINGERS:
            msg = (
                f"finger must be 1-4 or None for unspecified, got {self.finger}; "
                f"the left hand has four stopping fingers"
            )
            raise ValueError(msg)


@dataclass(frozen=True)
class Tuplet:
    r"""A group of notes played in the time of a different number of them.

    `ratio` is read as "numerator in the time of denominator": `(3, 2)` is the
    ordinary triplet, three written notes occupying the time of two, and maps
    onto LilyPond's `\tuplet 3/2 { ... }`.

    The notes inside carry their **written** durations, unscaled. See the
    module docstring: the ratio is the only place the scaling lives.
    """

    ratio: tuple[int, int]  # (3, 2) = three in the time of two
    notes: list[Note]  # written durations, never scaled

    def __post_init__(self) -> None:
        numerator, denominator = self.ratio
        if numerator <= 0 or denominator <= 0:
            msg = (
                f"tuplet ratio must be two positive integers, got {self.ratio}; "
                f"(3, 2) is three notes in the time of two"
            )
            raise ValueError(msg)

        if not self.notes:
            msg = "a tuplet must hold at least one note; an empty tuplet has no engraved form"
            raise ValueError(msg)

        foreign = _first_foreign(self.notes, (Note,))
        if foreign is not None:
            index, item = foreign
            msg = (
                f"a tuplet holds notes and nothing else, but element {index} is a "
                f"{type(item).__name__}. Spec §6 allows exactly one level of nesting: "
                f"a voice is flat with Tuplet as its single nested form, and a tuplet "
                f"inside a tuplet has no LilyPond construct to map onto."
            )
            raise TypeError(msg)


#: A flat sequence of notes and tuplets. The one and only nesting level.
Voice = list[Note | Tuplet]


@dataclass(frozen=True)
class Score:
    """One complete exercise, ready to engrave and to log.

    `params` travels inside the Score deliberately: the session log receives the
    exact parameter dictionary that produced the exercise, so any sheet is
    reproducible and the selector reads history back without a second
    bookkeeping path (spec §6, §12).

    `instruction` is a one-line focus cue for the cover page only. It is never
    rendered onto an exercise page — prose overlaid on notation competes with
    the notes (decision #10) — and an empty string means the family supplied
    none.

    `tempo_range` comes from the family, never from a sampled axis: letting it
    vary across sessions would be progressive overload arriving through the back
    door, which §17 defers to v2 (decision #20).

    `key` is the tonal center the notes are *written* against (§10a). A pitch is
    a 12-TET integer and therefore cannot carry a spelling on its own — F♯ and
    G♭ are the same number — so this is the field that decides whether the
    notation staff reads F♯ Dorian or the same sounds written as G♭ Dorian, an
    eight-flat key nobody plays from. Tablature is unaffected either way, which
    is what made the original defect silent.

    `None` is a real value and not an omission: it means the exercise has no
    tonal center, which is true of everything the `chromatic` family produces,
    and it spells by direction as tier 3 does. It is also the default, so a
    family that neglects to set a key produces a Score that engraves perfectly
    well and spells every note by direction. `tests/families/conftest.py` says
    what that costs; each family states its key in its own test.
    """

    title: str
    instruction: str  # one-line focus cue; cover page only
    instrument: InstrumentProfile
    time_signature: tuple[int, int]
    tempo_range: tuple[int, int]  # beats per minute, slowest to fastest
    voice: Voice
    key: theory.Key | None = None  # None = no tonal center, spelled by direction
    params: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        beats, beat_value = self.time_signature
        if beats <= 0 or beat_value <= 0:
            msg = f"time signature must be two positive integers, got {self.time_signature}"
            raise ValueError(msg)

        # 4/3 has no notated form: the lower number names a note value, and
        # note values are powers of two.
        if beat_value & (beat_value - 1):
            msg = (
                f"time signature denominator must be a power of two, got {beat_value}; "
                f"it names a note value, and there is no third note"
            )
            raise ValueError(msg)

        slowest, fastest = self.tempo_range
        if slowest <= 0:
            msg = f"tempo must be positive, got {self.tempo_range} beats per minute"
            raise ValueError(msg)

        if fastest < slowest:
            msg = (
                f"tempo range must run slowest to fastest, got {self.tempo_range}; "
                f"§12 prints it as a range on the cover page"
            )
            raise ValueError(msg)

        foreign = _first_foreign(self.voice, (Note, Tuplet))
        if foreign is not None:
            index, item = foreign
            msg = (
                f"a voice holds notes and tuplets, but element {index} is a "
                f"{type(item).__name__}. Spec §6 makes a voice a flat sequence with "
                f"Tuplet as its single nested form."
            )
            raise TypeError(msg)

        if self.key is not None:
            if self.key.tonic not in TONICS:
                msg = (
                    f"key tonic must be a pitch class {TONICS[0]}-{TONICS[-1]}, got "
                    f"{self.key.tonic}; §10a keeps the tonic a pitch class so that "
                    f"`root` stays an absolute pitch everywhere else, and 60 is "
                    f"middle C only in the second sense"
                )
                raise ValueError(msg)

            # Called for its lookup, not its answer: `tier` raises a KeyError
            # naming the value and every accepted scale type, which is the
            # message §13 asks for and one `theory` already writes.
            theory.tier(self.key.scale_type)


def sounding_duration(voice: Voice) -> Fraction:
    """Real elapsed time of `voice`, in whole notes: `1/4` is one quarter note.

    The single shared implementation of decision #16. Written durations inside a
    tuplet are scaled by its ratio; everything else sounds as written. Callers
    that need real time — measure math, tempo estimates, the §9 length gate —
    come here rather than reimplementing the formula, which is the whole point
    of there being one.
    """
    total = Fraction(0)
    for item in voice:
        if isinstance(item, Tuplet):
            numerator, denominator = item.ratio
            written = sum((note.duration for note in item.notes), Fraction(0))
            total += written * denominator / numerator
        else:
            total += item.duration
    return total
