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
distance on the instrument — a lower note off the neck, or a partner that runs
off the top or below the nut on its string — is **invalid** and raises, naming
what could not be satisfied; §9's validity gate resamples it. Quietly settling
for an adjacent string would engrave a plausible exercise that is not the one
that was requested, which is the §13 failure mode this project exists to avoid
— and it would be undetectable from the notation staff, because the pitches
would be right.

**The journey climbs the instrument, one string pair at a time (epic #72).**
Every exercise is a computed outer-to-outer up-and-down journey: the lower notes
box across the *lower* strings under the shared fingering journey
(`journey.boxed_span`), and every lower note's partner sits exactly
`string_skip + 1` strings above it, so the upper voice reaches the opposite outer
string. The lower voice is placed on a profile sliced to leave that much room
above — the top `string_skip + 1` strings are the partner's, never the lower
note's — which is what lets the pair distance stay a hard constraint while the
two voices together cover the whole instrument, low outer string to high outer
string, with no gap. Extent is governed by reaching the opposite outer string and
the octave count is emergent (spec §5), replacing the sampled
`string_set`/`direction`/octave draws.

**`pattern` orders the two notes inside a pair; the pairs always go up and
down.** The pairs are ordered by the single direction this epic produces —
`journey.updown`, ascend then the retrograde of the ascent — so `direction` is
no longer sampled or read. `pattern` still names which note of a pair comes
first: `ascending_pairs` plays the lower note first, `descending_pairs` the
upper, and `alternating` turns every other pair around, counted over the pairs
as played so it keeps alternating through the turnaround rather than restarting.
Reversing the whole note sequence instead would turn `descending_pairs` into
ascending ones while §12's cover page still printed "descending pairs" — a sheet
that is not the exercise it names — which is why `pattern` is an intra-pair
order and the journey supplies the retrograde around it.

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
from melete.families import journey
from melete.families._shared import (
    Parameters,
    layout_hints,
    realizable,
)
from melete.instrument import InstrumentProfile
from melete.layout import Lever
from melete.score import Note, Score

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

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

#: §7's axis columns, less the two the journey redesign retired (epic #72):
#: `string_set` (coverage is the whole instrument now, §4/§5) and `direction`
#: (always up-and-down, §5). Named here so a missing parameter can list what the
#: family expected rather than only what it did not find. `root` is read in both
#: contexts — every exercise starts somewhere — and `scale_type` only in the
#: diatonic one, which is what §7's "diatonic within root + scale" says.
AXES = (
    "interval",
    "context",
    "root",
    "scale_type",
    "string_skip",
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

#: The axes the journey placement names when a note runs off the neck (§13).
#: `journey.boxed_span` and the partner placement below raise with this rather
#: than a sentence each, because naming *this family's* axes is the whole of
#: what the error is for.
_JOURNEY_AXES = "interval, context, root, scale_type and string_skip"

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


def _chromatic_pairs(root: int, interval: int, count: int) -> list[tuple[int, int]]:
    """`count` lower notes a semitone apart, each with its exact partner."""
    step = _semitones(interval)
    return [(root + offset, root + offset + step) for offset in range(count)]


def _diatonic_pairs(root: int, scale_type: str, interval: int, count: int) -> list[tuple[int, int]]:
    """`count` scale degrees climbing from the root, each with the degree above it.

    The upper note is `interval - 1` *degrees* away, not a fixed semitone
    count, which is what makes a diatonic third minor on some degrees and major
    on others. Enough octaves are built that the top pair still has a partner to
    reach for; the closing octave `scale_pitches` appends does not matter because
    the degrees repeat past it anyway.
    """
    degrees_per_octave = len(theory.SCALES[scale_type])
    step = interval - 1
    octaves = -(-(count + step + 1) // degrees_per_octave) + 1
    degrees = theory.scale_pitches(root, scale_type, octaves)
    return [(degrees[index], degrees[index + step]) for index in range(count)]


def _place_journey(
    profile: InstrumentProfile,
    supply: Sequence[tuple[int, int]],
    skip: int,
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Place the leading run of `supply` pairs that fits one hand across the strings.

    `supply` is a long ascending run of `(lower, upper)` pairs; the journey uses
    only its leading prefix — as many as fit one hand position — so the extent and
    octave count are emergent, governed by reaching the opposite outer string
    rather than a sampled target (spec §5). The lower voice is boxed across the
    *lower* strings under `journey.boxed_span`, and each upper note then sits
    exactly `skip + 1` strings above its partner, so the upper voice reaches the
    high outer string and the two together cover the whole instrument with no gap
    (spec §4). The lower voice is laid on a profile sliced to leave the partner's
    strings free at the top — the pair distance stays a hard constraint, never
    satisfied by moving the lower note up into the partner's range.

    A partner that runs off the neck raises, naming the axes that could not all be
    satisfied (§13); §9 resamples an over-constrained draw rather than engraving a
    nearer exercise. The returned lists are the used prefix, one place per pair.
    """
    distance = skip + 1
    strings = len(profile.tuning)
    lower_strings = strings - distance
    if lower_strings < 1:
        msg = (
            f"{_FAMILY}: string_skip {skip} needs a partner {distance} strings above every lower "
            f"note, but profile {profile.name!r} has only {strings} strings, leaving no room for "
            f"the lower voice to climb. string_skip is a hard constraint on where a pair is "
            f"played, not a preference; §9 resamples this rather than narrowing the skip"
        )
        raise ValueError(msg)

    # `journey.boxed_span` boxes the lower voice across the lower strings only; the
    # top `distance` strings are the partner's. Slicing the tuning is what pins the
    # pair distance while the journey stays the shared one every family computes.
    lower_profile = InstrumentProfile(
        profile.name, profile.tuning[:lower_strings], profile.fret_count, profile.position_span
    )
    lows = [low for low, _high in supply]

    # The journey anchors on the low outer string; if its first note cannot sound
    # there the ascent has nowhere to start, and `boxed_span` would otherwise fault
    # on an empty anchor search. Name it as the §13 over-constraint it is.
    base_fret = lows[0] - lower_profile.tuning[0]
    if not 0 <= base_fret <= profile.fret_count:
        msg = (
            f"{_FAMILY}: the journey's first note {lows[0]} needs fret {base_fret} on the low "
            f"string of {profile.name!r} (frets 0..{profile.fret_count}); {_JOURNEY_AXES} cannot "
            f"all be satisfied. §9 resamples this rather than starting the journey off the neck"
        )
        raise ValueError(msg)

    used, low_places = journey.boxed_span(lower_profile, lows, _FAMILY, _JOURNEY_AXES)

    high_places: list[tuple[int, int]] = []
    for (_low, high), (low_string, _low_fret) in zip(supply[: len(used)], low_places, strict=True):
        high_string = low_string + distance
        high_fret = high - profile.tuning[high_string]
        if not 0 <= high_fret <= profile.fret_count:
            msg = (
                f"{_FAMILY}: the partner {high} needs fret {high_fret} on string {high_string} of "
                f"{profile.name!r} (frets 0..{profile.fret_count}); a string_skip {skip} pair "
                f"cannot be placed there. {_JOURNEY_AXES} cannot all be satisfied at once, and §9 "
                f"resamples this rather than moving the note to a string it was not asked for"
            )
            raise ValueError(msg)
        high_places.append((high_string, high_fret))
    return low_places, high_places


def _plays_downward(pattern: str, position: int) -> bool:
    """Whether the pair in this position is played upper note first."""
    if pattern == _ASCENDING_PAIRS:
        return False
    if pattern == _DESCENDING_PAIRS:
        return True
    return position % 2 == 1


def _title(root: int, named: str, interval: int, skip: str, pattern: str) -> str:
    """The plain-language name §12's cover page prints, built from the registry.

    `named` is what the context is called: the scale for a diatonic sequence,
    and the word "chromatic" for one with no scale to name. The direction is no
    longer stated — every journey is up-and-down (epic #72), so a word that never
    varies would only be noise on the cover page.
    """
    return (
        f"{theory.PITCH_CLASSES[root % _SEMITONES_PER_OCTAVE]} {named} "
        f"{INTERVAL_NAMES[interval]}, {vocabulary.display('string_skip', skip)}, "
        f"{vocabulary.display('pattern', pattern)}"
    )


def generate(profile: InstrumentProfile, params: Mapping[str, object]) -> tuple[Score, LayoutHints]:
    """Realize one interval or string-skipping exercise on `profile`, with hints.

    Pure: the same profile and parameters always produce the same Score. Extra
    keys in `params` are carried into the Score untouched rather than rejected
    — §8's rhythm axes travel in the same dictionary — but every axis this
    family reads is required, so a misspelled one is a loud failure and never a
    silent default.

    The §4.2 hints report the pair as the natural cell — two notes to a beat —
    and the note index of the apex the pairs turn around at, so the fitter's apex
    levers know where to act. Every journey is up-and-down now (epic #72), so the
    seam is always present.
    """
    read = Parameters(_FAMILY, AXES, params)
    interval = _interval(read)
    context = read.identifier("context")
    root = read.integer("root")
    skip = read.identifier("string_skip")
    pattern = realizable(read, "pattern", _PATTERNS)

    # A generous ascending supply of pairs; `journey.boxed_span` consumes only
    # the leading run that fits one hand position across the strings and stops, so
    # the extent is emergent (spec §5) and this length just has to exceed what any
    # one box can hold — a box spans at most every string, `position_span + 1`
    # frets each.
    supply = len(profile.tuning) * (profile.position_span + 2)

    if context == _DIATONIC:
        scale_type = read.identifier("scale_type")
        pairs = _diatonic_pairs(root, scale_type, interval, supply)
        named = vocabulary.display("scale_type", scale_type)
        # §10a: the intervals are degrees of this scale, so they are spelled by
        # it. `root` reduces to a pitch class because A1 and A2 are the same key.
        key: theory.Key | None = theory.Key(root % _SEMITONES_PER_OCTAVE, scale_type)
    else:
        pairs = _chromatic_pairs(root, interval, supply)
        named = vocabulary.display("context", context)
        # Stated rather than left to the default: a chromatic interval sequence
        # asserts no tonal center, so this branch is tier 3 by definition (§10a)
        # and spells by direction. `None` is the answer here, not the omission
        # it would be in the diatonic branch, which has a key to give.
        key = None

    low_places, high_places = _place_journey(profile, pairs, int(skip))
    # Only the leading prefix `boxed_span` used is engraved (its length is one
    # place per pair); the rest of the supply was never on the neck.
    pairs = pairs[: len(low_places)]

    voice: Voice = []
    # The journey is the single direction this epic produces: ascend the pairs,
    # then the retrograde of the ascent without replaying the apex pair (§5).
    for position, index in enumerate(journey.updown(range(len(pairs)), cell=1)):
        lower = Note(
            pitch=pairs[index][0],
            string=low_places[index][0],
            fret=low_places[index][1],
            duration=NOTE_DURATION,
            finger=None,
            accent=False,
        )
        upper = Note(
            pitch=pairs[index][1],
            string=high_places[index][0],
            fret=high_places[index][1],
            duration=NOTE_DURATION,
            finger=None,
            accent=False,
        )
        voice.extend((upper, lower) if _plays_downward(pattern, position) else (lower, upper))

    score = Score(
        title=_title(root, named, interval, skip, pattern),
        instruction=INSTRUCTION,
        instrument=profile,
        time_signature=DEFAULT_TIME_SIGNATURE,
        tempo_range=DEFAULT_TEMPO_RANGE,
        voice=voice,
        key=key,
        params=dict(params),
    )
    return score, _hints(len(pairs))


def _hints(pair_count: int) -> LayoutHints:
    """The §4.2 layout hints for a realized cycle.

    The cell is the pair, two notes to a beat. The journey turns around on the
    top pair of the ascending pass — played once — so the seam is that pair's
    last note, at the end of the `pair_count` pairs the pass sounds. Every
    journey is up-and-down (epic #72), so the apex levers are always offered
    alongside the trailing add/drop.
    """
    seam = _NOTES_PER_PAIR * pair_count - 1
    levers: tuple[Lever, ...] = (
        Lever.ADD_ONE,
        Lever.DROP_ONE,
        Lever.APEX_REPEAT,
        Lever.APEX_OMIT,
    )
    return layout_hints(cell=_NOTES_PER_PAIR, seam=seam, levers=levers)
