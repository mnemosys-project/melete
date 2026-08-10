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
from melete.instrument import positions
from melete.score import Note, Score

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from melete.instrument import InstrumentProfile
    from melete.score import Voice

#: Spec §7's tempo range for this family, in beats per minute. The *family*
#: declares it and the selector never samples it (decision #20); configuration
#: overrides it per family through `[pool.scales] tempo`.
#:
#: §7's table says 80-100. That reading of "the reference range in §12's
#: cover-page example" is too slow for the material: three notes per string in
#: triplet eighths is practised at 120-140, and a range that tops out at 100
#: would print a tempo nobody works at.
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

#: §7's `range_octaves` column.
_RANGE_OCTAVES = (1, 2, 3)

#: How many degrees `three_note_per_string` puts on each string. Named because
#: the identifier and the number must not be able to disagree.
_NOTES_PER_STRING = 3


def _parameter(params: Mapping[str, object], axis: str) -> object:
    """One parameter, or an error naming the axis and the full set (§13)."""
    if axis not in params:
        msg = f"scales: parameter {axis!r} is required; the family's axes are {list(AXES)}"
        raise ValueError(msg)
    return params[axis]


def _identifier(params: Mapping[str, object], axis: str) -> str:
    """One registry identifier, checked against `vocabulary` and nothing else."""
    value = _parameter(params, axis)
    if not isinstance(value, str) or value not in vocabulary.AXES[axis]:
        msg = f"scales: unknown {axis} {value!r}; accepted: {vocabulary.accepted(axis)}"
        raise ValueError(msg)
    return value


def _integer(params: Mapping[str, object], axis: str) -> int:
    """One range-like axis. `bool` is rejected: `True` is not root 1."""
    value = _parameter(params, axis)
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"scales: {axis} must be an integer, got {value!r}"
        raise ValueError(msg)
    return value


def _realizable(params: Mapping[str, object], axis: str, accepted: tuple[str, ...]) -> str:
    """One identifier from the subset of a shared axis this family realizes.

    `vocabulary` carries the union of every family's values for `traversal` and
    `pattern`, because the selector samples one axis. A value belonging to
    another family is rejected here by name rather than dispatched into a
    branch that does not exist.
    """
    value = _identifier(params, axis)
    if value not in accepted:
        realized = list(accepted)
        msg = f"scales: {axis} {value!r} belongs to another family; scales realizes {realized}"
        raise ValueError(msg)
    return value


def _octaves(params: Mapping[str, object]) -> int:
    """The `range_octaves` axis, which §7 enumerates rather than leaves open."""
    value = _integer(params, "range_octaves")
    if value not in _RANGE_OCTAVES:
        msg = f"scales: range_octaves must be one of {list(_RANGE_OCTAVES)}, got {value}"
        raise ValueError(msg)
    return value


def _string_set(params: Mapping[str, object], profile: InstrumentProfile) -> tuple[int, ...]:
    """The strings the exercise is laid across, low to high.

    Strictly ascending and validated rather than repaired, for the reason
    `instrument` refuses to re-sort a tuning: re-ordering or de-duplicating the
    set would engrave a different string set from the one the selector drew,
    and §9's coverage accounting would have no way to see the substitution.
    """
    value = _parameter(params, "string_set")
    if not isinstance(value, list | tuple) or not value:
        msg = f"scales: string_set must be a non-empty sequence of string indices, got {value!r}"
        raise ValueError(msg)

    strings = tuple(value)
    if any(isinstance(item, bool) or not isinstance(item, int) for item in strings):
        msg = f"scales: string_set must hold integer string indices, got {value!r}"
        raise ValueError(msg)

    if list(strings) != sorted(set(strings)):
        msg = (
            f"scales: string_set {list(strings)} must be strictly ascending with no "
            f"repeats; index 0 is the lowest string, and re-sorting it here would "
            f"engrave a different string set from the one that was specified"
        )
        raise ValueError(msg)

    last = len(profile.tuning) - 1
    if strings[0] < 0 or strings[-1] > last:
        msg = (
            f"scales: string_set {list(strings)} is off profile {profile.name!r}, "
            f"which has strings 0 to {last}"
        )
        raise ValueError(msg)
    return strings


