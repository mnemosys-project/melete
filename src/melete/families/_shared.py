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
written once. `realizable`, `octaves` and `string_set` are the three axis
readings that need more than a type: the subset of a shared axis one family can
lay out, §7's enumerated octave counts, and a string set validated against the
active profile.

**Assembling `LayoutHints`.** Every family returns §4.2's hints alongside its
`Score`, and the record is one shape for all four. `layout_hints` names it once
so no family restates the field order; the values it carries — the natural cell,
the turnaround seam, the legal levers — stay the family's own to decide.

**Ordering by `direction`.** §7's `direction` axis is shared, so its realization
is too. `apply_direction` is generic over the element type on purpose: `scales`
orders degree indices and `chromatic` orders string indices, and a helper that
knew about either would be a family in disguise. `there_and_back` is the
turnaround underneath it, named separately because `chromatic` needs that half
without the rest (see `chromatic._strings`) and because the off-by-one it
encodes — the turnaround element is played once, not twice — is the single
easiest thing here to get wrong.

**The `positional` layout.** B6a's brief proposed
`assign_positions(profile, pitches, string_set, traversal)` and this module
declined it while `scales` was the only caller: `chromatic` runs in the opposite
direction, deriving the fret from a finger and reading the pitch back out of it,
so one signature spanning both would have carried a dead half for each. Task B7
supplied the genuine second caller. `boxed` is the half the two share exactly —
a sequence of pitches, a string set, the base fret minimizing total travel, and
the refusal when the result is wider than a hand (issue #57) — and the
traversals that lay runs of notes along the strings stay in the families,
because what a run *is* differs between a scale and a chord.

## What is deliberately not here

**The fretboard-bounds errors of the other traversals.** They read alike, but
each names the axes that could not be satisfied *on that family's own terms*,
which is the whole of what §13 asks a raise to do. Generalizing them would cost
exactly the specificity they exist to provide — which is why `boxed`, the one
that did move, takes the axis list it should name rather than inventing one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from melete import vocabulary
from melete.instrument import hand_span, positions
from melete.layout import LayoutHints

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from melete.instrument import InstrumentProfile
    from melete.layout import Lever

#: §7's `range_octaves` column, which the spec enumerates rather than leaves
#: open. Shared because the column is one column, not one per family.
RANGE_OCTAVES = (1, 2, 3)


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


def realizable(read: Parameters, axis: str, accepted: tuple[str, ...]) -> str:
    """One identifier from the subset of a shared axis a family realizes.

    `vocabulary` carries the union of every family's values for `traversal` and
    `pattern`, because the selector samples one axis. A value belonging to
    another family is rejected here by name rather than dispatched into a
    branch that does not exist.
    """
    value = read.identifier(axis)
    if value not in accepted:
        realized = list(accepted)
        family = read.family
        msg = f"{family}: {axis} {value!r} belongs to another family; {family} realizes {realized}"
        raise ValueError(msg)
    return value


def octaves(read: Parameters) -> int:
    """The `range_octaves` axis, which §7 enumerates rather than leaves open."""
    value = read.integer("range_octaves")
    if value not in RANGE_OCTAVES:
        msg = f"{read.family}: range_octaves must be one of {list(RANGE_OCTAVES)}, got {value}"
        raise ValueError(msg)
    return value


def string_set(read: Parameters, profile: InstrumentProfile) -> tuple[int, ...]:
    """The strings the exercise is laid across, low to high.

    Strictly ascending and validated rather than repaired, for the reason
    `instrument` refuses to re-sort a tuning: re-ordering or de-duplicating the
    set would engrave a different string set from the one the selector drew,
    and §9's coverage accounting would have no way to see the substitution.
    """
    family = read.family
    value = read.value("string_set")
    if not isinstance(value, list | tuple) or not value:
        msg = f"{family}: string_set must be a non-empty sequence of string indices, got {value!r}"
        raise ValueError(msg)

    strings = tuple(value)
    if any(isinstance(item, bool) or not isinstance(item, int) for item in strings):
        msg = f"{family}: string_set must hold integer string indices, got {value!r}"
        raise ValueError(msg)

    if list(strings) != sorted(set(strings)):
        msg = (
            f"{family}: string_set {list(strings)} must be strictly ascending with no "
            f"repeats; index 0 is the lowest string, and re-sorting it here would "
            f"engrave a different string set from the one that was specified"
        )
        raise ValueError(msg)

    last = len(profile.tuning) - 1
    if strings[0] < 0 or strings[-1] > last:
        msg = (
            f"{family}: string_set {list(strings)} is off profile {profile.name!r}, "
            f"which has strings 0 to {last}"
        )
        raise ValueError(msg)
    return strings


def windowed(window: Sequence[int], count: int) -> list[int]:
    """Indices in playing order: one window of offsets slid along `count` items.

    §7 gives `scales` and `arpeggios` a `pattern` column each, and both columns
    are the same construction — a window of offsets advanced one item at a time.
    `straight` is the identity window `(0,)`, `scales`' thirds is `(0, 2)` and
    the arpeggio's 1-3-5-3 is `(0, 1, 2, 1)`. The families keep their own
    tables, because which figures they name is a musical judgement; the slide,
    and its off-by-one — the last window must still fit, so there are
    `count - max(window)` of them — is written once.
    """
    return [start + offset for start in range(count - max(window)) for offset in window]


def _reachable(
    profile: InstrumentProfile,
    pitch: int,
    strings: tuple[int, ...],
    family: str,
    axes: str,
) -> list[tuple[int, int]]:
    """Every place within `strings` that sounds `pitch`, lowest string first."""
    places = [place for place in positions(profile, pitch) if place[0] in strings]
    if not places:
        msg = (
            f"{family}: pitch {pitch} is unreachable on strings {list(strings)} of profile "
            f"{profile.name!r}, which has frets 0 to {profile.fret_count}: {axes} cannot "
            f"all be satisfied on this instrument"
        )
        raise ValueError(msg)
    return places


def boxed(
    profile: InstrumentProfile,
    pitches: Sequence[int],
    strings: tuple[int, ...],
    family: str,
    axes: str,
) -> list[tuple[int, int]]:
    """The `positional` layout, or a refusal: this content is not a position.

    For each candidate base fret, every pitch takes the position within
    `strings` nearest to it; the base fret with the lowest total distance wins,
    ties going to the lower fret, and a pitch with two equally near positions
    goes to the lower string. Deterministic all the way down, which is what
    reproducibility from a session log needs.

    **The result is then checked against the profile's `position_span`, and a
    layout wider than one hand raises** (issue #57). The minimization has no
    floor of its own — two octaves of a pentatonic across three strings cannot
    fit under a hand on any tuning, so the argmin returns the least bad answer
    — and the family used to report that as success. It engraved a fourteen-
    fret reach under a cover page reading "positional", which is worse than an
    unplayable exercise: it is a mislabelled one, and the label is the part a
    student trusts. Refusing turns a silent mislabelling into an
    over-constrained specification, which §9's validity gate already knows how
    to resample.

    The check costs nothing in coverage of the layouts that do fit: measured
    over ~19,400 positional draws from §10's example pool, the travel-minimizing
    base is within one position **exactly when** some base fret can hold every
    pitch within one, so nothing playable is refused by the choice of objective.

    `axes` is the family's own list of the axes that could not all be satisfied
    (§13). It is a parameter rather than a fixed sentence because naming *the
    caller's* axes is the whole of what the error is for.
    """
    choices = [_reachable(profile, pitch, strings, family, axes) for pitch in pitches]

    def travel(base: int) -> int:
        return sum(min(abs(fret - base) for _string, fret in places) for places in choices)

    # `min` keeps the first of equal keys, so ties go to the lower fret.
    base = min(range(profile.fret_count + 1), key=travel)
    places = [min(places, key=lambda place: (abs(place[1] - base), place[0])) for places in choices]

    span = hand_span(fret for _string, fret in places)
    if span > profile.position_span:
        msg = (
            f"{family}: a positional traversal must fit one position, and the closest layout "
            f"spans {span} frets against a position of {profile.position_span} on profile "
            f"{profile.name!r}: {axes} cannot all be satisfied under one hand. §9 resamples "
            f"this rather than engraving a shift under a 'positional' label"
        )
        raise ValueError(msg)
    return places


def box(
    profile: InstrumentProfile,
    pitches: Sequence[int],
    strings: tuple[int, ...],
    anchors: tuple[int, ...],
    family: str,
    axes: str,
) -> list[tuple[int, int]]:
    """Place `pitches` under one hand anchored at `anchors[0]` (spec §4).

    Each pitch takes the position within `strings` nearest the anchor base fret,
    ties to the lower fret then the lower string. The result must fit one
    `position_span`, or this raises — the anchor is pinned, so unlike the
    superseded `boxed` it never drifts off the root to minimise travel. Two
    anchors are the #67 two-hand seam and are not realized here.
    """
    if len(anchors) != 1:
        msg = (
            f"box: {len(anchors)} anchors is the two-hand seam owned by #67; "
            f"this epic lays out one hand"
        )
        raise NotImplementedError(msg)
    base = anchors[0]
    choices = [_reachable(profile, pitch, strings, family, axes) for pitch in pitches]
    places = [min(c, key=lambda p: (abs(p[1] - base), p[0])) for c in choices]
    span = hand_span(fret for _string, fret in places)
    if span > profile.position_span:
        msg = (
            f"{family}: the layout anchored at fret {base} spans {span} frets against a "
            f"position of {profile.position_span} on profile {profile.name!r}: {axes} cannot "
            f"all be satisfied under one hand. §9 resamples this rather than engraving a shift"
        )
        raise ValueError(msg)
    return places


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


def directed_by_cell[T](order: Sequence[T], direction: str, cell: int) -> list[T]:
    """§7's `direction`, with the `up_down` turnaround falling on a *cell* boundary.

    `apply_direction`'s `up_down` turns around at the note level: `there_and_back`
    over a flat order of `cell`-note groups replays every note but the apex,
    leaving `2L - 1` notes ≡ `cell - 1 (mod cell)`. For `cell > 1` that is a
    half-filled beat no meter divides — the §132 defect that kept a `thirds`
    up-and-down from ever tiling. Turning around a whole cell early instead — the
    ascent, then the retrograde of the ascent *minus its apex cell* — keeps the
    count a whole number of cells (`2L - cell`, i.e. `2 x 13 - 1 = 25` cells for
    26-note thirds) so the fitter always has whole beats to lay out.

    `up` and `down` are unchanged from `apply_direction`, deliberately: they never
    turn around, so a one-way pass is already `L` notes — whole cells — and needs
    no adjustment. `down` therefore stays the *note-level* retrograde that
    `scales` and `arpeggios` define a descending figure to be (descending thirds
    are `15-13, 14-12, …`, each pair high note first), not a cell-order reversal —
    that reversal is `intervals`' own reading of `direction`, and the two families
    differ on purpose (see `intervals`).

    The apex cell is played once in the base cycle; the fitter's `APEX_REPEAT` /
    `APEX_OMIT` levers repeat or omit that one cell to reach an even bar count. For
    `cell == 1` this reduces exactly to `apply_direction`. `order` must be a whole
    number of cells long — the `windowed` callers always are, a window slid one
    step at a time emitting its full width every step.
    """
    if direction == "up":
        return list(order)
    if direction == "down":
        return list(reversed(order))
    # `up_down`: ascend, then retrograde the ascent without its trailing apex
    # cell, so the apex plays once and the note count stays a whole cell count.
    return [*order, *reversed(order[: len(order) - cell])]


def layout_hints(cell: int, seam: int | None, levers: tuple[Lever, ...]) -> LayoutHints:
    """Assemble a family's LayoutHints (spec §4.2).

    Every family emits the same record — a natural group size, an optional
    turnaround seam and the note-count levers legal here — so its construction is
    written once, the same way `windowed` and `apply_direction` are. The family
    still owns the three values, because what a cell is and where a seam falls is
    a musical judgement; this only names the shape they travel in.
    """
    return LayoutHints(cell=cell, seam=seam, levers=levers)
