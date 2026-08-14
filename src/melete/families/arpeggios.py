"""`arpeggios` — chord tones (spec §6, §7, MNEMOSYS A1, A2).

`generate` is a pure function: no I/O, no randomness, no clock. The selector
(§9) chooses the parameters and this module realizes them, which is what makes
a sheet reproducible from its session log and this family testable without any
of the machinery around it. It therefore imports neither `selection` nor
`config`.

## What one exercise is

One exercise is the chord's up-and-down *journey* across the instrument (spec
§5): the tones ascend from the root on the lowest string, laid out by the
quality's canonical seed shape, until the shape reaches the opposite outer
string, and then return without replaying the turnaround. Extent and octave
count are emergent — they fall out of reaching the top string — rather than a
sampled target, exactly as `scales` and every other family now compute their
geometry (spec §8). Direction is never sampled: the journey is always up and
down (`journey.updown`).

## Which notes, then where: two passes, in that order

The pitch content comes from `theory.chord_pitches` and nothing here
reimplements chord maths. The family's own work is the second half of §6's
promise — **it decides where each note is played**, not only which note it is —
and it delegates that placement to `arpeggio_shapes.shape_places`, which tiles
one canonical seed shape per quality up the strings. Positions are assigned to
the *ascending chord tones*, once, before `pattern` is applied: a pattern like
`numeric_1353` plays most tones three times, and a chord whose tones moved
around under the hand between repetitions would be a different exercise every
time it came round.

## The axes, and what this module decided about them

**Arpeggios have one layout in v1 — the seed shape.** The `traversal` axis is
gone (spec §6, §8): its three former values (`positional`, `across_strings`,
`single_string`) would all now route through `shape_places` to identical output,
so keeping it would be a no-op axis §9's coverage accounting could not tell
apart. The single/two-string modes are deferred (spec §13). The
`direction`, `string_set` and `range_octaves` axes are gone for the same reason
they left every family: direction is always up-and-down, the string set is the
whole instrument outer-to-outer, and the octave count is emergent.

**`inversion` is a registry identifier, not a rotation count.** §7 writes the
column as root/first/second/third, `vocabulary` carries those four identifiers
and `config` samples the axis through the same `_registry` path as every other
identifier, so that is what arrives here. The bare integer
`theory.chord_pitches` takes is an implementation detail of `theory`, and
`INVERSIONS` is the one place the two meet: a value's *position* in it is the
rotation count. An inversion the chord cannot support — a triad's third — is
rejected by `theory` and the refusal is allowed through unwrapped, because its
message already names the quality and the range it accepted.

**`pattern` shapes the sequence and the journey then orders it**, the same way
round as in `scales`. Each pattern is a window of tone offsets slid along the
ascending chord: `numeric_1353` is `(0, 1, 2, 1)`, so it emits 1-3-5-3, 3-5-7-5;
`broken` is `(0, 2)`, which skips a tone and comes back for it. `sweep_ordered`
is the three-tone window `(0, 1, 2)` — the arpeggio rolled up in overlapping
three-note sweeps, which is how sweep picking is drilled.

**`finger` is left unspecified.** §6 makes fingering first class because in
*chromatic* permutation work the fingering is the exercise. Here the position
is, and prescribing a finger would engrave a fingering the caller never asked
for. The field is `None`, which §6 defines as unspecified rather than absent.

## The key, and what it costs the fully diminished seventh

§10a: chords are spelled by function, and `theory.IMPLIED_PARENT` is what turns
that into the one `Key` mechanism the scales already use — the chord tones fall
out as a subset of the parent's spelling. Stating the key costs this family
nothing, because it already holds the root and the quality; *not* stating it
would cost every note on the sheet its spelling, silently, because a key-less
Score still constructs and still engraves.

## Running off the neck

A specification that cannot be laid out as a full journey to the top string
raises, naming the axes that could not be satisfied. It is never clamped to fit
— a clamped exercise is a plausible-looking sheet that is not the one the
selector drew, and §9's validity gate exists precisely to resample this case.
"""

from __future__ import annotations

from fractions import Fraction
from typing import TYPE_CHECKING

