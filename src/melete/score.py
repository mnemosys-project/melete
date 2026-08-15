r"""The Score IR — the seam between the families and the emitter (spec §4, §6).

A family produces a `Score`; the emitter (`alphatab/emit.py`) consumes one.
Neither imports the other, so a family never learns that the renderer exists and
the emitter never learns what a Dorian mode is. Everything here is pure data: this module knows
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
be inferred — because `rhythm.py` and `alphatab/emit.py` sit on opposite sides
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

## Tuplet nesting is permitted; the one-level rule was LilyPond's (melete#87)

A `Voice` is a flat sequence with `Tuplet` as its nested form. A `Tuplet` holds
`Note`s and *may* hold another `Tuplet`: the old "one level, no more" rule
existed only because LilyPond's `\tuplet 3/2 { ... }` was the target, and it is
lifted for the alphaTab port (epic #1 §4 correction, melete#71). The voice's own
membership — notes and tuplets, nothing else — is still checked at construction,
because the annotations that state it are erased before any family runs. The
port's families emit no nested tuplets and the alphaTex emitter flattens any it
is handed, so the deeper structure this permits is latent, not yet produced.

## Measures ARE modelled now, for the alphaTab pipeline (melete#87)

`Measure` wraps one bar's voice. The LilyPond path never needed it — durations
imply barlines and LilyPond inserts them — but the alphaTab renderer does not
auto-bar, so a barring pass splits a `Voice` into `Measure`s and the alphaTex
emitter emits one bar apiece. §7's short final measure is still not padded here.
`Measure` is consumed only by the emitter; adding it alongside the (now-removed)
LilyPond path left that emitter's inputs untouched, which is what kept the change
additive.

## Frozen shallowly, and not hashable

`Tuplet.notes` is a list and `Score.params` is a dict, exactly as §6 specifies.
`frozen=True` therefore stops those fields being *rebound* without freezing
their contents, and the generated `__hash__` raises `TypeError` on both types.
That is left alone deliberately: nothing in the pipeline keys a dict by a score
or builds a set of them, and loosening `frozen` or `eq` to make hashing work
would trade a real guarantee for one nothing needs. `Note` is hashable, being
made of scalars.
"""

from dataclasses import dataclass, field, replace
from enum import Enum
from fractions import Fraction
from typing import TYPE_CHECKING

from melete import theory

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from melete.instrument import InstrumentProfile

#: Left hand, index finger through little finger (spec §6).
FINGERS = range(1, 5)


class Hand(Enum):
    """Which hand frets a note (epic #67, spec §4).

    Bounded at two on purpose: one or two fretting hands is the whole musical
    space, and a count above two is not a musical case (spec §11 decision 2).
    Single-hand families always emit `LEFT`; two-hand tapping is the only path
    that produces `RIGHT`.
    """

    LEFT = "left"
    RIGHT = "right"


class Attack(Enum):
    """How a note is sounded (epic #67, spec §4).

    Orthogonal to `Hand`: either hand can tap, and a slur can occur under either
    hand. `PLUCKED` is the default, which is what leaves every existing family
    and golden file unchanged.
    """

    TAPPED = "tapped"  # attacked by tapping the fret (either hand)
    PLUCKED = "plucked"  # ordinary picked/plucked note — the default
    SLURRED = "slurred"  # sounded by hammer-on/pull-off; no fresh attack


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
    *is* the exercise, and a notation renderer engraves fingering marks natively.
    """

    pitch: int  # absolute semitones, C4 = 60
    string: int  # index into the profile's tuning, 0 = lowest
    fret: int  # 0 = open
    duration: Fraction  # WRITTEN value; 1 = whole note, 1/4 = quarter
    finger: int | None  # 1-4 of `hand`; None = unspecified
    accent: bool
    tied: bool = False  # tied into the following note; set by the barring pass (melete#87)
    hand: Hand = Hand.LEFT  # which hand frets the note; single-hand families emit LEFT (epic #67)
    attack: Attack = Attack.PLUCKED  # how the note is sounded; the default is unchanged (epic #67)

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
    onto alphaTex's `{tu 3 2}`.

    The notes inside carry their **written** durations, unscaled. See the
    module docstring: the ratio is the only place the scaling lives.

    A member may itself be a `Tuplet`: the "one level, no more" rule was
    LilyPond-imposed and its construction-time prohibition is lifted (melete#87,
    epic #1 §4). The static type stays `list[Note]` — the current walkers handle
    only flat tuplets — so a nested tuplet is permitted to build but is neither
    produced by the families nor consumed as a nested bracket; the alphaTex
    emitter flattens any it is handed.
    """

    ratio: tuple[int, int]  # (3, 2) = three in the time of two
    notes: list[Note]  # written durations, never scaled; runtime also permits a nested Tuplet

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

        foreign = _first_foreign(self.notes, (Note, Tuplet))
        if foreign is not None:
            index, item = foreign
            msg = (
                f"a tuplet holds notes and tuplets, but element {index} is a "
                f"{type(item).__name__}. The one-level-of-nesting rule was "
                f"LilyPond-imposed and is lifted (melete#87, epic #1 §4): a Tuplet "
                f"may now hold a Tuplet, but still only Notes and Tuplets."
            )
            raise TypeError(msg)


