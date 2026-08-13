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
