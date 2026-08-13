"""`intervals` — interval and string-skipping sequences (spec §7, MNEMOSYS P2, T4).

`generate` is a pure function: no I/O, no randomness, no clock. The selector
(§9) chooses the parameters and this module realizes them, which is what makes
a sheet reproducible from its session log and this family testable without any
of the machinery around it. It therefore imports neither `selection` nor
`config`.

## Why this family exists

The other three families would still be the exercises they are if `Note` held
only a pitch. This one would not. §7 puts it in the tool because **tablature
makes string topology expressible**, and a string-skipping drill is defined by
*which strings the two notes of a pair land on* — the same two pitches played
on adjacent strings and played three strings apart are different exercises for
the plucking hand and identical for the notation staff. That is the whole
justification for modelling the fretboard in the core (decision #4) rather than
treating position as a rendering detail, and it is why `string_skip` is a hard
constraint here rather than a hint.

## What one exercise is

One exercise is **one complete cycle of the pattern** (§7) and is never
truncated. Here the cycle is one octave of lower notes, each sounded together
with the note `interval` above it: eight pairs for a seven-note scale, thirteen
for a chromatic context. The octave itself is included as a lower note for the
same reason `scales` closes on its octave — a run that stops a step short of it
reads as unfinished.

## The axes, and what this module decided about them

**`context` decides what "a third" means, and the two answers really differ.**
A *diatonic* third is a scale degree away, so it is three semitones on some
degrees and four on others; a *chromatic* third is four semitones everywhere,
because there is no scale to bend it. The chromatic sizes are the major and
perfect ones, derived from the major scale rather than written out a second
time, so a 9th is a major 9th and an 8th is the octave.

**`string_skip` is a hard constraint on position, not a preference.** The two
notes of a pair are placed exactly `string_skip + 1` strings apart, the lower
note on the lower string. A specification that cannot be placed at that
distance within `string_set` is **invalid** and raises, naming what could not
be satisfied; §9's validity gate resamples it. Quietly settling for an adjacent
string would engrave a plausible exercise that is not the one that was
requested, which is the §13 failure mode this project exists to avoid — and it
would be undetectable from the notation staff, because the pitches would be
right.

**One string pair, held for the whole exercise.** The pair is chosen once, from
the pairs `string_set` offers at the required distance, and every lower note
goes on its lower string and every upper note on its upper string. That is what
makes the exercise a string-skipping drill rather than a scale that happens to
cross strings, and it is the only layout under which the *transition between*
pairs also respects the skip: a walk that advanced one string per pair would
put the top of one pair one string away from the bottom of the next, which is
the adjacent crossing a skip-1 specification exists to forbid. Of the pairs
that can carry every note, the lowest wins — deterministic all the way down,
which is what reproducibility from a session log needs.

**`pattern` orders the two notes inside a pair; `direction` orders the pairs.**
This is the one place this family turns `direction` round from the way `scales`
and `arpeggios` use it, and deliberately. There a pattern is a window slid along
the scale, and the retrograde of the whole sequence genuinely *is* the
descending figure. Here the pattern names which note of the pair comes first, so
reversing the whole note sequence would turn `descending_pairs` into ascending
ones while §12's cover page still printed "descending pairs" — a sheet that is
not the exercise it names. `alternating` turns every other pair around, counted
over the pairs as played, so `up_down` keeps alternating through the turnaround
rather than restarting.

## The key

§10a: the key is a branch on `context`, and it is stated explicitly in both
branches because *neither* answer is a default. A diatonic sequence is spelled
against the scale its intervals are degrees of. A chromatic one asserts no tonal
center at all, so it is tier 3 by definition and spells by direction — sharps
ascending, flats descending — exactly as `chromatic` does. `None` there is the
answer, not an omission: a family that ships without a key does not fail, it
engraves every note by the direction rule while the tablature stays correct, and
the two staves disagree silently.

`scale_type` is read **only** in the diatonic branch. Requiring it in a
chromatic context would make two specifications that differ in nothing an
exercise can hear engrave the same sheet, and §9's coverage accounting has no
way to tell such a pair apart.

## Running off the neck

A specification that cannot be realized on the profile raises, naming the axes
that could not be satisfied. It is never clamped to fit — a clamped exercise is
a plausible-looking sheet that is not the one the selector drew, and §9's
validity gate exists precisely to resample this case.
"""