#: A flat sequence of notes and tuplets; a `Tuplet` may itself nest (melete#87).
Voice = list[Note | Tuplet]


@dataclass(frozen=True)
class Measure:
    """One bar's worth of voice, for renderers that must place barlines.

    The LilyPond emitter never needed this: durations imply barlines and LilyPond
    inserts them. The alphaTab renderer does not auto-bar, so a barring pass
    groups a `Voice` into `Measure`s and the alphaTex emitter emits one bar per
    `Measure`. Consumed only by the alphaTex pipeline; adding it left the
    (now-removed) LilyPond emitter's inputs unchanged (melete#87, epic #1 §4),
    which kept that change additive.

    Frozen shallowly like `Score`: the `voice` list cannot be rebound, though its
    contents are not deep-frozen. There is no membership check here — a `Measure`
    is built by the barring pass from an already-validated `Voice`, never from
    raw input.
    """

    voice: Voice


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

    `repeat` wraps the whole exercise in a repeat (spec §5): the practice loop
    plays the exercise twice rather than once. It is a plain intent flag on the
    renderer-agnostic side — *whether* the exercise repeats — and carries no
    knowledge of how a renderer draws a repeat barline; the emitter owns that.
    It defaults `False`, so an exercise plays once unless a family opts in.
    """

    title: str
    instruction: str  # one-line focus cue; cover page only
    instrument: InstrumentProfile
    time_signature: tuple[int, int]
    tempo_range: tuple[int, int]  # beats per minute, slowest to fastest
    voice: Voice
    key: theory.Key | None = None  # None = no tonal center, spelled by direction
    params: dict[str, object] = field(default_factory=dict)
    repeat: bool = False  # wrap the whole exercise in a repeat (spec §5)

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


def notes(voice: Voice) -> Iterator[Note]:
    """Every note a voice prints, tuplets flattened into their contents.

    The pipeline's producers emit at most one level of nesting, so this is one
    pass and never recursion (a nested tuplet is permitted to build since
    melete#87 but is produced by nothing, so this walk never meets one). It lives
    here rather than beside either caller because a voice is
    this module's structure: the length gate (§9) and the emitter's clef
    decision (§10) both have to see the notes *inside* a tuplet, and two private
    walks that must agree about the nesting rule are the drift decision #19
    exists to prevent.
    """
    for item in voice:
        if isinstance(item, Tuplet):
            yield from item.notes
        else:
            yield item


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


#: The augmentations a single written note value can carry: no dots, one dot
#: (×3/2), two dots (×7/4). This is the SAME writable set the emitter encodes in
#: its `_AUGMENTATIONS` (the original `lilypond/emit.py` encoded it too),
#: duplicated here deliberately so the barring pass stays renderer-agnostic — it
#: must not import the emitter (the renderer boundary, CLAUDE.md). The LilyPond
#: emitter has since been removed (epic #46, Task 10); `alphatab/emit.py` now
#: carries the emitter-side copy, and a future DRY pass could fold the two into a
#: single shared constant if that is ever wanted.
_WRITABLE_AUGMENTATIONS: tuple[Fraction, ...] = (
    Fraction(1),
    Fraction(3, 2),
    Fraction(7, 4),
)


def _split_writable(duration: Fraction) -> list[Fraction]:
    """Decompose a duration into individually writable note values.

    A *writable* value is a power-of-two note (whole, half, quarter, …) carrying
    zero, one or two dots: `duration / aug` is `1/2**k` for some `aug` in
    `_WRITABLE_AUGMENTATIONS`. That is exactly the set the emitter's
    `duration_token` accepts, mirrored here for the boundary reason above.

    A barline remainder is not always one such note — `5/8` is not — so it is
    split into the fewest writable pieces (here `1/2 + 1/8`), taken greedily
    largest-first, which the barring pass then ties together.

    `duration` must be dyadic (a power-of-two denominator), which every written
    note value and every barline remainder is. A non-dyadic value — a tuplet's
    sounding `1/12`, say — has no notehead and is rejected here rather than
    silently mis-split (decision #16; no silent failures).
    """
    if duration.denominator & (duration.denominator - 1):
        msg = (
            f"{duration} is not a dyadic duration and has no written form. "
            f"_split_writable decomposes barline remainders, which are always a "
            f"power-of-two fraction of a whole note. A sounding tuplet value like "
            f"1/12 belongs inside a Tuplet, where its ratio scales it (decision #16)."
        )
        raise ValueError(msg)

    pieces: list[Fraction] = []
    remaining = duration
    while remaining > 0:
        # The largest power-of-two note value (a whole note at most — a breve is
        # not writable, exactly as three dots are not) that fits the remainder.
        base = Fraction(1)
        while base > remaining:
            base /= 2
        # Extend it with the largest number of dots that still fits: the
        # augmentations ascend, so the last one that fits wins.
        piece = base
        for augmentation in _WRITABLE_AUGMENTATIONS:
            dotted = base * augmentation
            if dotted <= remaining:
                piece = dotted
        pieces.append(piece)
        remaining -= piece
    return pieces


def _plan_pieces(
    duration: Fraction, space: Fraction, capacity: Fraction
) -> list[tuple[list[Fraction], bool]]:
    """Lay an overflowing note out across bars as per-bar groups of pieces.

    The note's total `duration` is spread across bars: `space` remains in the
    current bar and each later bar offers a full `capacity`. Every chunk is the
    part that lands in one bar, decomposed into writable pieces
    (`_split_writable`), paired with whether it fills that bar exactly — i.e.
    whether a barline follows. The caller ties the pieces together and closes a
    `Measure` after each chunk a barline follows.
    """
    chunks: list[tuple[list[Fraction], bool]] = []
    remaining = duration
    room = space
    while remaining > 0:
        take = min(remaining, room)
        remaining -= take
        chunks.append((_split_writable(take), take == room))
        room = capacity
    return chunks


def bar(voice: Voice, time_signature: tuple[int, int]) -> list[Measure]:
    """Split a `Voice` into `Measure`s at the barlines a time signature implies.

    The LilyPond emitter never needed this — LilyPond inserts barlines from the
    durations themselves — but the alphaTab renderer does not auto-bar, so the
    alphaTex pipeline bars the voice first and emits one `Measure` per bar
    (melete#87).

    A bar holds `beats * (1 / beat_value)` whole notes of sounding time: 4/4
    holds one whole note, 6/8 holds three quarters. The voice is walked in
    *sounding* time (`sounding_duration`, decision #16), and each item is placed
    as follows.

    - A **Note** that fits the current bar is placed whole. One that would
      overflow is **split at the barline and tied**: the part that fits stays in
      this bar with `tied=True`, and the remainder continues into the next
      bar(s), looping while it spans whole bars. Each emitted piece is an
      individually writable value (`_split_writable`), every piece but the last
      is `tied=True`, and the final piece keeps the note's original `tied`.
      `accent` rides the first piece only; `string`, `fret` and `finger` ride
      every piece — they are the same stopped note throughout.
    - A **Tuplet** is indivisible: it is placed whole and never split or
      flattened into its notes (the barring pass does not descend into it — a
      nested tuplet passes through untouched). Its notes align to beats, so a
      family never straddles a barline with one; a tuplet whose sounding time
      *would* cross a barline is rejected rather than silently mis-split.

    The short final measure is **not** padded (spec §7): it closes with whatever
    it holds.
    """
    beats, beat_value = time_signature
    capacity = beats * Fraction(1, beat_value)

    measures: list[Measure] = []
    current: Voice = []
    filled = Fraction(0)

    for item in voice:
        if isinstance(item, Tuplet):
            span = sounding_duration([item])
            if filled + span > capacity:
                msg = (
                    f"a tuplet sounding {span} does not fit the {filled} already in a "
                    f"bar of {capacity}: it would cross a barline. Tuplets are "
                    f"indivisible — families align them to beats so this cannot arise "
                    f"from the pipeline, and splitting one silently would mis-time it."
                )
                raise ValueError(msg)
            current.append(item)
            filled += span
            if filled == capacity:
                measures.append(Measure(voice=current))
                current = []
                filled = Fraction(0)
            continue

        space = capacity - filled
        if item.duration <= space:
            current.append(item)
            filled += item.duration
            if filled == capacity:
                measures.append(Measure(voice=current))
                current = []
                filled = Fraction(0)
            continue

        chunks = _plan_pieces(item.duration, space, capacity)
        total = sum(len(pieces) for pieces, _ in chunks)
        position = 0
        for pieces, closes_bar in chunks:
            for piece_duration in pieces:
                current.append(
                    replace(
                        item,
                        duration=piece_duration,
                        accent=item.accent if position == 0 else False,
                        tied=item.tied if position == total - 1 else True,
                    )
                )
                filled += piece_duration
                position += 1
            if closes_bar:
                measures.append(Measure(voice=current))
                current = []
                filled = Fraction(0)

    if current:
        measures.append(Measure(voice=current))
    return measures
