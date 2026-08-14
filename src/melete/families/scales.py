"""`scales` — modes and scale patterns (spec §7, MNEMOSYS H1, H2, H3, H5).

`generate` is a pure function: no I/O, no randomness, no clock. The selector
(§9) chooses the parameters and this module realizes them, which is what makes
a sheet reproducible from its session log and this family testable without any
of the machinery around it. It therefore imports neither `selection` nor
`config`.

The largest family — roughly 24,000 variants before rhythm is applied.

## What one exercise is: the outer-to-outer journey (epic #72, spec §5)

One exercise is **one computed round trip** across the instrument. The root is
anchored on the lowest string (the selector realizes that anchor, §5) and the
journey climbs **outward, string by string, to the opposite outer string** under
the chosen fingering style — then turns around and returns as the exact
retrograde of the ascent. Direction is never sampled: every scale is drilled up
and back (spec §5, decision 1).

**Extent is governed by reaching the opposite outer string, and the octave count
is emergent** — never a sampled target (spec §5, decision 11). A six-string
already spans every string within one boxed hand position; a
three-note-per-string climb walks string by string to the top. What that yields
in octaves is whatever the instrument gives (≈2.5 on a six-string), and the
family no longer carries the one-octave `positional` fallback the old
two-octave target needed — there is no fixed target to fall short of.

## Which notes, then where: two passes, in that order

The pitch content comes from `theory.scale_pitches` — a long ascending supply,
enough octaves to reach the top string on any profile — and nothing here
reimplements it. The family's own work is the second half of §6's promise: it
decides **where** each note is played. Placement is delegated to the shared
`journey` builder, which returns the pitches it actually used and their
`(string, fret)` places; the family picks the fingering style and its pitch
content and leaves the geometry to `journey`.

Positions are assigned to the *degrees of the ascending journey*, once, before
the `pattern` window and the up-and-down retrograde are applied. That ordering
is the design, not an implementation convenience: a pattern like `groups_of_3`
plays most degrees three times, and a scale whose notes moved around under the
hand between repetitions would be a different exercise every time it came round.

## The axes this family reads (spec §7, §8)

Four axes: `root`, `scale_type`, `traversal` (the fingering style), and
`pattern`. The three geometry axes the old model sampled — `direction`,
`string_set`, `range_octaves` — are gone (spec §8): direction is always
up-and-down, string coverage is the whole instrument, and octave count is
emergent. Those keys may still arrive in `params` while the config migration
(#72 Task E2) lands; the family simply no longer reads them, and extra keys are
carried into the Score untouched, per the existing contract.

**`traversal` is the fingering style**, and it is a sampled *content* choice —
which mapping to drill — whose geometry is then computed (spec §6):

- **`positional`** — the box climbs the neck by string, every note sitting under
  one hand within `position_span`. `journey.boxed_span` grows the box pitch by
  pitch from the low anchor while it still fits one position.
- **`three_note_per_string`** — three consecutive scale degrees on each string,
  climbing outward to the top string by construction.

The two single-string / one-octave-per-string readings the old model carried are
deferred to the single/two-string modes (spec §13) and are not realized here.

**`pattern` shapes the sequence and the journey then plays it up and back.**
Every pattern is a window of degree offsets slid one degree at a time along the
full ascent (spec §7) — `thirds` is `(0, 2)`, so it emits 1-3, 2-4, 3-5;
`groups_of_3` is `(0, 1, 2)`, so it emits 1-2-3, 2-3-4, 3-4-5. The window reaches
across the whole neck because the journey supplies the full outer-to-outer ascent
it slides along (the fix for defect 3). The retrograde of the patterned ascent
*is* the descent — `journey.updown` reuses `directed_by_cell`, turning around a
whole cell at a time so the note count stays a whole number of beats.

**`finger` is left unspecified.** §6 makes fingering first class because in
*chromatic* permutation work the fingering is the exercise. Here the position
is, and prescribing a finger would engrave a fingering the caller never asked
for. The field is `None`, which §6 defines as unspecified rather than absent.

## Running off the neck

A specification that cannot be realized on the profile raises, naming the axes
that could not be satisfied (spec §10). It is never clamped or truncated to fit
— the journey is never shortened to make it playable — and §9's validity gate
resamples the draw.
"""

from __future__ import annotations

from fractions import Fraction
from typing import TYPE_CHECKING

from melete import theory, vocabulary
from melete.families._shared import Parameters, layout_hints, realizable, windowed
from melete.families.journey import boxed_span, per_string, updown
from melete.layout import Lever
from melete.score import Note, Score

if TYPE_CHECKING:
    from collections.abc import Mapping

    from melete.instrument import InstrumentProfile
    from melete.layout import LayoutHints
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

#: §7's axis columns, after epic #72 retired the three geometry axes
#: (`direction`, `string_set`, `range_octaves`). Named here so a missing
#: parameter can list what the family expected rather than only what it did not
#: find.
AXES = (
    "root",
    "scale_type",
    "traversal",
    "pattern",
)