from __future__ import annotations

from fractions import Fraction
from typing import TYPE_CHECKING

from melete import theory, vocabulary
from melete.families._shared import (
    Parameters,
    apply_direction,
    layout_hints,
    realizable,
    string_set,
)
from melete.layout import Lever
from melete.score import Note, Score

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from melete.instrument import InstrumentProfile
    from melete.layout import LayoutHints
    from melete.score import Voice

#: This family's identifier in `vocabulary.AXES["family"]`, and the prefix on
#: every error this module raises (§13). Written once so the two cannot drift.
_FAMILY = "intervals"

#: Spec §7's tempo range for this family, in beats per minute. The *family*
#: declares it and the selector never samples it (decision #20); configuration
#: overrides it per family through `[pool.intervals] tempo`.
#:
#: String crossing and skipping do cost accuracy at speed, which is why this
#: range starts below the scales' — but not by as much as the original 70-90
#: assumed, which was reasoned from categories rather than from an instrument
#: and came out too slow to practise against. §7 carries that reasoning; the
#: number is declared here.
DEFAULT_TEMPO_RANGE = (70, 130)

#: The un-modified reading: one note per beat in common time. `rhythm.py` (§8)
#: is the cross-cutting modifier that re-times a Score into subdivisions and
#: other meters, so this family states the plainest possible rhythm and leaves
#: the subject to the one module that owns it.
DEFAULT_TIME_SIGNATURE = (4, 4)
NOTE_DURATION = Fraction(1, 4)

INSTRUCTION = "Mute the strings you skip over; both notes of a pair should speak equally."

#: §7's axis columns. Named here so a missing parameter can list what the
#: family expected rather than only what it did not find. `root` is read in
#: both contexts — every exercise starts somewhere — and `scale_type` only in
#: the diatonic one, which is what §7's "diatonic within root + scale" says.
AXES = (
    "interval",
    "context",
    "root",
    "scale_type",
    "string_skip",
    "string_set",
    "direction",
    "pattern",
)

#: §7's `context` column has exactly two values, so the chromatic case is the
#: remaining branch rather than a second test — the same reason
#: `apply_direction` leaves `up_down` to fall through.
_DIATONIC = "diatonic"
_ASCENDING_PAIRS = "ascending_pairs"
_DESCENDING_PAIRS = "descending_pairs"

#: The subset of §7's `pattern` column this family realizes. `vocabulary`
#: carries the union of every family's patterns in one axis, so the family
#: states which of them it can lay out — `thirds` and `broken` belong to
#: `scales` and `arpeggios`.
_PATTERNS = (_ASCENDING_PAIRS, _DESCENDING_PAIRS, "alternating")

_SEMITONES_PER_OCTAVE = len(theory.PITCH_CLASSES)

#: The natural cell (§4.3): each pair is the two notes sounded together, so one
#: beat's worth of this exercise is two notes. Named because the count and the
#: two-note construction below must not be able to disagree.
_NOTES_PER_PAIR = 2

#: §7's `interval` column, 2nd through 10th, and the prose §12's cover page
#: prints for each. One table, so the accepted set and the display names cannot
#: disagree. `vocabulary` deliberately does not carry this axis: it is a range,
#: validated here against what a family can realize rather than enumerated
#: alongside the registry identifiers.
INTERVAL_NAMES: dict[int, str] = {
    2: "seconds",
    3: "thirds",
    4: "fourths",
    5: "fifths",
    6: "sixths",
    7: "sevenths",
    8: "octaves",
    9: "ninths",
    10: "tenths",
}

#: The chromatic sizes are the major scale's, extended past the octave: a 3rd
#: is a major third, a 5th a perfect fifth, a 9th a major ninth. Derived rather
#: than tabulated, because a second table of the same nine numbers is a second
#: thing to keep right.
_MAJOR_SCALE = theory.SCALES["ionian"]