def _patterned(pattern: str, degrees: int) -> list[int]:
    """Degree indices in playing order, before `direction` is applied."""
    window = _PATTERN_WINDOWS[pattern]
    return [start + offset for start in range(degrees - max(window)) for offset in window]


def _directed(indices: Sequence[int], direction: str) -> list[int]:
    """`indices` ordered by §7's `direction` axis."""
    if direction == "up":
        return list(indices)
    if direction == "down":
        return list(reversed(indices))
    # up_down: back down without replaying the turnaround degree.
    return [*indices, *indices[-2::-1]]


def _reachable(
    profile: InstrumentProfile,
    pitch: int,
    strings: tuple[int, ...],
) -> list[tuple[int, int]]:
    """Every place within `strings` that sounds `pitch`, lowest string first."""
    places = [place for place in positions(profile, pitch) if place[0] in strings]
    if not places:
        msg = (
            f"scales: pitch {pitch} is unreachable on strings {list(strings)} of profile "
            f"{profile.name!r}, which has frets 0 to {profile.fret_count}: root, "
            f"scale_type, range_octaves and string_set cannot all be satisfied on this "
            f"instrument"
        )
        raise ValueError(msg)
    return places


def _boxed(
    profile: InstrumentProfile,
    pitches: Sequence[int],
    strings: tuple[int, ...],
) -> list[tuple[int, int]]:
    """The `positional` layout: the base fret minimizing total fret travel."""
    choices = [_reachable(profile, pitch, strings) for pitch in pitches]

    def travel(base: int) -> int:
        return sum(min(abs(fret - base) for _string, fret in places) for places in choices)

    # `min` keeps the first of equal keys, so ties go to the lower fret.
    base = min(range(profile.fret_count + 1), key=travel)
    return [min(places, key=lambda place: (abs(place[1] - base), place[0])) for places in choices]


def _chunk_sizes(traversal: str, degrees: int, octaves: int, strings: int) -> list[int]:
    """How many consecutive degrees each string carries, in playing order.

    The closing octave joins the last string of an `octave_per_string` layout
    rather than starting a string of its own: it is the resolution of the
    octave below it, not a new one.
    """
    if traversal == _SINGLE_STRING:
        return [degrees]
    if traversal == _THREE_NOTE_PER_STRING:
        return [_NOTES_PER_STRING] * strings
    per_octave = (degrees - 1) // octaves
    return [*[per_octave] * (octaves - 1), per_octave + 1]


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
                    f"scales: pitch {pitch} needs fret {fret} on string {string} of profile "
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
    octaves: int,
) -> list[tuple[int, int]]:
    """Where each degree of the ascending scale is played, in scale order."""
    if traversal == _POSITIONAL:
        return _boxed(profile, pitches, strings)

    sizes = _chunk_sizes(traversal, len(pitches), octaves, len(strings))
    if len(sizes) != len(strings) or sum(sizes) != len(pitches):
        msg = (
            f"scales: traversal {traversal!r} needs {len(sizes)} strings carrying "
            f"{sum(sizes)} degrees, but string_set {list(strings)} has {len(strings)} "
            f"and {octaves} octaves of {scale_type!r} has {len(pitches)}. traversal, "
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
    root = _integer(params, "root")
    scale_type = _identifier(params, "scale_type")
    traversal = _realizable(params, "traversal", _TRAVERSALS)
    pattern = _realizable(params, "pattern", tuple(_PATTERN_WINDOWS))
    direction = _identifier(params, "direction")
    octaves = _octaves(params)
    strings = _string_set(params, profile)

    pitches = theory.scale_pitches(root, scale_type, octaves)
    places = _places(profile, pitches, strings, traversal, scale_type, octaves)
    order = _directed(_patterned(pattern, len(pitches)), direction)

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
        params=dict(params),
    )
