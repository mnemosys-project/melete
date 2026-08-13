"""`arpeggios` — chord tones (spec §7, MNEMOSYS A1, A2).

`generate` is a pure function: no I/O, no randomness, no clock. The selector
(§9) chooses the parameters and this module realizes them, which is what makes
a sheet reproducible from its session log and this family testable without any
of the machinery around it. It therefore imports neither `selection` nor
`config`.

## What one exercise is

One exercise is **one complete cycle of the pattern** (§7) and is never
truncated. Here the cycle is the chord's tones across `range_octaves`, closing
on the final octave, reordered by `pattern` and then ordered by `direction`.
One octave of a seventh chord is five notes, not four: `scales` closes on its
octave for the same reason, and an arpeggio that stops on the seventh reads as
unfinished rather than as economical.

## Which notes, then where: two passes, in that order

The pitch content comes from `theory.chord_pitches` and nothing here
reimplements chord maths. The family's own work is the second half of §6's
promise — **it decides where each note is played**, not only which note it is.

Positions are assigned to the *ascending chord tones*, once, before `pattern`
and `direction` are applied, exactly as `scales` assigns them to its degrees. A
pattern like `numeric_1353` plays most tones three times, and a chord whose
tones moved around under the hand between repetitions would be a different
exercise every time it came round.

## The axes, and what this module decided about them

**`inversion` is a registry identifier, not a rotation count.** §7 writes the
column as root/first/second/third, `vocabulary` carries those four identifiers
and `config` samples the axis through the same `_registry` path as every other
identifier, so that is what arrives here. The bare integer
`theory.chord_pitches` takes is an implementation detail of `theory`, and
`INVERSIONS` is the one place the two meet: a value's *position* in it is the
rotation count. An inversion the chord cannot support — a triad's third — is
rejected by `theory` and the refusal is allowed through unwrapped, because its
message already names the quality and the range it accepted. Wrapping round to
root position instead would engrave the wrong chord convincingly (§13).

**`traversal` decides how the chord is spread over the strings.**
`positional` keeps the hand in one place, minimizing total fret travel across
the whole cycle and **raising when the chord will not fit under one hand**
(`_shared.boxed`, shared with `scales`; issue #57) — two octaves over four
strings puts the upper octave up the neck, which is a shift and not a position,
and a label a player cannot trust is worse than a draw §9 has to replace.
`across_strings` is
the arpeggio's own layout: each successive tone moves to the next string in
`string_set` **where the string set allows it**, which is the sweep-picked
shape a player actually uses. A tone the next string cannot reach — a fifth
that would need a negative fret there — stays where it is rather than forcing
the shape, and once the strings run out the remaining tones continue up the
top string of the set. Neither is a silent repair: both keep every note on a
string that can sound it, and a tone no string in the set can sound raises.
`single_string` needs exactly one string, and a wider set is a contradiction
between two axes rather than a hard specification.

**`pattern` shapes the sequence and `direction` then orders it**, the same way
round as in `scales`, so a descending figure is the retrograde of the ascending
one rather than a second, mirrored implementation of every figure. Each pattern
is a window of tone offsets slid along the chord: `numeric_1353` is
`(0, 1, 2, 1)`, so it emits 1-3-5-3, 3-5-7-5; `broken` is `(0, 2)`, which skips
a tone and comes back for it.

`sweep_ordered` is the three-tone window `(0, 1, 2)` — the arpeggio rolled up
in overlapping three-note sweeps, which is how sweep picking is drilled. The
other available reading, "order the notes so the picking hand never returns to
a string it has left", was rejected: on every layout this family produces the
strings already ascend with the pitch, so that reading would make
`sweep_ordered` an alias of `straight` — two values of one axis naming a single
exercise, which §9's coverage accounting could not tell apart.

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

`dim`, `dim7` and `aug` imply symmetric parents and therefore land in §10a's
tier 3, which prints no signature and spells by direction: C dim7 is written
`C D# F# A` rather than the functional `C Eb Gb Bbb`. That is a stated boundary
of the model rather than a defect here — a fully diminished seventh needs a
doubly diminished seventh above the root and no seven-note scale supplies one,
so there is no parent to point at. §10a records the whole argument.

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
    layout_hints,
    octaves,
    realizable,
    string_set,
    windowed,
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
_FAMILY = "arpeggios"

#: Spec §7's tempo range for this family, in beats per minute. The *family*
#: declares it and the selector never samples it (decision #20); configuration
#: overrides it per family through `[pool.arpeggios] tempo`.
#:
#: The demand here is comparable to `scales`, so the range is the same one.
#: The original 80-100 was reasoned from categories rather than from an
#: instrument and came out too slow to be useful — it is where the author warms
#: up, not where he practices. §7 carries that reasoning; the number is
#: declared here.
DEFAULT_TEMPO_RANGE = (80, 140)

#: The un-modified reading: one note per beat in common time. `rhythm.py` (§8)
#: is the cross-cutting modifier that re-times a Score into subdivisions and
#: other meters, so this family states the plainest possible rhythm and leaves
#: the subject to the one module that owns it.
DEFAULT_TIME_SIGNATURE = (4, 4)
NOTE_DURATION = Fraction(1, 4)

INSTRUCTION = "Name each chord tone as it sounds; keep the string crossings even."

#: §7's axis columns. Named here so a missing parameter can list what the
#: family expected rather than only what it did not find.
AXES = (
    "root",
    "quality",
    "inversion",
    "traversal",
    "string_set",
    "pattern",
    "range_octaves",
    "direction",
)

#: §7's `inversion` column, and the one place its identifiers meet the integer
#: rotation count `theory.chord_pitches` takes: a value's *position* here is
#: that count. `theory` decides whether the chord can support it — a triad has
#: no third inversion — so nothing is enumerated twice.
INVERSIONS: tuple[str, ...] = ("root", "first", "second", "third")

_POSITIONAL = "positional"
_ACROSS_STRINGS = "across_strings"
_SINGLE_STRING = "single_string"
_STRAIGHT = "straight"

#: The subset of §7's `traversal` column this family realizes. `vocabulary`
#: carries the union of every family's traversals in one axis, so the family
#: states which of them it can lay out — `three_note_per_string` and
#: `octave_per_string` belong to `scales`.
_TRAVERSALS = (_POSITIONAL, _ACROSS_STRINGS, _SINGLE_STRING)

#: Each pattern as the tone offsets of one window, slid one chord tone at a
#: time along the ascending chord. `straight` is the identity window.
#:
#: The widest window spans three tones and the shortest cycle this family can
#: produce is one octave of a triad, which is four notes, so no pattern can be
#: starved of tones to slide along.
_PATTERN_WINDOWS: dict[str, tuple[int, ...]] = {
    _STRAIGHT: (0,),
    "numeric_1353": (0, 1, 2, 1),
    "broken": (0, 2),
    "sweep_ordered": (0, 1, 2),
}

#: The axes a `positional` layout names when a tone is out of reach (§13).
_POSITIONAL_AXES = "root, quality, inversion, range_octaves and string_set"

_SEMITONES_PER_OCTAVE = len(theory.PITCH_CLASSES)


def _tones(root: int, quality: str, inversion: str, octave_count: int) -> list[int]:
    """The ascending chord tones across `octave_count`, closing on the octave.

    `theory` owns the chord and the inversion; this only stacks the result and
    appends the closing note, which is the same shape `theory.scale_pitches`
    gives the scales.
    """
    chord = theory.chord_pitches(root, quality, INVERSIONS.index(inversion))
    return [
        *(
            pitch + _SEMITONES_PER_OCTAVE * octave
            for octave in range(octave_count)
            for pitch in chord
        ),
        chord[0] + _SEMITONES_PER_OCTAVE * octave_count,
    ]


def _fret(profile: InstrumentProfile, pitch: int, string: int) -> int | None:
    """The fret sounding `pitch` on `string`, or None if that string cannot."""
    fret = pitch - profile.tuning[string]
    return fret if 0 <= fret <= profile.fret_count else None


def _demanded(profile: InstrumentProfile, pitch: int, string: int) -> int:
    """The fret sounding `pitch` on `string`, or an error naming what it needed."""
    fret = _fret(profile, pitch, string)
    if fret is None:
        msg = (
            f"{_FAMILY}: pitch {pitch} needs fret {pitch - profile.tuning[string]} on string "
            f"{string} of profile {profile.name!r}, which has frets 0 to {profile.fret_count}. "
            f"The cycle is never truncated to fit (§7), so this specification is unrealizable "
            f"rather than shorter"
        )
        raise ValueError(msg)
    return fret


def _across(
    profile: InstrumentProfile,
    pitches: Sequence[int],
    strings: tuple[int, ...],
) -> list[tuple[int, int]]:
    """One chord tone per string, where `string_set` allows (§7).

    The walk moves up one string per tone and holds where it cannot: a tone the
    next string would need a negative fret for waits a string, and once the set
    runs out the remaining tones continue up its top string. Both are ordinary
    outcomes of a chord that is wider than the string set, not repairs — every
    note still lands on a string that can sound it, and one that no string can
    sound raises rather than being moved somewhere it was not asked for.
    """
    index = 0
    places = [(strings[0], _demanded(profile, pitches[0], strings[0]))]
    for pitch in pitches[1:]:
        if index + 1 < len(strings) and _fret(profile, pitch, strings[index + 1]) is not None:
            index += 1
        places.append((strings[index], _demanded(profile, pitch, strings[index])))
    return places


def _places(
    profile: InstrumentProfile,
    pitches: Sequence[int],
    strings: tuple[int, ...],
    traversal: str,
) -> list[tuple[int, int]]:
    """Where each ascending chord tone is played, in chord order.

    `single_string` is the remaining case rather than a third test, for the
    same reason `apply_direction` leaves `up_down` to fall through: `realizable`
    has already rejected every traversal this family does not lay out.
    """
    if traversal == _POSITIONAL:
        return boxed(profile, pitches, strings, _FAMILY, _POSITIONAL_AXES)
    if traversal == _ACROSS_STRINGS:
        return _across(profile, pitches, strings)

    if len(strings) != 1:
        msg = (
            f"{_FAMILY}: traversal {traversal!r} plays the whole arpeggio on one string, but "
            f"string_set {list(strings)} names {len(strings)}. traversal and string_set "
            f"cannot both be satisfied; §9 resamples this rather than narrowing the set"
        )
        raise ValueError(msg)
    return [(strings[0], _demanded(profile, pitch, strings[0])) for pitch in pitches]


def _title(
    root: int, quality: str, inversion: str, traversal: str, pattern: str, direction: str
) -> str:
    """The plain-language name §12's cover page prints, built from the registry."""
    figure = vocabulary.display("direction", direction)
    if pattern != _STRAIGHT:
        figure = f"{figure} {vocabulary.display('pattern', pattern)}"

    chord = f"{theory.PITCH_CLASSES[root % _SEMITONES_PER_OCTAVE]} "
    chord += vocabulary.display("quality", quality)
    if inversion != INVERSIONS[0]:
        chord += f", {vocabulary.display('inversion', inversion)}"
    return f"{chord}, {vocabulary.display('traversal', traversal)}, {figure}"


