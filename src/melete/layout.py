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

#: Sane beats-per-bar; a hard filter that outranks even-M (spec §4.5).
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

    Ranked (spec §4.5): even ``M`` first, then a bar boundary on the seam, then
    larger ``b`` (fuller bars, fewer lines).
    """
    pairs = [(b, beats // b) for b in _SANE_BEATS if beats % b == 0]

    def rank(pair: tuple[int, int]) -> tuple[int, int, int]:
        b, m = pair
        even = 0 if m % 2 == 0 else 1
        on_seam = 0 if (seam_beat is not None and seam_beat % b == 0) else 1
        return (even, on_seam, -b)

    return sorted(pairs, key=rank)


def fit(note_count: int, hints: LayoutHints) -> LayoutPlan:
    """Derive a whole-bar layout for ``note_count`` notes (spec §4).

    This lever-free core tiles ``note_count / cell`` beats into sane bars. It
    raises when nothing tiles; issue #114 wraps it with a note-count lever search.
    """
    return _fit_fixed(note_count, hints, applied=())


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

    Apex levers act on a whole *cell* — the ``cell`` notes ending at ``seam`` — so
    repeating the apex of a 4-note chromatic group adds four notes, while a
    single-note scale apex (``cell=1``) adds one. ``ADD_ONE``/``DROP_ONE`` always
    act on a single trailing note.
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
        return [*voice, voice[-1]]
    if lever is Lever.DROP_ONE:
        return list(voice[:-1])
    msg = f"unknown lever {lever!r}"
    raise ValueError(msg)
