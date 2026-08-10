"""The rhythm modifier — one `Score -> Score` function over all four families.

Rhythm is **not** a fifth family (spec §8, decision #3). It is a cross-cutting
modifier, because overload dimensions are orthogonal: treating rhythm as a
parameter axis multiplies the variant space rather than adding to it, and keeps
the rhythm logic in one component instead of four copies of it.

A family decides *which* notes and *where* on the neck; this module decides
*when*. It therefore restamps every duration and every accent, and it discards
whatever grouping arrived — a family's tuplets, if it emitted any, are not a
second opinion about the rhythm. Pitch, string, fret and fingering are carried
through untouched.

## Written durations, always (decision #16)

`Note.duration` is the value that gets engraved; `Tuplet.ratio` supplies the
scaling; sounding time is derived by `score.sounding_duration` and never stored.
So `triplet_eighth` produces `Note`s of written duration `1/8` inside a `Tuplet`
of ratio `(3, 2)`, which sound `1/12` each. Storing `1/12` would be storing a
duration with no notehead to engrave it with.

## A note-value pattern redistributes time, it never adds any

`long_short` lengthens the first note of a pair by half and shortens the second
by the same amount: `1/8 1/8` becomes `3/16 1/16`, a dotted eighth and a
sixteenth. The pair still sounds for `2/8`. The ratio is 3:1 rather than the
2:1 of an even swing because 3:1 is the one that lands on a *notehead* — a
long of `4/3` the subdivision is not writable at all.

Two rules keep the redistribution exact:

- **Pairing restarts inside every tuplet.** Pairs that straddled a group
  boundary would leave a `(3, 2)` tuplet holding seven eighths' worth of
  written value instead of six: still correct in total, but no longer three in
  the time of two, and no longer a group whose written content matches the
  ratio it is engraved under.
- **An unpaired final note keeps the straight value.** An odd count — nine
  notes, or the third note of every triplet — leaves one note with no partner
  to trade with. Lengthening it would add time that nothing gives back, and
  §7's `max_notes` gate and §14's duration test both reason about a cycle whose
  length is exactly the note count times the subdivision.

Both rules are why `sounding_duration` is identical between `straight` and
`long_short` for the same input, which is the assertion this module is built
around.

## Grouping and the short final group

A tuplet subdivision packs notes into groups of its ratio's numerator: six for
a sextuplet, five for a quintuplet, three for triplet eighths. A cycle whose
length is not a multiple of that leaves a short final group, which stays a
tuplet under the same ratio rather than being flattened — flattening it would
re-time those notes from `1/12` to `1/8` and stretch the exercise. That is the
same stance §7 takes on the short final *measure*: accept it, do not pad it.

Measures are not modelled anywhere (§6), so `time_signature` here is a label
placed on the `Score` for the emitter. Nothing in this module counts bars.
"""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from typing import TYPE_CHECKING

from melete import vocabulary
from melete.score import Tuplet

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    from melete.score import Note, Score, Voice

#: §8's `subdivision` axis: the **written** duration one note gets, and the
#: tuplet ratio it is engraved under, or `None` when it needs no tuplet.
#: A sextuplet is `(6, 4)` rather than `(3, 2)` because six sixteenths in the
#: time of four is the group a player reads as one beat.
SUBDIVISIONS: dict[str, tuple[Fraction, tuple[int, int] | None]] = {
    "quarter": (Fraction(1, 4), None),
    "eighth": (Fraction(1, 8), None),
    "sixteenth": (Fraction(1, 16), None),
    "triplet_eighth": (Fraction(1, 8), (3, 2)),
    "sextuplet": (Fraction(1, 16), (6, 4)),
    "quintuplet": (Fraction(1, 16), (5, 4)),
}

#: §8's `accent_pattern` axis as (period, offset) over the flat note sequence,
#: or `None` for no accents at all.
#:
#: `displaced` is "displaced by one" (§8) read as the ordinary duple grouping
#: moved off the downbeat: a period of four with the accent on the second note
#: rather than the first. The spec names the pattern without fixing its period,
#: and four is the grouping a reader supplies for free — which is exactly what
#: makes displacing it an exercise. `every_3` and `every_5` are already the odd
#: groupings, so a third odd period here would add nothing.
ACCENTS: dict[str, tuple[int, int] | None] = {
    "none": None,
    "every_3": (3, 0),
    "every_5": (5, 0),
    "displaced": (4, 1),
}

#: §8's `note_value_pattern` axis: what the two notes of a pair are multiplied
#: by. The two factors sum to 2, which is the whole of the "redistributes, does
#: not add" guarantee — a pair of subdivision `d` still sounds `2d`.
LONG = Fraction(3, 2)
SHORT = Fraction(1, 2)