from melete import theory, vocabulary
from melete.families._shared import Parameters, layout_hints, realizable, windowed
from melete.families.arpeggio_shapes import shape_places
from melete.families.journey import updown
from melete.layout import Lever
from melete.score import Note, Score

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from melete.instrument import InstrumentProfile
    from melete.layout import LayoutHints
    from melete.score import Voice

#: This family's identifier in `vocabulary.AXES["family"]`, and the prefix on
#: every error this module raises (§13). Written once so the two cannot drift.
_FAMILY = "arpeggios"

#: Spec §7's tempo range for this family, in beats per minute. The *family*
#: declares it and the selector never samples it (decision #20); configuration
#: overrides it per family through `[pool.arpeggios] tempo`.
#:
#: The demand here is comparable to `scales`, so the range is the same one.
DEFAULT_TEMPO_RANGE = (80, 140)

#: The un-modified reading: one note per beat in common time. `rhythm.py` (§8)
#: is the cross-cutting modifier that re-times a Score into subdivisions and
#: other meters, so this family states the plainest possible rhythm and leaves
#: the subject to the one module that owns it.
DEFAULT_TIME_SIGNATURE = (4, 4)
NOTE_DURATION = Fraction(1, 4)

INSTRUCTION = "Name each chord tone as it sounds; keep the string crossings even."

#: §7's axis columns this family reads, after epic #72 retired the geometry axes
#: (`direction`, `string_set`, `range_octaves`) and the now-redundant `traversal`
#: (arpeggios have one layout in v1 — the seed shape). Named here so a missing
#: parameter can list what the family expected rather than only what it did not
#: find.
AXES = (
    "root",
    "quality",
    "inversion",
    "pattern",
)

#: §7's `inversion` column, and the one place its identifiers meet the integer
#: rotation count `theory.chord_pitches` takes: a value's *position* here is
#: that count. `theory` decides whether the chord can support it — a triad has
#: no third inversion — so nothing is enumerated twice.
INVERSIONS: tuple[str, ...] = ("root", "first", "second", "third")

_STRAIGHT = "straight"

#: Each pattern as the tone offsets of one window, slid one chord tone at a
#: time along the ascending chord. `straight` is the identity window.
#:
#: The widest window spans three tones and the shortest journey this family can
#: produce reaches the top string over several octaves, so no pattern can be
#: starved of tones to slide along.
_PATTERN_WINDOWS: dict[str, tuple[int, ...]] = {
    _STRAIGHT: (0,),
    "numeric_1353": (0, 1, 2, 1),
    "broken": (0, 2),
    "sweep_ordered": (0, 1, 2),
}

_SEMITONES_PER_OCTAVE = len(theory.PITCH_CLASSES)

#: Strings an octave spans in perfect-fourths tuning — the same step
#: `arpeggio_shapes` tiles the seed by, so the two cannot disagree about how far
#: up the neck a higher octave sits.
_OCTAVE_STRING_STEP = 2


