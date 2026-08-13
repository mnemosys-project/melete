"""Tests for the layout fitter's contract and lever realization (spec §4.6).

This module covers only the first slice of the fitter: the `LayoutHints`
dataclass a family hands the fitter, and `realize_lever`, the note-count
adjustment it applies. The plan (`fit`/`LayoutPlan`) lands in later tasks.

The point of the lever tests is that an apex lever acts on a whole *cell* — the
run of notes that forms one beat — not on a single note. Repeating the apex of a
four-note chromatic group must add four notes, while a single-note scale apex
(`cell=1`) adds one. A lever that always touched one note would silently mis-fit
every chromatic exercise, so each cell width is pinned here.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from melete.layout import Lever, LayoutHints, realize_lever
from melete.score import Note


def _n(pitch: int) -> Note:
    """A throwaway note carrying only a distinguishable `pitch`.

    Position, duration and articulation are fixed and irrelevant here: the lever
    tests assert on the pitch sequence alone, so `fret` tracks `pitch` merely to
    keep every note individually legal.
    """
    return Note(
        pitch=pitch,
        string=0,
        fret=pitch - 23,
        duration=Fraction(1, 4),
        finger=None,
        accent=False,
    )


def _pitches(voice: list[Note]) -> list[int]:
    """The pitch sequence of `voice`, the only thing the lever tests read."""
    return [note.pitch for note in voice]


def test_layout_hints_stores_its_fields() -> None:
    hints = LayoutHints(cell=4, seam=24, levers=(Lever.APEX_REPEAT,))
    assert hints.cell == 4
    assert hints.seam == 24
    assert hints.levers == (Lever.APEX_REPEAT,)


def test_a_seam_may_be_absent() -> None:
    hints = LayoutHints(cell=1, seam=None, levers=())
    assert hints.seam is None


@pytest.mark.parametrize("cell", [0, -1])
def test_a_cell_below_one_is_rejected(cell: int) -> None:
    with pytest.raises(ValueError, match="cell"):
        LayoutHints(cell=cell, seam=None, levers=())


def test_apex_repeat_duplicates_a_single_note_apex() -> None:
    voice = [_n(23), _n(24), _n(25)]
    assert _pitches(realize_lever(voice, Lever.APEX_REPEAT, seam=2)) == [23, 24, 25, 25]


def test_apex_repeat_duplicates_a_whole_cell() -> None:
    # A four-note chromatic group ending at its apex: repeating it adds four
    # notes, not one.
    voice = [_n(23), _n(24), _n(25), _n(26), _n(27), _n(28), _n(29), _n(30)]
    result = realize_lever(voice, Lever.APEX_REPEAT, seam=3, cell=4)
    assert _pitches(result) == [23, 24, 25, 26, 23, 24, 25, 26, 27, 28, 29, 30]


def test_apex_omit_drops_a_single_note_apex() -> None:
    voice = [_n(23), _n(24), _n(25)]
    assert _pitches(realize_lever(voice, Lever.APEX_OMIT, seam=1)) == [23, 25]


def test_apex_omit_drops_a_whole_cell() -> None:
    voice = [_n(23), _n(24), _n(25), _n(26), _n(27), _n(28), _n(29), _n(30)]
    result = realize_lever(voice, Lever.APEX_OMIT, seam=3, cell=4)
    assert _pitches(result) == [27, 28, 29, 30]


def test_add_one_repeats_the_trailing_note() -> None:
    voice = [_n(23), _n(24), _n(25)]
    assert _pitches(realize_lever(voice, Lever.ADD_ONE, seam=None)) == [23, 24, 25, 25]


def test_drop_one_removes_the_trailing_note() -> None:
    voice = [_n(23), _n(24), _n(25)]
    assert _pitches(realize_lever(voice, Lever.DROP_ONE, seam=None)) == [23, 24]


@pytest.mark.parametrize("lever", [Lever.APEX_REPEAT, Lever.APEX_OMIT])
def test_an_apex_lever_without_a_seam_is_rejected(lever: Lever) -> None:
    with pytest.raises(ValueError, match="seam"):
        realize_lever([_n(23), _n(24), _n(25)], lever, seam=None)


def test_realize_lever_returns_a_new_list() -> None:
    voice = [_n(23), _n(24), _n(25)]
    result = realize_lever(voice, Lever.DROP_ONE, seam=None)
    assert result is not voice
    assert _pitches(voice) == [23, 24, 25]