def _semitones(interval: int) -> int:
    """How far above its lower note a chromatic `interval` sounds."""
    step = interval - 1
    degrees = len(_MAJOR_SCALE)
    return _MAJOR_SCALE[step % degrees] + _SEMITONES_PER_OCTAVE * (step // degrees)


def _interval(read: Parameters) -> int:
    """The `interval` axis, which §7 bounds at a 2nd and a 10th."""
    value = read.integer("interval")
    if value not in INTERVAL_NAMES:
        msg = (
            f"{_FAMILY}: interval must be one of {sorted(INTERVAL_NAMES)} — a 2nd through a "
            f"10th (§7) — got {value}"
        )
        raise ValueError(msg)
    return value


def _chromatic_pairs(root: int, interval: int) -> list[tuple[int, int]]:
    """One octave of lower notes a semitone apart, each with its exact partner."""
    step = _semitones(interval)
    return [(root + offset, root + offset + step) for offset in range(_SEMITONES_PER_OCTAVE + 1)]


def _diatonic_pairs(root: int, scale_type: str, interval: int) -> list[tuple[int, int]]:
    """One octave of scale degrees, each with the degree `interval` above it.

    The upper note is `interval - 1` *degrees* away, not a fixed semitone
    count, which is what makes a diatonic third minor on some degrees and major
    on others. Enough octaves are built that the top of the cycle still has a
    partner to reach for; the closing octave `scale_pitches` appends is dropped
    because the degrees repeat past it anyway.
    """
    degrees_per_octave = len(theory.SCALES[scale_type])
    span = -(-interval // degrees_per_octave) + 1
    degrees = theory.scale_pitches(root, scale_type, span)[: span * degrees_per_octave]
    step = interval - 1
    return [(degrees[index], degrees[index + step]) for index in range(degrees_per_octave + 1)]


def _frets(profile: InstrumentProfile, pitches: Sequence[int], string: int) -> list[int] | None:
    """Where `string` sounds each pitch, or None if it cannot sound them all."""
    frets = [pitch - profile.tuning[string] for pitch in pitches]
    if any(fret < 0 or fret > profile.fret_count for fret in frets):
        return None
    return frets


def _placed(
    profile: InstrumentProfile,
    pairs: Sequence[tuple[int, int]],
    strings: tuple[int, ...],
    skip: int,
) -> tuple[tuple[int, int], list[int], list[int]]:
    """The string pair the exercise is played on, and the frets on each of them.

    Both failures are specification errors rather than repairs (§13): a
    `string_set` offering no pair at the required distance, and a pair distance
    no two strings in the set can carry the notes at. Neither is resolved by
    moving a note to a string it was not asked for — §9's validity gate
    resamples an over-constrained draw, which is a different thing from
    engraving a nearby exercise and calling it the one requested.
    """
    distance = skip + 1
    candidates = [(low, low + distance) for low in strings if low + distance in strings]
    if not candidates:
        msg = (
            f"{_FAMILY}: string_skip {skip} needs two strings {distance} apart, and string_set "
            f"{list(strings)} on profile {profile.name!r} has no such pair. string_skip is a "
            f"hard constraint on where a pair is played, not a preference: settling for a "
            f"nearer string would engrave a plausible exercise that is not the one specified"
        )
        raise ValueError(msg)

    lows = [low for low, _high in pairs]
    highs = [high for _low, high in pairs]
    for low_string, high_string in candidates:
        low_frets = _frets(profile, lows, low_string)
        high_frets = _frets(profile, highs, high_string)
        if low_frets is not None and high_frets is not None:
            return (low_string, high_string), low_frets, high_frets

    msg = (
        f"{_FAMILY}: no string pair {distance} apart within string_set {list(strings)} can carry "
        f"pitches {lows[0]}-{lows[-1]} against {highs[0]}-{highs[-1]} on profile "
        f"{profile.name!r}, which has frets 0 to {profile.fret_count}. interval, context, root, "
        f"string_set and string_skip cannot all be satisfied at once; §9 resamples this rather "
        f"than moving a note to a string it was not asked for"
    )
    raise ValueError(msg)


def _plays_downward(pattern: str, position: int) -> bool:
    """Whether the pair in this position is played upper note first."""
    if pattern == _ASCENDING_PAIRS:
        return False
    if pattern == _DESCENDING_PAIRS:
        return True
    return position % 2 == 1


def _title(root: int, named: str, interval: int, skip: str, pattern: str, direction: str) -> str:
    """The plain-language name §12's cover page prints, built from the registry.

    `named` is what the context is called: the scale for a diatonic sequence,
    and the word "chromatic" for one with no scale to name.
    """
    return (
        f"{theory.PITCH_CLASSES[root % _SEMITONES_PER_OCTAVE]} {named} "
        f"{INTERVAL_NAMES[interval]}, {vocabulary.display('string_skip', skip)}, "
        f"{vocabulary.display('pattern', pattern)}, {vocabulary.display('direction', direction)}"
    )


def generate(profile: InstrumentProfile, params: Mapping[str, object]) -> tuple[Score, LayoutHints]:
    """Realize one interval or string-skipping exercise on `profile`, with hints.

    Pure: the same profile and parameters always produce the same Score. Extra
    keys in `params` are carried into the Score untouched rather than rejected
    — §8's rhythm axes travel in the same dictionary — but every axis this
    family reads is required, so a misspelled one is a loud failure and never a
    silent default.

    The §4.2 hints report the pair as the natural cell — two notes to a beat —
    and, for an `up_down` exercise, the note index of the apex the pairs turn
    around at, so the fitter's apex levers know where to act. A one-directional
    exercise has no such seam.
    """
    read = Parameters(_FAMILY, AXES, params)
    interval = _interval(read)
    context = read.identifier("context")
    root = read.integer("root")

    if context == _DIATONIC:
        scale_type = read.identifier("scale_type")
        pairs = _diatonic_pairs(root, scale_type, interval)
        named = vocabulary.display("scale_type", scale_type)
        # §10a: the intervals are degrees of this scale, so they are spelled by
        # it. `root` reduces to a pitch class because A1 and A2 are the same key.
        key: theory.Key | None = theory.Key(root % _SEMITONES_PER_OCTAVE, scale_type)
    else:
        pairs = _chromatic_pairs(root, interval)
        named = vocabulary.display("context", context)
        # Stated rather than left to the default: a chromatic interval sequence
        # asserts no tonal center, so this branch is tier 3 by definition (§10a)
        # and spells by direction. `None` is the answer here, not the omission
        # it would be in the diatonic branch, which has a key to give.
        key = None

    skip = read.identifier("string_skip")
    strings = string_set(read, profile)
    direction = read.identifier("direction")
    pattern = realizable(read, "pattern", _PATTERNS)

    # The identifiers are the digit strings "0", "1" and "2" (§7 writes them as
    # numbers; `vocabulary` carries them like every other axis), and they have
    # been validated against the registry, so this conversion cannot surprise.
    placement, low_frets, high_frets = _placed(profile, pairs, strings, int(skip))
    low_string, high_string = placement

    voice: Voice = []
    for position, index in enumerate(apply_direction(range(len(pairs)), direction)):
        lower = Note(
            pitch=pairs[index][0],
            string=low_string,
            fret=low_frets[index],
            duration=NOTE_DURATION,
            finger=None,
            accent=False,
        )
        upper = Note(
            pitch=pairs[index][1],
            string=high_string,
            fret=high_frets[index],
            duration=NOTE_DURATION,
            finger=None,
            accent=False,
        )
        voice.extend((upper, lower) if _plays_downward(pattern, position) else (lower, upper))

    score = Score(
        title=_title(root, named, interval, skip, pattern, direction),
        instruction=INSTRUCTION,
        instrument=profile,
        time_signature=DEFAULT_TIME_SIGNATURE,
        tempo_range=DEFAULT_TEMPO_RANGE,
        voice=voice,
        key=key,
        params=dict(params),
    )
    return score, _hints(len(pairs), direction)


def _hints(pair_count: int, direction: str) -> LayoutHints:
    """The §4.2 layout hints for a realized cycle.

    The cell is the pair, two notes to a beat. `up_down` turns around on the top
    pair of the ascending pass — played once — so the seam is that pair's last
    note, at the end of the `pair_count` pairs the pass sounds; `up` and `down`
    have no turnaround, so they offer only the trailing add/drop.
    """
    seam = _NOTES_PER_PAIR * pair_count - 1 if direction == "up_down" else None
    levers: tuple[Lever, ...] = (Lever.ADD_ONE, Lever.DROP_ONE)
    if seam is not None:
        levers = (*levers, Lever.APEX_REPEAT, Lever.APEX_OMIT)
    return layout_hints(cell=_NOTES_PER_PAIR, seam=seam, levers=levers)