def _tones_to_the_top(octave_len: int, top: int) -> int:
    """How many ascending tones the seed lays out before one lands on `top`.

    The seed places tone `index` on string `(index % octave_len) +
    _OCTAVE_STRING_STEP * (index // octave_len)` (one tone per string, an octave
    two strings up), mirroring `arpeggio_shapes.shape_places`. Every string is
    reached in turn, so `top` is always hit exactly; the count is the index that
    first lands on it, plus one.
    """
    index = 0
    while (index % octave_len) + _OCTAVE_STRING_STEP * (index // octave_len) != top:
        index += 1
    return index + 1


def _journey(
    profile: InstrumentProfile,
    root: int,
    quality: str,
    inversion: str,
) -> tuple[list[int], list[tuple[int, int]]]:
    """Ascending chord tones placed by the seed shape, low string to top string.

    The tones climb from the root's placement on the lowest instrument string,
    laid out by `arpeggio_shapes.shape_places`, until the shape reaches the
    opposite outer string — the point where the journey turns around (spec §5).
    Extent and octave count are emergent, never a sampled target: the count of
    tones is exactly what it takes the seed to reach the top string.

    `shape_places` is the authority on placement, so its refusals propagate
    unwrapped (§13): an unknown quality, or a tone that runs off the neck before
    the top string — the "unrealizable journey" §9 resamples rather than
    engraving a short arpeggio.
    """
    chord = theory.chord_pitches(root, quality, INVERSIONS.index(inversion))
    root_place = (0, root - profile.tuning[0])
    top = len(profile.tuning) - 1

    count = _tones_to_the_top(len(chord), top)
    tones = [
        chord[index % len(chord)] + _SEMITONES_PER_OCTAVE * (index // len(chord))
        for index in range(count)
    ]
    places = shape_places(profile, root_place, quality, tones)
    return tones, places


def _title(root: int, quality: str, inversion: str, pattern: str) -> str:
    """The plain-language name §12's cover page prints, built from the registry.

    The journey is always up-and-down (spec §5), so the title states no
    direction: what it names is the chord, its inversion when there is one, and
    the pattern figure when it is not the plain reading.
    """
    name = (
        f"{theory.PITCH_CLASSES[root % _SEMITONES_PER_OCTAVE]} "
        f"{vocabulary.display('quality', quality)}"
    )
    if inversion != INVERSIONS[0]:
        name += f", {vocabulary.display('inversion', inversion)}"
    if pattern != _STRAIGHT:
        name += f", {vocabulary.display('pattern', pattern)}"
    return name


def generate(profile: InstrumentProfile, params: Mapping[str, object]) -> tuple[Score, LayoutHints]:
    """Realize one arpeggio exercise on `profile`, with the §4.2 layout hints.

    Pure: the same profile and parameters always produce the same Score. Extra
    keys in `params` are carried into the Score untouched rather than rejected
    — §8's rhythm axes travel in the same dictionary — but every axis this
    family reads is required, so a misspelled one is a loud failure and never a
    silent default.

    The voice is the up-and-down seed-shape journey (spec §5): the chord tones
    are placed once by `arpeggio_shapes.shape_places` from the root on the lowest
    string, `pattern` slides its window along the ascent, and `journey.updown`
    orders the result up and back without replaying the apex.

    The hints are the fitter's window onto what the voice alone does not carry:
    the natural cell is one turn of the `pattern` window, and the journey names
    the apex it turns around at so the fitter's apex levers know where to act.
    """
    read = Parameters(_FAMILY, AXES, params)
    root = read.integer("root")
    quality = read.identifier("quality")
    inversion = read.identifier("inversion")
    pattern = realizable(read, "pattern", tuple(_PATTERN_WINDOWS))

    tones, places = _journey(profile, root, quality, inversion)
    window = _PATTERN_WINDOWS[pattern]
    ascending = windowed(window, len(tones))
    order = updown(ascending, len(window))

    voice: Voice = [
        Note(
            pitch=tones[tone],
            string=places[tone][0],
            fret=places[tone][1],
            duration=NOTE_DURATION,
            finger=None,
            accent=False,
        )
        for tone in order
    ]

    score = Score(
        title=_title(root, quality, inversion, pattern),
        instruction=INSTRUCTION,
        instrument=profile,
        time_signature=DEFAULT_TIME_SIGNATURE,
        tempo_range=DEFAULT_TEMPO_RANGE,
        voice=voice,
        # §10a: a chord is spelled by function, and the implied parent is what
        # turns that into the one `Key` mechanism the scales use. `root`
        # reduces to a pitch class because A1 and A2 are the same key.
        key=theory.Key(root % _SEMITONES_PER_OCTAVE, theory.IMPLIED_PARENT[quality]),
        params=dict(params),
    )
    return score, _hints(window, ascending)


def _hints(window: tuple[int, ...], ascending: Sequence[int]) -> LayoutHints:
    """The §4.2 layout hints for a realized journey.

    The cell is one turn of the `pattern` window. The journey is always
    up-and-down (spec §5): `journey.updown` turns around at a cell boundary — the
    apex cell of the ascending pass, played once — so the seam is that cell's
    last note and the apex levers become legal.
    """
    return layout_hints(
        cell=len(window),
        seam=len(ascending) - 1,
        levers=(Lever.ADD_ONE, Lever.DROP_ONE, Lever.APEX_REPEAT, Lever.APEX_OMIT),
    )
