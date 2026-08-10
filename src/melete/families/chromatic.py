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
from melete.instrument import pitch_at
from melete.score import FINGERS, Note, Score

if TYPE_CHECKING:
    from collections.abc import Mapping

    from melete.instrument import InstrumentProfile
    from melete.score import Voice

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


def _parameter(params: Mapping[str, object], axis: str) -> object:
    """One parameter, or an error naming the axis and the full set (§13)."""
    if axis not in params:
        msg = f"chromatic: parameter {axis!r} is required; the family's axes are {list(AXES)}"
        raise ValueError(msg)
    return params[axis]


def _identifier(params: Mapping[str, object], axis: str) -> str:
    """One registry identifier, checked against `vocabulary` and nothing else."""
    value = _parameter(params, axis)
    if not isinstance(value, str) or value not in vocabulary.AXES[axis]:
        msg = f"chromatic: unknown {axis} {value!r}; accepted: {vocabulary.accepted(axis)}"
        raise ValueError(msg)
    return value


def _integer(params: Mapping[str, object], axis: str) -> int:
    """One range-like axis. `bool` is rejected: `True` is not fret 1."""
    value = _parameter(params, axis)
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"chromatic: {axis} must be an integer, got {value!r}"
        raise ValueError(msg)
    return value


def _permutation(params: Mapping[str, object]) -> tuple[int, ...]:
    """One ordering of the four fretting fingers."""
    value = _parameter(params, "permutation")
    if not isinstance(value, list | tuple) or sorted(value) != list(FINGERS):
        msg = (
            f"chromatic: permutation {value!r} is not an ordering of the fretting "
            f"fingers {list(FINGERS)}; the permutation is the exercise, so a partial "
            f"or repeated ordering is a different exercise rather than a shorter one"
        )
        raise ValueError(msg)
    return tuple(value)


def _strings(direction: str, traversal: str, start_string: int, span: int) -> list[int]:
    """The string each permutation cycle is played on, in playing order."""
    if span < 1:
        msg = f"chromatic: span must cover at least one string, got {span}"
        raise ValueError(msg)

    if traversal == _SINGLE_STRING and span != 1:
        msg = (
            f"chromatic: string_traversal {traversal!r} covers one string, so span must "
            f"be 1, got {span}. Ignoring the span would engrave a narrower exercise than "
            f"the one specified and replaying the string would repeat the same four notes"
        )
        raise ValueError(msg)

    step = _STRING_STEP[traversal]
    ascending = [start_string + cycle * step for cycle in range(span)]
    if direction == "up":
        return ascending
    if direction == "down":
        return [start_string - cycle * step for cycle in range(span)]
    # up_down: back down without replaying the turnaround string.
    return ascending + ascending[-2::-1]


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


def generate(profile: InstrumentProfile, params: Mapping[str, object]) -> Score:
    """Realize one chromatic permutation exercise on `profile`.

    Pure: the same profile and parameters always produce the same Score. Extra
    keys in `params` are carried into the Score untouched rather than rejected
    — §8's rhythm axes travel in the same dictionary — but every axis this
    family reads is required, so a misspelled one is a loud failure and never a
    silent default.
    """
    permutation = _permutation(params)
    start_string = _integer(params, "start_string")
    start_fret = _integer(params, "start_fret")
    span = _integer(params, "span")
    direction = _identifier(params, "direction")
    traversal = _identifier(params, "string_traversal")
    shift = _identifier(params, "shift")

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
            f"chromatic: strings {low_string} to {high_string} are off profile "
            f"{profile.name!r}, which has strings 0 to {last_string}: "
            f"start_string={start_string} with span={span}, string_traversal={traversal!r} "
            f"and direction={direction!r} cannot be realized on this instrument"
        )
        raise ValueError(msg)

    frets = [fret for _string, fret, _finger in positions]
    low_fret, high_fret = min(frets), max(frets)
    if low_fret < 0 or high_fret > profile.fret_count:
        msg = (
            f"chromatic: frets {low_fret} to {high_fret} are off profile {profile.name!r}, "
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

    return Score(
        title=_title(permutation, traversal, direction, shift),
        instruction=INSTRUCTION,
        instrument=profile,
        time_signature=DEFAULT_TIME_SIGNATURE,
        tempo_range=DEFAULT_TEMPO_RANGE,
        voice=voice,
        params=dict(params),
    )
