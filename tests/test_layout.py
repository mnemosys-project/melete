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
from typing import cast

import pytest

from melete.layout import LayoutHints, LayoutPlan, Lever, fit, realize_lever
from melete.score import Note, Voice


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


def _pitches(voice: Voice) -> list[int]:
    """The pitch sequence of `voice`, the only thing the lever tests read.

    The `isinstance` narrowing is the assertion that these voices are all bare
    notes: `realize_lever` never introduces a tuplet, so a `Tuplet` here would be
    a real defect rather than something to paper over.
    """
    pitches: list[int] = []
    for item in voice:
        assert isinstance(item, Note)
        pitches.append(item.pitch)
    return pitches


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
    voice: Voice = [_n(23), _n(24), _n(25)]
    assert _pitches(realize_lever(voice, Lever.APEX_REPEAT, seam=2)) == [23, 24, 25, 25]


def test_apex_repeat_duplicates_a_whole_cell() -> None:
    # A four-note chromatic group ending at its apex: repeating it adds four
    # notes, not one.
    voice: Voice = [_n(23), _n(24), _n(25), _n(26), _n(27), _n(28), _n(29), _n(30)]
    result = realize_lever(voice, Lever.APEX_REPEAT, seam=3, cell=4)
    assert _pitches(result) == [23, 24, 25, 26, 23, 24, 25, 26, 27, 28, 29, 30]


def test_apex_omit_drops_a_single_note_apex() -> None:
    voice: Voice = [_n(23), _n(24), _n(25)]
    assert _pitches(realize_lever(voice, Lever.APEX_OMIT, seam=1)) == [23, 25]


def test_apex_omit_drops_a_whole_cell() -> None:
    voice: Voice = [_n(23), _n(24), _n(25), _n(26), _n(27), _n(28), _n(29), _n(30)]
    result = realize_lever(voice, Lever.APEX_OMIT, seam=3, cell=4)
    assert _pitches(result) == [27, 28, 29, 30]


def test_add_one_repeats_the_trailing_note() -> None:
    voice: Voice = [_n(23), _n(24), _n(25)]
    assert _pitches(realize_lever(voice, Lever.ADD_ONE, seam=None)) == [23, 24, 25, 25]


def test_drop_one_removes_the_trailing_note() -> None:
    voice: Voice = [_n(23), _n(24), _n(25)]
    assert _pitches(realize_lever(voice, Lever.DROP_ONE, seam=None)) == [23, 24]


@pytest.mark.parametrize("lever", [Lever.APEX_REPEAT, Lever.APEX_OMIT])
def test_an_apex_lever_without_a_seam_is_rejected(lever: Lever) -> None:
    voice: Voice = [_n(23), _n(24), _n(25)]
    with pytest.raises(ValueError, match="seam"):
        realize_lever(voice, lever, seam=None)


def test_an_unknown_lever_is_rejected() -> None:
    # The fitter only ever passes a `Lever`, so the trailing guard is
    # unreachable in normal use; a bogus value proves it fails loudly rather
    # than silently returning the voice unchanged (no silent failures).
    voice: Voice = [_n(23)]
    with pytest.raises(ValueError, match="unknown lever"):
        realize_lever(voice, cast("Lever", object()), seam=None)


def test_realize_lever_returns_a_new_list() -> None:
    voice: Voice = [_n(23), _n(24), _n(25)]
    result = realize_lever(voice, Lever.DROP_ONE, seam=None)
    assert result is not voice
    assert _pitches(voice) == [23, 24, 25]


def test_fit_prefers_fuller_bars_among_even_seam_aligned_meters() -> None:
    # 48 sixteenths / cell 4 = 12 beats. Every candidate meter with an even bar
    # count that also lands a bar boundary on the seam is equally legible, so the
    # tie breaks on the fullest bar: 6/4 x 2 beats 3/4 x 4 and 2/4 x 6.
    plan = fit(48, LayoutHints(cell=4, seam=24, levers=()))
    assert plan.subdivision == "sixteenth"
    assert plan.time_signature == (6, 4)
    assert plan.bars == 2
    assert plan.levers_applied == ()


def test_fit_breaks_a_larger_beat_count_on_the_fuller_bar() -> None:
    # 32 eighths / cell 2 = 16 beats. 4/4 x 4 and 2/4 x 8 are both even and
    # seam-aligned; the larger beats-per-bar wins.
    plan = fit(32, LayoutHints(cell=2, seam=16, levers=()))
    assert plan.time_signature == (4, 4)
    assert plan.bars == 4


def test_fit_maps_the_cell_to_its_subdivision() -> None:
    triplet = fit(24, LayoutHints(cell=3, seam=None, levers=()))
    sextuplet = fit(24, LayoutHints(cell=6, seam=None, levers=()))
    assert triplet.subdivision == "triplet_eighth"
    assert sextuplet.subdivision == "sextuplet"


def test_fit_records_a_layout_plan() -> None:
    plan = fit(48, LayoutHints(cell=4, seam=24, levers=()))
    assert isinstance(plan, LayoutPlan)
    assert plan.trace  # a human-readable account of the decision


def test_fit_raises_when_no_sane_meter_divides_the_beats() -> None:
    # 14 notes / cell 2 = 7 beats; none of the sane beats-per-bar divides 7.
    with pytest.raises(ValueError, match="no whole-bar fit"):
        fit(14, LayoutHints(cell=2, seam=None, levers=()))


def test_fit_raises_when_the_note_count_is_not_a_whole_number_of_beats() -> None:
    # 15 notes / cell 2 leaves a half-filled beat; a note-count lever is needed.
    with pytest.raises(ValueError, match="no whole-bar fit"):
        fit(15, LayoutHints(cell=2, seam=None, levers=()))


def test_fit_rejects_a_cell_with_no_subdivision() -> None:
    # `LayoutHints` admits any cell >= 1, but only 1-6 map to a subdivision that
    # fills one beat; a cell of 7 has no engraving and must fail loudly.
    with pytest.raises(ValueError, match="no subdivision mapping"):
        fit(28, LayoutHints(cell=7, seam=None, levers=()))
