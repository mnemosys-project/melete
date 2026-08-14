"""The layout fitter (spec §4): derive a legible, whole-bar engraving.

Renderer-agnostic (must not import ``alphatab``). A family emits a ``Score`` plus
``LayoutHints``; ``fit`` turns the note count and hints into a ``LayoutPlan`` —
subdivision, time signature, bar count, any note-count levers applied, and a
human-readable trace — such that the voice tiles into whole measures.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from melete.score import Voice


class Lever(enum.Enum):
    """A musically-legal note-count adjustment the fitter may apply (spec §4.6)."""

    APEX_REPEAT = "apex_repeat"
    APEX_OMIT = "apex_omit"
    ADD_ONE = "add_one"
    DROP_ONE = "drop_one"


@dataclass(frozen=True)
class LayoutHints:
    """What the fitter needs from a family that the voice alone does not carry.

    ``cell`` is the natural group size g (spec §4.3): the run of notes that forms
    one beat. ``seam`` is the note index of the musical turnaround (an up/down
    pattern's apex), or ``None``. ``levers`` are the adjustments legal here.
    """

    cell: int
    seam: int | None
    levers: tuple[Lever, ...]

    def __post_init__(self) -> None:
        if self.cell < 1:
            msg = f"cell (group size g) must be at least 1, got {self.cell}"
            raise ValueError(msg)


#: Group size g -> the subdivision key (rhythm.SUBDIVISIONS) whose g notes fill
#: one quarter-note beat. Denominator therefore stays 4 (spec §4.1).
_SUBDIVISION_FOR_CELL: dict[int, str] = {
    1: "quarter",
    2: "eighth",
    3: "triplet_eighth",
    4: "sixteenth",
    5: "quintuplet",
    6: "sextuplet",
}

#: Sane beats-per-bar; a hard filter that outranks even-M (spec §4.5). 2/4 stays
#: in the whitelist so a genuinely one-beat exercise still tiles (span=1 chromatic
#: repeats its apex cell to 2/4 x 1), but it is demoted to a strict last resort in
#: the ranking below — never chosen when any 3/4, 4/4 or 6/4 fit exists (melete#174).
_SANE_BEATS: tuple[int, ...] = (2, 3, 4, 6)


@dataclass(frozen=True)
class LayoutPlan:
    """The fitter's decision for one exercise (spec §4).

    ``subdivision`` names the rhythm the notes are engraved as, ``time_signature``
    and ``bars`` tile them into whole measures, ``levers_applied`` records any
    note-count adjustment the fit required, and ``trace`` is the human-readable
    account of why this meter won.
    """

    subdivision: str
    time_signature: tuple[int, int]
    bars: int
    levers_applied: tuple[Lever, ...]
    trace: str


def _candidates(beats: int, seam_beat: int | None) -> list[tuple[int, int]]:
    """Every ``(b, M)`` with ``b*M == beats`` and ``b`` sane, best-first.

    Ranked (spec §4.5, melete#174): 2/4 last of all — a strict last resort that
    wins only when it is the sole candidate (a one-beat exercise); then even ``M``,
    then a bar boundary on the seam, then larger ``b`` (fuller bars, fewer lines).
    """
    pairs = [(b, beats // b) for b in _SANE_BEATS if beats % b == 0]

    def rank(pair: tuple[int, int]) -> tuple[int, int, int, int]:
        b, m = pair
        last_resort = 1 if b == 2 else 0
        even = 0 if m % 2 == 0 else 1
        on_seam = 0 if (seam_beat is not None and seam_beat % b == 0) else 1
        return (last_resort, even, on_seam, -b)

    return sorted(pairs, key=rank)


#: Effect of each lever on the note count. Every lever moves the count by a whole
#: cell — one beat — so the sign here is all that matters and ``fit`` scales it by
#: ``cell`` (see fit()). Sorted by |delta| so the smallest edit is tried first.
_LEVER_DELTA: dict[Lever, int] = {
    Lever.DROP_ONE: -1,
    Lever.ADD_ONE: +1,
    Lever.APEX_OMIT: -1,
    Lever.APEX_REPEAT: +1,
}


def _try(note_count: int, hints: LayoutHints, applied: tuple[Lever, ...]) -> LayoutPlan | None:
    try:
        return _fit_fixed(note_count, hints, applied)
    except ValueError:
        return None


def _quality(plan: LayoutPlan) -> tuple[int, int]:
    """Lower is better: prefer an even bar count, then fewer levers."""
    return (0 if plan.bars % 2 == 0 else 1, len(plan.levers_applied))


def fit(note_count: int, hints: LayoutHints) -> LayoutPlan:
    """Whole-bar layout, engaging one legal lever only when needed (spec §4.5-4.6).

    A clean, even, lever-free fit is ideal and returned at once. Otherwise each
    legal lever is tried — every lever moves the count by exactly one whole cell,
    which is one beat — and the best result wins by ``_quality``, preferring an
    even bar count, then the fewest levers. Falls back to an odd-but-sane
    lever-free count when no lever improves on it; raises only when nothing tiles.

    Because a lever shifts the beat count ``B`` by exactly ±1, and ``B ± 1`` is
    always even whenever ``B`` is odd, a single lever always reaches an even (thus
    sane, ``b = 2``) meter whenever any lever is declared. Every family declares a
    lever, so every family always tiles: the only reason to raise is a leverless
    ``LayoutHints`` whose count already has no sane meter.
    """
    best = _try(note_count, hints, ())
    if best is not None and best.bars % 2 == 0:
        return best

    for lever in sorted(hints.levers, key=lambda lv: abs(_LEVER_DELTA[lv])):
        delta = (1 if _LEVER_DELTA[lever] > 0 else -1) * hints.cell
        candidate = _try(note_count + delta, hints, (lever,))
        if candidate is None:
            continue
        if best is None or _quality(candidate) < _quality(best):
            best = candidate

    if best is None:
        msg = (
            f"no whole-bar fit for {note_count} notes with cell {hints.cell} and "
            f"levers {list(hints.levers)} (spec §4.6): the pattern needs a new "
            f"lever declared by its family"
        )
        raise ValueError(msg)
    return best


def plan_voice(voice: Voice, hints: LayoutHints) -> tuple[Voice, LayoutPlan]:
    """Fit ``voice`` and realize any chosen lever on the notes (spec §4)."""
    plan = fit(len(voice), hints)
    adjusted = list(voice)
    for lever in plan.levers_applied:
        adjusted = realize_lever(adjusted, lever, hints.seam, hints.cell)
    return adjusted, plan


def _fit_fixed(note_count: int, hints: LayoutHints, applied: tuple[Lever, ...]) -> LayoutPlan:
    cell = hints.cell
    if cell not in _SUBDIVISION_FOR_CELL:
        msg = f"cell {cell} has no subdivision mapping; expected 1-6"
        raise ValueError(msg)
    if note_count % cell != 0:
        msg = (
            f"no whole-bar fit: {note_count} notes is not a multiple of the "
            f"cell {cell}, so beats are not whole (a note-count lever is needed)"
        )
        raise ValueError(msg)

    beats = note_count // cell
    if beats < 1:
        msg = (
            f"no whole-bar fit: {note_count} notes is {beats} beats, an empty "
            f"exercise (a note-count lever must add a cell rather than drop the last)"
        )
        raise ValueError(msg)
    seam_beat = None if hints.seam is None else hints.seam // cell
    ranked = _candidates(beats, seam_beat)
    if not ranked:
        msg = (
            f"no whole-bar fit: {beats} beats has no sane beats-per-bar in "
            f"{_SANE_BEATS} (spec §4.5); a note-count lever is required"
        )
        raise ValueError(msg)

    b, m = ranked[0]
    subdivision = _SUBDIVISION_FOR_CELL[cell]
    trace = (
        f"{note_count} notes / cell {cell} = {beats} beats; chose {b}/4 x {m} "
        f"(subdivision {subdivision}); candidates {ranked}; levers {list(applied)}"
    )
    return LayoutPlan(
        subdivision=subdivision,
        time_signature=(b, 4),
        bars=m,
        levers_applied=applied,
        trace=trace,
    )


def realize_lever(voice: Voice, lever: Lever, seam: int | None, cell: int = 1) -> Voice:
    """Apply ``lever`` to ``voice``, returning a new list (spec §4.6).

    Every lever acts on a whole *cell* — the run of notes that forms one beat — so
    the note count always moves by an exact beat. The apex levers act on the cell
    ending at ``seam``: repeating the apex of a 4-note chromatic group adds four
    notes, while a single-note scale apex (``cell=1``) adds one. ``ADD_ONE`` and
    ``DROP_ONE`` act on the *trailing* cell — the last ``cell`` notes — so for
    ``cell=1`` they still repeat or drop one trailing note, unchanged.
    """
    if lever is Lever.APEX_REPEAT:
        if seam is None:
            msg = "APEX_REPEAT needs a seam index; none was supplied"
            raise ValueError(msg)
        apex = voice[seam - cell + 1 : seam + 1]
        return [*voice[: seam + 1], *apex, *voice[seam + 1 :]]
    if lever is Lever.APEX_OMIT:
        if seam is None:
            msg = "APEX_OMIT needs a seam index; none was supplied"
            raise ValueError(msg)
        return [*voice[: seam - cell + 1], *voice[seam + 1 :]]
    if lever is Lever.ADD_ONE:
        return [*voice, *voice[-cell:]]
    if lever is Lever.DROP_ONE:
        return list(voice[:-cell])
    msg = f"unknown lever {lever!r}"
    raise ValueError(msg)