def generate(profile: InstrumentProfile, params: Mapping[str, object]) -> tuple[Score, LayoutHints]:
    """Realize one arpeggio exercise on `profile`, with the §4.2 layout hints.

    Pure: the same profile and parameters always produce the same Score. Extra
    keys in `params` are carried into the Score untouched rather than rejected
    — §8's rhythm axes travel in the same dictionary — but every axis this
    family reads is required, so a misspelled one is a loud failure and never a
    silent default.

    The hints are the fitter's window onto what the voice alone does not carry:
    the natural cell is one turn of the `pattern` window, and an `up_down`
    exercise names the apex it turns around at so the fitter's apex levers know
    where to act. A one-directional exercise has no such seam.
    """
    read = Parameters(_FAMILY, AXES, params)
    root = read.integer("root")
    quality = read.identifier("quality")
    inversion = read.identifier("inversion")
    traversal = realizable(read, "traversal", _TRAVERSALS)
    pattern = realizable(read, "pattern", tuple(_PATTERN_WINDOWS))
    direction = read.identifier("direction")
    octave_count = octaves(read)
    strings = string_set(read, profile)

    pitches = _tones(root, quality, inversion, octave_count)
    places = _places(profile, pitches, strings, traversal)
    window = _PATTERN_WINDOWS[pattern]
    ascending = windowed(window, len(pitches))
    order = apply_direction(ascending, direction)

    voice: Voice = [
        Note(
            pitch=pitches[tone],
            string=places[tone][0],
            fret=places[tone][1],
            duration=NOTE_DURATION,
            finger=None,
            accent=False,
        )
        for tone in order
    ]

    score = Score(
        title=_title(root, quality, inversion, traversal, pattern, direction),
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
    return score, _hints(window, ascending, direction)


def _hints(window: tuple[int, ...], ascending: Sequence[int], direction: str) -> LayoutHints:
    """The §4.2 layout hints for a realized cycle.

    The cell is one turn of the `pattern` window. `up_down` turns around at the
    top of the ascending pass — its last note, played once — so the seam is that
    note's index and the apex levers become legal; a `up` or `down` exercise has
    no turnaround, so it offers only the trailing add/drop.
    """
    seam = len(ascending) - 1 if direction == "up_down" else None
    levers: tuple[Lever, ...] = (Lever.ADD_ONE, Lever.DROP_ONE)
    if seam is not None:
        levers = (*levers, Lever.APEX_REPEAT, Lever.APEX_OMIT)
    return layout_hints(cell=len(window), seam=seam, levers=levers)
