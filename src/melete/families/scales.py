"""`scales` — modes and scale patterns (spec §7, MNEMOSYS H1, H2, H3, H5).

`generate` is a pure function: no I/O, no randomness, no clock. The selector
(§9) chooses the parameters and this module realizes them, which is what makes
a sheet reproducible from its session log and this family testable without any
of the machinery around it. It therefore imports neither `selection` nor
`config`.

The largest family — roughly 24,000 variants before rhythm is applied.

## What one exercise is

One exercise is **one complete cycle of the pattern** (§7) and is never
truncated. Here the cycle is the whole scale across `range_octaves`, closing on
the final octave, reordered by `pattern` and then ordered by `direction`. Two
octaves of a seven-note mode is fifteen degrees, not fourteen: `theory` appends
the closing octave because an exercise stopping a step short of it reads as
unfinished.

## Which notes, then where: two passes, in that order

The pitch content comes from `theory.scale_pitches` and nothing here
reimplements it. The family's own work is the second half of §6's promise —
**it decides where each note is played**, not only which note it is.

Positions are assigned to the *degrees of the ascending scale*, once, before
`pattern` and `direction` are applied. That ordering is the design, not an
implementation convenience: a pattern like `groups_of_3` plays most degrees
three times, and a scale whose notes moved around under the hand between
repetitions would be a different exercise every time it came round.

## The axes, and what this module decided about them

Four of §7's seven axes admit more than one reading. Each is settled here
rather than left to the caller, and the choices are stated because they are
choices:

**`pattern` shapes the sequence and `direction` then orders it.** Every pattern
is a window of degree offsets slid along the scale — `thirds` is `(0, 2)`, so
it emits 1-3, 2-4, 3-5; `groups_of_3` is `(0, 1, 2)`, so it emits 1-2-3, 2-3-4,
3-4-5. Reversing the *patterned* sequence is what a descending figure actually
is: the retrograde of ascending thirds is 15-13, 14-12, 13-11, which is
descending thirds played from the top. Applying `direction` first and then the
pattern would need a second, mirrored implementation of every figure to reach
the same place. `up_down` ascends and returns without replaying the turnaround
degree, exactly as `chromatic` does with its turnaround string.

**`traversal` fixes the note count for three of its four values**, and this is
where a specification most often turns out to be unrealizable.
`three_note_per_string` puts three consecutive degrees on each string, so the
cycle is `3 x len(string_set)` notes; `octave_per_string` puts one octave on
each string, so it needs one string per octave; `single_string` needs exactly
one. When `range_octaves`, `scale_type` and `string_set` disagree about the
length — two octaves of a pentatonic is eleven degrees, which no number of
strings can carry three at a time — the family raises and names the axes that
could not all be satisfied. This is §13's "pool over-constrained" case
verbatim, and §9's validity gate exists to resample it.

**`positional` minimizes total fret travel across the whole cycle.** For each
candidate base fret, every degree takes the position within `string_set`
nearest to it; the base fret with the lowest total distance wins, ties going to
the lower fret, and a degree with two equally near positions goes to the lower
string. A two-octave scale over four strings does not fit in one four-fret box
on any tuning, so this is a genuine minimization rather than a lookup of a
memorized shape — and it is deterministic, which is what reproducibility needs.
The minimization itself is `_shared.boxed`, because `arpeggios` lays out its
chord tones the same way; what stays here is the error it names on failure.

**`finger` is left unspecified.** §6 makes fingering first class because in
*chromatic* permutation work the fingering is the exercise. Here the position
is, and prescribing a finger would engrave a fingering the caller never asked
for. The field is `None`, which §6 defines as unspecified rather than absent.

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
    boxed,
    octaves,
    realizable,
    string_set,
    windowed,
)
from melete.score import Note, Score

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from melete.instrument import InstrumentProfile
    from melete.score import Voice

#: This family's identifier in `vocabulary.AXES["family"]`, and the prefix on
#: every error this module raises (§13). Written once so the two cannot drift.
_FAMILY = "scales"

#: Spec §7's tempo range for this family, in beats per minute. The *family*
#: declares it and the selector never samples it (decision #20); configuration
#: overrides it per family through `[pool.scales] tempo`.
#:
#: Three notes per string in triplet eighths is practised near the top of this
#: range and the bottom of it is a warm-up, which is why the original 80-100 —
#: reasoned from categories rather than from an instrument — printed a tempo
#: nobody works at. §7 carries that reasoning; the number is declared here.
DEFAULT_TEMPO_RANGE = (80, 140)

#: The un-modified reading: one note per beat in common time. `rhythm.py` (§8)
#: is the cross-cutting modifier that re-times a Score into subdivisions and
#: other meters, so this family states the plainest possible rhythm and leaves
#: the subject to the one module that owns it.
DEFAULT_TIME_SIGNATURE = (4, 4)
NOTE_DURATION = Fraction(1, 4)

INSTRUCTION = "Keep the plucking hand even through the string crossings."

#: §7's axis columns. Named here so a missing parameter can list what the
#: family expected rather than only what it did not find.
AXES = (
    "root",
    "scale_type",
    "traversal",
    "string_set",
    "pattern",
    "range_octaves",
    "direction",
)

_POSITIONAL = "positional"
_THREE_NOTE_PER_STRING = "three_note_per_string"
_OCTAVE_PER_STRING = "octave_per_string"
_SINGLE_STRING = "single_string"
_STRAIGHT = "straight"

#: The subset of §7's `traversal` column this family realizes. `vocabulary`
#: carries the union of every family's traversals in one axis, so the family
#: states which of them it can lay out — `across_strings` belongs to
#: `arpeggios`.
_TRAVERSALS = (_POSITIONAL, _THREE_NOTE_PER_STRING, _OCTAVE_PER_STRING, _SINGLE_STRING)

#: Each pattern as the degree offsets of one window, slid one degree at a time
#: along the scale. `straight` is the identity window; §7's "numeric
#: permutations (1-2-3-5)" is `(0, 1, 2, 4)`.
#:
#: The widest window spans five degrees and the shortest cycle this family can
#: produce is one octave of a pentatonic, which is six, so no pattern can be
#: starved of degrees to slide along.
_PATTERN_WINDOWS: dict[str, tuple[int, ...]] = {
    _STRAIGHT: (0,),
    "thirds": (0, 2),
    "fourths": (0, 3),
    "groups_of_3": (0, 1, 2),
    "groups_of_4": (0, 1, 2, 3),
    "numeric_1235": (0, 1, 2, 4),
}

#: The axes a `positional` layout names when a degree is out of reach (§13).
#: `_shared.boxed` raises with this rather than a sentence of its own, because
#: naming *this family's* axes is the whole of what the error is for.
_POSITIONAL_AXES = "root, scale_type, range_octaves and string_set"

#: How many degrees `three_note_per_string` puts on each string. Named because
#: the identifier and the number must not be able to disagree.
_NOTES_PER_STRING = 3


def _chunk_sizes(traversal: str, degrees: int, octave_count: int, strings: int) -> list[int]:
    """How many consecutive degrees each string carries, in playing order.

    The closing octave joins the last string of an `octave_per_string` layout
    rather than starting a string of its own: it is the resolution of the
    octave below it, not a new one.
    """
    if traversal == _SINGLE_STRING:
        return [degrees]
    if traversal == _THREE_NOTE_PER_STRING:
        return [_NOTES_PER_STRING] * strings
    per_octave = (degrees - 1) // octave_count
    return [*[per_octave] * (octave_count - 1), per_octave + 1]


def _laid_out(
    profile: InstrumentProfile,
    pitches: Sequence[int],
    strings: tuple[int, ...],
    sizes: Sequence[int],
) -> list[tuple[int, int]]:
    """Consecutive runs of degrees on consecutive strings, one run per string."""
    places: list[tuple[int, int]] = []
    start = 0
    for string, size in zip(strings, sizes, strict=True):
        for pitch in pitches[start : start + size]:
            fret = pitch - profile.tuning[string]
            if not 0 <= fret <= profile.fret_count:
                msg = (
                    f"{_FAMILY}: pitch {pitch} needs fret {fret} on string {string} of profile "
                    f"{profile.name!r}, which has frets 0 to {profile.fret_count}. The cycle "
                    f"is never truncated to fit (§7), so this specification is unrealizable "
                    f"rather than shorter"
                )
                raise ValueError(msg)
            places.append((string, fret))
        start += size
    return places


def _places(
    profile: InstrumentProfile,
    pitches: Sequence[int],
    strings: tuple[int, ...],
    traversal: str,
    scale_type: str,
    octave_count: int,
) -> list[tuple[int, int]]:
    """Where each degree of the ascending scale is played, in scale order."""
    if traversal == _POSITIONAL:
        return boxed(profile, pitches, strings, _FAMILY, _POSITIONAL_AXES)

    sizes = _chunk_sizes(traversal, len(pitches), octave_count, len(strings))
    if len(sizes) != len(strings) or sum(sizes) != len(pitches):
        msg = (
            f"{_FAMILY}: traversal {traversal!r} needs {len(sizes)} strings carrying "
            f"{sum(sizes)} degrees, but string_set {list(strings)} has {len(strings)} "
            f"and {octave_count} octaves of {scale_type!r} has {len(pitches)}. traversal, "
            f"string_set, range_octaves and scale_type cannot all be satisfied at once; "
            f"§9 resamples this rather than truncating the cycle"
        )
        raise ValueError(msg)
    return _laid_out(profile, pitches, strings, sizes)


def _title(root: int, scale_type: str, traversal: str, pattern: str, direction: str) -> str:
    """The plain-language name §12's cover page prints, built from the registry."""
    figure = vocabulary.display("direction", direction)
    if pattern != _STRAIGHT:
        figure = f"{figure} {vocabulary.display('pattern', pattern)}"
    return (
        f"{theory.PITCH_CLASSES[root % len(theory.PITCH_CLASSES)]} "
        f"{vocabulary.display('scale_type', scale_type)}, "
        f"{vocabulary.display('traversal', traversal)}, {figure}"
    )


