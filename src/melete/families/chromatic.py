"""`chromatic` — finger-independence permutations (spec §7, MNEMOSYS T1).

`generate` is a pure function: no I/O, no randomness, no clock. The selector
(§9) chooses the parameters and this module realizes them, which is what makes
a sheet reproducible from its session log and this family testable without any
of the machinery around it. It therefore imports neither `selection` nor
`config`.

## What one exercise is

One exercise is **one complete cycle of the pattern** (§7) and is never
truncated. Here the cycle is one pass over the strings the specification
covers, playing the permutation once on each: `span` strings x four fingers.
With `span = 4` that is sixteen notes.

## The axes, and what this module decided about them

Three of §7's seven axes admit more than one reading. Each is settled here
rather than left to the caller, and the choices are stated because they are
choices:

**`direction` orders the strings, and never the fingers.** Playing the
retrograde of the permutation on the way down is what a bassist does by habit,
but it would make `(1, 2, 3, 4)` descending the same note sequence as
`(4, 3, 2, 1)` ascending reversed — two specifications, one exercise, and an
alias the coverage-aware selector of §9 would have no way to see. The
permutation *is* the exercise (§6 on `finger` being first class), so it is
played as written and `direction` decides only the order the strings are
visited. `up_down` ascends and returns without replaying the turnaround
string, which would otherwise sound the same four notes twice in a row.

**`shift` advances once per permutation cycle**, not once per pass. A cycle of
the permutation is the four notes of one group, so `fret_per_cycle` starts
each successive group one fret above the last and `position_per_cycle` starts
it one hand position — four frets, one per finger — above. Both are real
exercises: the first is the diagonal walk up the neck, the second is a
position shift drilled across the strings. Read the other way ("once per
pass"), a shifted specification would have to repeat the pass until it
returned to its starting pitch class — twelve passes, 192 notes at `span = 4`
— and would be rejected by §7's `max_notes` bound on essentially every draw.

**`single_string` covers one string, so it requires `span == 1`.** The
combination `single_string` with `span = 3` is a contradiction between two
axes rather than a hard specification, and §13 forbids resolving it quietly:
ignoring the span or repeating the same four notes three times would both
engrave something the caller did not ask for.

## Running off the neck

A specification that cannot be realized on the profile raises, naming the axes
that could not be satisfied. It is never clamped to fit — a clamped exercise
is a plausible-looking sheet that is not the one the selector drew, and §9's
validity gate exists precisely to resample this case.
"""

from __future__ import annotations

from fractions import Fraction
from typing import TYPE_CHECKING

from melete import vocabulary
from melete.families._shared import Parameters, layout_hints, there_and_back
from melete.instrument import pitch_at
from melete.layout import Lever
from melete.score import FINGERS, Note, Score

if TYPE_CHECKING:
    from collections.abc import Mapping

    from melete.instrument import InstrumentProfile
    from melete.layout import LayoutHints
    from melete.score import Voice

#: This family's identifier in `vocabulary.AXES["family"]`, and the prefix on
#: every error this module raises (§13). Written once so the two cannot drift.
_FAMILY = "chromatic"

#: Spec §7's tempo range for this family, in beats per minute. The *family*
#: declares it and the selector never samples it (decision #20); configuration
#: overrides it per family through `[pool.chromatic] tempo`.
DEFAULT_TEMPO_RANGE = (60, 120)

#: The un-modified reading: one note per beat in common time. `rhythm.py` (§8)
#: is the cross-cutting modifier that re-times a Score into subdivisions and
#: other meters, so this family states the plainest possible rhythm and leaves
#: the subject to the one module that owns it.
DEFAULT_TIME_SIGNATURE = (4, 4)
NOTE_DURATION = Fraction(1, 4)

#: A hand position is one finger per fret, so it is as many frets as there are
#: fretting fingers. Derived rather than written as 4 because it is the same
#: four, and the two must not be able to disagree.
POSITION_FRETS = len(FINGERS)

INSTRUCTION = "One finger per fret; keep each finger down until the string changes."

#: §7's axis columns. Named here so a missing parameter can list what the
#: family expected rather than only what it did not find.
AXES = (
    "permutation",
    "start_string",
    "start_fret",
    "direction",
    "string_traversal",
    "shift",
    "span",
)

_NO_SHIFT = "none"
_SINGLE_STRING = "single_string"

#: How far the pass moves along the strings for each permutation cycle.
_STRING_STEP = {"adjacent": 1, "skip_1": 2, _SINGLE_STRING: 0}

#: How far the fretting hand moves up the neck for each permutation cycle.
_FRET_STEP = {_NO_SHIFT: 0, "fret_per_cycle": 1, "position_per_cycle": POSITION_FRETS}


def _permutation(read: Parameters) -> tuple[int, ...]:
    """One ordering of the four fretting fingers."""
    value = read.value("permutation")
    if not isinstance(value, list | tuple) or sorted(value) != list(FINGERS):
        msg = (
            f"{_FAMILY}: permutation {value!r} is not an ordering of the fretting "
            f"fingers {list(FINGERS)}; the permutation is the exercise, so a partial "
            f"or repeated ordering is a different exercise rather than a shorter one"
        )
        raise ValueError(msg)
    return tuple(value)