_POSITIONAL = "positional"
_THREE_NOTE_PER_STRING = "three_note_per_string"
_STRAIGHT = "straight"

#: The subset of §7's `traversal` column this family realizes as a fingering
#: style (spec §6). `vocabulary` carries the union of every family's traversals
#: in one axis, so the family states which of them it can lay out — the
#: single-string and one-octave-per-string readings are deferred (spec §13), and
#: `across_strings` belongs to `arpeggios`.
_TRAVERSALS = (_POSITIONAL, _THREE_NOTE_PER_STRING)

#: Each pattern as the degree offsets of one window, slid one degree at a time
#: along the full ascent. `straight` is the identity window; §7's "numeric
#: permutations (1-2-3-5)" is `(0, 1, 2, 4)`.
#:
#: The widest window spans five degrees, and the outer-to-outer journey supplies
#: far more than that on any profile, so no pattern can be starved of degrees to
#: slide along.
_PATTERN_WINDOWS: dict[str, tuple[int, ...]] = {
    _STRAIGHT: (0,),
    "thirds": (0, 2),
    "fourths": (0, 3),
    "groups_of_3": (0, 1, 2),
    "groups_of_4": (0, 1, 2, 3),
    "numeric_1235": (0, 1, 2, 4),
}

#: The axes the `journey` builder names when a note falls off the neck (§13).
#: The builder raises with this rather than a sentence of its own, because
#: naming *this family's* axes is the whole of what the error is for.
_JOURNEY_AXES = "root and scale_type"

#: How many degrees `three_note_per_string` puts on each string. Named because
#: the identifier and the number must not be able to disagree.
_NOTES_PER_STRING = 3


def _title(root: int, scale_type: str, traversal: str, pattern: str) -> str:
    """The plain-language name §12's cover page prints, built from the registry.

    Direction is no longer named: every scale is drilled up and down (spec §5),
    so stating it would print a word that is always the same.
    """
    name = (
        f"{theory.PITCH_CLASSES[root % len(theory.PITCH_CLASSES)]} "
        f"{vocabulary.display('scale_type', scale_type)}, "
        f"{vocabulary.display('traversal', traversal)}"
    )
    if pattern != _STRAIGHT:
        name = f"{name}, {vocabulary.display('pattern', pattern)}"
    return name


def generate(profile: InstrumentProfile, params: Mapping[str, object]) -> tuple[Score, LayoutHints]:
    """Realize one scale exercise on `profile`, with the §4.2 layout hints.

    Pure: the same profile and parameters always produce the same Score. Extra
    keys in `params` are carried into the Score untouched rather than rejected —
    §8's rhythm axes travel in the same dictionary, and so do the retired
    geometry axes until the config migration (#72 Task E2) lands — but every axis
    this family reads is required.

    The journey is computed, not sampled: a long ascending pitch supply is placed
    outer-string to opposite-outer-string under the chosen fingering style
    (`journey.boxed_span` for `positional`, `journey.per_string` for
    `three_note_per_string`), the `pattern` window slides along the notes the
    journey actually used, and `journey.updown` plays that ascent and its exact
    retrograde. Extent and octave count are emergent from reaching the top string
    (spec §5); there is no octave target and no one-octave fallback.

    The hints carry §4.2's layout accounting: one turn of the `pattern` window is
    the natural cell, and the up-and-down voice declares its apex — the `seam`
    where the ascending half turns around — with the apex-repeat/omit levers the
    fitter uses to reach a whole-bar count.
    """
    read = Parameters(_FAMILY, AXES, params)
    root = read.integer("root")
    scale_type = read.identifier("scale_type")
    traversal = realizable(read, "traversal", _TRAVERSALS)
    pattern = realizable(read, "pattern", tuple(_PATTERN_WINDOWS))

    # Enough octaves that the ascent reaches the opposite outer string on any
    # profile: one per string is always more than a hand or the string count
    # needs, and `journey` uses only the leading run it can actually place.
    supply = theory.scale_pitches(root, scale_type, len(profile.tuning) + 1)
    if traversal == _THREE_NOTE_PER_STRING:
        pitches, places = per_string(profile, supply, _NOTES_PER_STRING, _FAMILY, _JOURNEY_AXES)
    else:  # positional
        pitches, places = boxed_span(profile, supply, _FAMILY, _JOURNEY_AXES)

    window = _PATTERN_WINDOWS[pattern]
    ascending = windowed(window, len(pitches))
    order = updown(ascending, len(window))

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

    score = Score(
        title=_title(root, scale_type, traversal, pattern),
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
    # §4.2 hints: the pattern window is the cell; the up-and-down voice is
    # `directed_by_cell` over the ascending order, turning around at a cell
    # boundary, so its apex — the last ascending note — is the seam, and the
    # fitter reaches a whole bar by repeating or omitting that apex cell.
    hints = layout_hints(
        cell=len(window),
        seam=len(ascending) - 1,
        levers=(Lever.APEX_REPEAT, Lever.APEX_OMIT),
    )
    return score, hints