def generate(profile: InstrumentProfile, params: Mapping[str, object]) -> Score:
    """Realize one scale exercise on `profile`.

    Pure: the same profile and parameters always produce the same Score. Extra
    keys in `params` are carried into the Score untouched rather than rejected
    — §8's rhythm axes travel in the same dictionary — but every axis this
    family reads is required, so a misspelled one is a loud failure and never a
    silent default.
    """
    read = Parameters(_FAMILY, AXES, params)
    root = read.integer("root")
    scale_type = read.identifier("scale_type")
    traversal = realizable(read, "traversal", _TRAVERSALS)
    pattern = realizable(read, "pattern", tuple(_PATTERN_WINDOWS))
    direction = read.identifier("direction")
    octave_count = octaves(read)
    strings = string_set(read, profile)

    pitches = theory.scale_pitches(root, scale_type, octave_count)
    places = _places(profile, pitches, strings, traversal, scale_type, octave_count)
    order = apply_direction(windowed(_PATTERN_WINDOWS[pattern], len(pitches)), direction)

    voice: Voice = [
        Note(
            pitch=pitches[degree],
            string=places[degree][0],
            fret=places[degree][1],
            duration=NOTE_DURATION,
            finger=None,
            accent=False,
        )
        for degree in order
    ]

    return Score(
        title=_title(root, scale_type, traversal, pattern, direction),
        instruction=INSTRUCTION,
        instrument=profile,
        time_signature=DEFAULT_TIME_SIGNATURE,
        tempo_range=DEFAULT_TEMPO_RANGE,
        voice=voice,
        # §10a: the exercise is spelled against its own scale, and `root`
        # reduces to a pitch class because A1 and A2 are the same key.
        key=theory.Key(root % len(theory.PITCH_CLASSES), scale_type),
        params=dict(params),
    )
