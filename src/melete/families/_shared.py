"""What every family would otherwise write identically (spec §7).

This is not a family. Nothing here is `generate(profile, params) -> Score` and
nothing here decides what an exercise *is* — that judgement stays in the family
that makes it. This module holds only the parts `chromatic` and `scales` had
already written twice by the time `arpeggios` and `intervals` (tasks B7 and B8)
were due to write them a third and a fourth time.

## What is here

**Reading parameters.** §13 gives every family the same contract for a bad
parameter: name the family, name the axis, and say what would have been
accepted. Only the family's name and its own axis tuple differ between the two
implementations of that contract, so `Parameters` carries both and the three
readings — a raw value, a registry identifier, a range-like integer — are
written once.

**Ordering by `direction`.** §7's `direction` axis is shared, so its realization
is too. `apply_direction` is generic over the element type on purpose: `scales`
orders degree indices and `chromatic` orders string indices, and a helper that
knew about either would be a family in disguise. `there_and_back` is the
turnaround underneath it, named separately because `chromatic` needs that half
without the rest (see `chromatic._strings`) and because the off-by-one it
encodes — the turnaround element is played once, not twice — is the single
easiest thing here to get wrong.

## What is deliberately not here

**Position assignment.** B6a's brief proposed
`assign_positions(profile, pitches, string_set, traversal)`. The two callers run
in opposite directions: `scales` holds a pitch sequence and asks where to play
it, while `chromatic` holds a finger and a shift, derives the fret from them and
reads the pitch back out of the fret. One signature spanning both would carry a
dead half for each caller. It waits for `arpeggios`, which is a genuine second
caller of the `scales` shape.

**The fretboard-bounds errors.** They read alike, but each names the axes that
could not be satisfied *on that family's own terms*, which is the whole of what
§13 asks a raise to do. Generalizing them would cost exactly the specificity
they exist to provide.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from melete import vocabulary

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


@dataclass(frozen=True)
class Parameters:
    """One family's reading of the parameter mapping it was called with.

    `family` and `axes` are what make an error message §13-compliant: the
    family names itself so a stack of them can be told apart, and it lists the
    axes it reads so a caller who misspelled one can see what was expected
    rather than only what was not found.

    Extra keys are never rejected — §8's rhythm axes travel in the same
    dictionary — so this reads the mapping and never audits it.
    """

    #: The family's identifier in `vocabulary.AXES["family"]`.
    family: str
    #: Every axis the family reads, in the order §7's table lists them.
    axes: tuple[str, ...]
    #: The specification the family was handed.
    values: Mapping[str, object]

    def value(self, axis: str) -> object:
        """One parameter, or an error naming the axis and the full set (§13)."""
        if axis not in self.values:
            msg = (
                f"{self.family}: parameter {axis!r} is required; "
                f"the family's axes are {list(self.axes)}"
            )
            raise ValueError(msg)
        return self.values[axis]

    def identifier(self, axis: str) -> str:
        """One registry identifier, checked against `vocabulary` and nothing else.

        Whether the family can *realize* the identifier is a second question and
        a different error: `vocabulary` carries the union of every family's
        values for a shared axis.
        """
        value = self.value(axis)
        if not isinstance(value, str) or value not in vocabulary.AXES[axis]:
            msg = f"{self.family}: unknown {axis} {value!r}; accepted: {vocabulary.accepted(axis)}"
            raise ValueError(msg)
        return value

    def integer(self, axis: str) -> int:
        """One range-like axis. `bool` is rejected: `True` is not fret 1."""
        value = self.value(axis)
        if isinstance(value, bool) or not isinstance(value, int):
            msg = f"{self.family}: {axis} must be an integer, got {value!r}"
            raise ValueError(msg)
        return value


def there_and_back[T](items: Sequence[T]) -> list[T]:
    """`items` forward and then back, without replaying the turnaround.

    The last element is the turnaround and is played once. Replaying it would
    sound the same note — or, in `chromatic`, the same four notes — twice in a
    row, which is a stumble rather than a figure. A single element is therefore
    a single pass: there is nothing to return along.
    """
    return [*items, *items[-2::-1]]


def apply_direction[T](items: Sequence[T], direction: str) -> list[T]:
    """`items` ordered by §7's `direction` axis.

    Generic over the element type because the axis is: a family decides *what*
    it orders — degree indices, string indices, chord tones — and `direction`
    only says in which order. The returned list is always a new one, so a caller
    can hand in the sequence it is still holding.

    `direction` is a registry identifier and is expected to have been validated
    against `vocabulary` already; `up_down` is the remaining case rather than a
    third test, for the same reason no family re-validates it.
    """
    if direction == "up":
        return list(items)
    if direction == "down":
        return list(reversed(items))
    return there_and_back(items)