def _strings(direction: str, traversal: str, start_string: int, span: int) -> list[int]:
    """The string each permutation cycle is played on, in playing order.

    `down` walks *downward from* `start_string` rather than reversing the ascent,
    which is why this family orders its own strings instead of handing the walk
    to `_shared.apply_direction`. The exercise begins on the string it was
    specified to begin on, so descending covers a different set of strings and is
    not the ascending pass played backwards. Only the turnaround is shared, and
    it is shared exactly — `scales` does the same thing to its degrees.
    """
    if span < 1:
        msg = f"{_FAMILY}: span must cover at least one string, got {span}"
        raise ValueError(msg)

    if traversal == _SINGLE_STRING and span != 1:
        msg = (
            f"{_FAMILY}: string_traversal {traversal!r} covers one string, so span must "
            f"be 1, got {span}. Ignoring the span would engrave a narrower exercise than "
            f"the one specified and replaying the string would repeat the same four notes"
        )
        raise ValueError(msg)

    step = -_STRING_STEP[traversal] if direction == "down" else _STRING_STEP[traversal]
    walk = [start_string + cycle * step for cycle in range(span)]
    return there_and_back(walk) if direction == "up_down" else walk


def _title(permutation: tuple[int, ...], traversal: str, direction: str, shift: str) -> str:
    """The plain-language name §12's cover page prints, built from the registry."""
    parts = [
        vocabulary.display("string_traversal", traversal),
        vocabulary.display("direction", direction),
    ]
    if shift != _NO_SHIFT:
        parts.append(vocabulary.display("shift", shift))
    fingers = "-".join(str(finger) for finger in permutation)
    return f"Chromatic {fingers}, {', '.join(parts)}"


def generate(profile: InstrumentProfile, params: Mapping[str, object]) -> tuple[Score, LayoutHints]:
    """Realize one chromatic permutation exercise on `profile`, with layout hints.

    Pure: the same profile and parameters always produce the same Score. Extra
    keys in `params` are carried into the Score untouched rather than rejected
    — §8's rhythm axes travel in the same dictionary — but every axis this
    family reads is required, so a misspelled one is a loud failure and never a
    silent default.

    The hints here are §4.2's minimum: the permutation is the natural cell — one
    group of `len(permutation)` notes to a beat — with the plain add/drop levers
    and no seam. The precise `up_down` apex accounting is #116's work; this task
    only widens the return.
    """
    read = Parameters(_FAMILY, AXES, params)
    permutation = _permutation(read)
    start_string = read.integer("start_string")
    start_fret = read.integer("start_fret")
    span = read.integer("span")
    direction = read.identifier("direction")
    traversal = read.identifier("string_traversal")
    shift = read.identifier("shift")

    fret_step = _FRET_STEP[shift]
    strings = _strings(direction, traversal, start_string, span)
    positions = [
        (string, start_fret + finger - 1 + cycle * fret_step, finger)
        for cycle, string in enumerate(strings)
        for finger in permutation
    ]

    last_string = len(profile.tuning) - 1
    low_string, high_string = min(strings), max(strings)
    if low_string < 0 or high_string > last_string:
        msg = (
            f"{_FAMILY}: strings {low_string} to {high_string} are off profile "
            f"{profile.name!r}, which has strings 0 to {last_string}: "
            f"start_string={start_string} with span={span}, string_traversal={traversal!r} "
            f"and direction={direction!r} cannot be realized on this instrument"
        )
        raise ValueError(msg)

    frets = [fret for _string, fret, _finger in positions]
    low_fret, high_fret = min(frets), max(frets)
    if low_fret < 0 or high_fret > profile.fret_count:
        msg = (
            f"{_FAMILY}: frets {low_fret} to {high_fret} are off profile {profile.name!r}, "
            f"which has frets 0 to {profile.fret_count}: start_fret={start_fret} with "
            f"permutation {permutation}, span={span} and shift={shift!r} cannot be "
            f"realized on this instrument"
        )
        raise ValueError(msg)

    voice: Voice = [
        Note(
            pitch=pitch_at(profile, string, fret),
            string=string,
            fret=fret,
            duration=NOTE_DURATION,
            finger=finger,
            accent=False,
        )
        for string, fret, finger in positions
    ]

    score = Score(
        title=_title(permutation, traversal, direction, shift),
        instruction=INSTRUCTION,
        instrument=profile,
        time_signature=DEFAULT_TIME_SIGNATURE,
        tempo_range=DEFAULT_TEMPO_RANGE,
        voice=voice,
        # Stated rather than left to the default: permutation work asserts no
        # tonal center at all, so this family is tier 3 by definition (§10a)
        # and spells by direction. `None` is the answer here, not the omission
        # it would be in a family that has a key to give.
        key=None,
        params=dict(params),
    )
    # Minimal but valid hints (§4.2): the permutation group is the cell, no seam,
    # plain add/drop levers. #116 refines the `up_down` apex accounting.
    hints = layout_hints(
        cell=len(permutation),
        seam=None,
        levers=(Lever.ADD_ONE, Lever.DROP_ONE),
    )
    return score, hints