NOTE_VALUE_PATTERNS: dict[str, tuple[Fraction, Fraction] | None] = {
    "straight": None,
    "long_short": (LONG, SHORT),
    "short_long": (SHORT, LONG),
}

#: §8's four axes, named exactly as `vocabulary` and `[pool.rhythm]` name them.
#: Resolving them as one mapping is what makes the `params` this module records
#: complete by construction: whatever it reads is exactly what §12's cover page
#: and `session.json` get back, with no second list to keep in step.
AXES = ("subdivision", "time_signature", "accent_pattern", "note_value_pattern")

_PAIR = 2


def apply(score: Score, params: Mapping[str, object]) -> Score:
    """`score` re-rhythmed under §8's four axes, as a new `Score`.

    `params` is read, not consumed: it may carry the family's axes alongside
    the rhythm ones, since §12's cover page and `session.json` describe an
    exercise with a single merged dictionary. All four rhythm axes must be
    present and must be canonical identifiers from `vocabulary` — a missing or
    misspelled axis raises, naming it and its accepted values, because a
    default silently substituted here is a wrong exercise on the page (§13).
    """
    axes = {axis: _axis(params, axis) for axis in AXES}
    written, ratio = SUBDIVISIONS[axes["subdivision"]]

    notes = list(_flatten(score.voice))
    if not notes:
        msg = (
            f"cannot apply rhythm to {score.title!r}: the score has no notes. "
            f"A family emits one complete cycle of its pattern (§7), so an "
            f"empty voice is a bug upstream, not an exercise of length zero."
        )
        raise ValueError(msg)

    group = ratio[0] if ratio is not None else len(notes)
    pattern = NOTE_VALUE_PATTERNS[axes["note_value_pattern"]]
    durations = _durations(len(notes), written, pattern, group)
    accents = _accents(len(notes), ACCENTS[axes["accent_pattern"]])

    restamped = [
        replace(note, duration=duration, accent=accent)
        for note, duration, accent in zip(notes, durations, accents, strict=True)
    ]

    return replace(
        score,
        time_signature=_meter(axes["time_signature"]),
        voice=_grouped(restamped, ratio),
        params={**score.params, **axes},
    )


def _axis(params: Mapping[str, object], axis: str) -> str:
    """One canonical identifier out of `params`, or a `ValueError` naming it."""
    accepted = vocabulary.accepted(axis)
    if axis not in params:
        msg = f"rhythm requires a {axis}; accepted: {accepted}"
        raise ValueError(msg)

    value = params[axis]
    if not isinstance(value, str) or value not in accepted:
        msg = f"unknown {axis} {value!r}; accepted: {accepted}"
        raise ValueError(msg)
    return value


def _meter(identifier: str) -> tuple[int, int]:
    """`"7_8"` as `(7, 8)`. The slash lives in the display name only (§13)."""
    beats, _, beat_value = identifier.partition("_")
    return int(beats), int(beat_value)


def _flatten(voice: Voice) -> Iterator[Note]:
    """Every note of `voice` in order, with whatever grouping it had dropped."""
    for item in voice:
        if isinstance(item, Tuplet):
            yield from item.notes
        else:
            yield item


def _durations(
    count: int,
    written: Fraction,
    pattern: tuple[Fraction, Fraction] | None,
    group: int,
) -> list[Fraction]:
    """The written duration of each of `count` notes under a note-value pattern.

    Pairs restart every `group` notes, and a group of odd length ends on the
    plain subdivision: see the module docstring on why both are what keeps the
    total sounding duration identical to `straight`.
    """
    if pattern is None:
        return [written] * count

    first, second = pattern
    durations: list[Fraction] = []
    for start in range(0, count, group):
        span = min(group, count - start)
        for index in range(span):
            if index == span - 1 and span % _PAIR:
                durations.append(written)  # no partner to trade time with
            elif index % _PAIR:
                durations.append(written * second)
            else:
                durations.append(written * first)
    return durations


def _accents(count: int, rule: tuple[int, int] | None) -> list[bool]:
    """Which of `count` notes are accented, indexed across group boundaries.

    The index runs over the notes, not over the tuplets they are packed into:
    accenting every third note of a sextuplet run is the cross-grouping
    exercise §8 is asking for, and resetting per group would silently turn it
    into the metre it was meant to cut across.
    """
    if rule is None:
        return [False] * count

    period, offset = rule
    return [index % period == offset for index in range(count)]


def _grouped(notes: Sequence[Note], ratio: tuple[int, int] | None) -> Voice:
    """`notes` packed into tuplets of `ratio`, or left flat when there is none."""
    if ratio is None:
        return [*notes]

    size = ratio[0]
    return [
        Tuplet(ratio=ratio, notes=list(notes[start : start + size]))
        for start in range(0, len(notes), size)
    ]
