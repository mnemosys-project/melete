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

from melete.layout import LayoutHints, LayoutPlan, Lever, fit, plan_voice, realize_lever
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


def test_add_one_repeats_a_whole_cell() -> None:
    # §132: add/drop move a whole cell so the beat count stays integral. On a
    # two-note cell, ADD_ONE repeats the trailing two notes, not one.
    voice: Voice = [_n(23), _n(24), _n(25), _n(26)]
    result = realize_lever(voice, Lever.ADD_ONE, seam=None, cell=2)
    assert _pitches(result) == [23, 24, 25, 26, 25, 26]


def test_drop_one_removes_the_trailing_note() -> None:
    voice: Voice = [_n(23), _n(24), _n(25)]
    assert _pitches(realize_lever(voice, Lever.DROP_ONE, seam=None)) == [23, 24]


def test_drop_one_removes_a_whole_cell() -> None:
    # The mirror of add: DROP_ONE drops the trailing two-note cell.
    voice: Voice = [_n(23), _n(24), _n(25), _n(26)]
    assert _pitches(realize_lever(voice, Lever.DROP_ONE, seam=None, cell=2)) == [23, 24]


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


def test_fit_never_chooses_2_4_when_a_fuller_meter_tiles() -> None:
    # melete#174: 28 sixteenths / cell 1 = 28 beats. 2/4 x 14 is even-barred and
    # once won the even-M rank outright, but 2/4 is now a strict last resort — it
    # is never chosen while any 3/4, 4/4 or 6/4 tiles, so the odd-barred 4/4 x 7
    # wins instead. This is the whole point of the demotion.
    plan = fit(28, LayoutHints(cell=1, seam=None, levers=()))
    assert plan.time_signature == (4, 4)
    assert plan.bars == 7


def test_fit_uses_2_4_only_as_a_last_resort_to_rescue_a_one_beat_exercise() -> None:
    # melete#174/#178: a genuinely one-beat exercise (4 notes / cell 4 = 1 beat,
    # the span=1 chromatic shape) has no 3/4, 4/4 or 6/4 fit at any reachable
    # count — APEX_REPEAT can only double the apex cell to 2 beats, and both
    # reachable fits (leverless: no meter; repeat: 2/4 x 1) are un-notatable-any-
    # other-way. #178 makes 2/4 a true last resort, so this is the *sole* survivor
    # where every reachable fit is 2/4: it still tiles as 2/4 x 1 via the repeat.
    plan = fit(4, LayoutHints(cell=4, seam=3, levers=(Lever.APEX_REPEAT, Lever.APEX_OMIT)))
    assert plan.time_signature == (2, 4)
    assert plan.bars == 1
    assert plan.levers_applied == (Lever.APEX_REPEAT,)


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
    # fills one beat; a cell of 7 has no engraving and must fail loudly. With no
    # lever to try, the lever search re-raises its own outer "no whole-bar fit"
    # message (the inner "no subdivision mapping" cause is wrapped, spec §4.6).
    with pytest.raises(ValueError, match="no whole-bar fit"):
        fit(28, LayoutHints(cell=7, seam=None, levers=()))


def test_fit_returns_a_clean_even_fit_without_a_lever() -> None:
    # 48 sixteenths / cell 4 = 12 beats -> 6/4 x 2, already even: no lever fires
    # even though two are legal here (spec §4.5).
    plan = fit(48, LayoutHints(cell=4, seam=24, levers=(Lever.APEX_REPEAT, Lever.APEX_OMIT)))
    assert plan.time_signature == (6, 4)
    assert plan.bars == 2
    assert plan.levers_applied == ()


def test_fit_fires_an_apex_lever_from_a_prime_baseline() -> None:
    # 44 notes / cell 4 = 11 beats has no sane bar. APEX_REPEAT adds the 4-note
    # apex cell -> 48 -> 6/4 x 2 (even); APEX_OMIT -> 40 -> 2/4 x 5 is odd and
    # loses on quality, so the repeat wins (the chromatic case, spec §4.6).
    plan = fit(44, LayoutHints(cell=4, seam=23, levers=(Lever.APEX_REPEAT, Lever.APEX_OMIT)))
    assert plan.time_signature == (6, 4)
    assert plan.bars == 2
    assert plan.levers_applied == (Lever.APEX_REPEAT,)


def test_fit_adds_one_note_to_reach_an_even_sane_meter() -> None:
    # 11 notes / cell 1 = 11 beats has no sane bar; +1 -> 12 -> 6/4 x 2.
    plan = fit(11, LayoutHints(cell=1, seam=None, levers=(Lever.ADD_ONE, Lever.DROP_ONE)))
    assert plan.time_signature == (6, 4)
    assert plan.bars == 2
    assert plan.levers_applied == (Lever.ADD_ONE,)


def test_fit_burns_a_lever_to_escape_a_leverless_2_4() -> None:
    # melete#178: 10 notes / cell 1 = 10 beats tiles LEVERLESSLY only on 2/4 x 5
    # (10 is 2 x an odd not divisible by 3). Under #174 that leverless 2/4 still
    # won, because it spent no lever. #178 makes 2/4 a *true* last resort: any
    # non-2 fit — even one that burns a single lever — outranks a 2/4 fit, so
    # DROP_ONE -> 9 -> 3/4 x 3 is chosen instead. The one leverless-2/4 count is
    # rescued by spending a lever.
    plan = fit(10, LayoutHints(cell=1, seam=None, levers=(Lever.ADD_ONE, Lever.DROP_ONE)))
    assert plan.time_signature == (3, 4)
    assert plan.bars == 3
    assert plan.levers_applied == (Lever.DROP_ONE,)


@pytest.mark.parametrize(
    ("beats", "bars", "lever"),
    [
        (10, 3, Lever.DROP_ONE),  # -1 -> 9  -> 3/4 x 3
        (14, 5, Lever.ADD_ONE),  # +1 -> 15 -> 3/4 x 5
        (22, 7, Lever.DROP_ONE),  # -1 -> 21 -> 3/4 x 7
        (26, 9, Lever.ADD_ONE),  # +1 -> 27 -> 3/4 x 9
    ],
)
def test_fit_escapes_every_leverless_2_4_count_to_3_4(beats: int, bars: int, lever: Lever) -> None:
    # melete#178: the four cell-1 counts that tile leverlessly on 2/4 alone
    # (2 x odd-not-divisible-by-3: 10, 14, 22, 26) each reach a 3/4 fit by
    # spending exactly one lever (±1 beat lands a multiple of 3). Because 2/4 is
    # now a true last resort, the fitter burns that lever every time rather than
    # settle for the leverless 2/4.
    plan = fit(beats, LayoutHints(cell=1, seam=None, levers=(Lever.ADD_ONE, Lever.DROP_ONE)))
    assert plan.time_signature == (3, 4)
    assert plan.bars == bars
    assert plan.levers_applied == (lever,)


def test_fit_drops_a_whole_cell_to_reach_an_even_meter() -> None:
    # §132: 26 notes / cell 2 = 13 beats is prime, so no meter divides it. Every
    # lever now moves the count by exactly one cell (= one beat), so DROP_ONE
    # reaches 24 -> 12 beats -> an even, sane meter; ADD_ONE reaches 28 -> 14 ->
    # 2/4 x 7 (odd) and loses on quality. Exactly one lever fires.
    plan = fit(26, LayoutHints(cell=2, seam=None, levers=(Lever.DROP_ONE, Lever.ADD_ONE)))
    assert plan.subdivision == "eighth"
    assert plan.time_signature == (6, 4)
    assert plan.bars == 2
    assert plan.levers_applied == (Lever.DROP_ONE,)


def test_fit_adds_a_cell_rather_than_dropping_to_an_empty_exercise() -> None:
    # §132 edge: a single-cell voice (4 notes / cell 4 = 1 beat) has no sane
    # meter. DROP_ONE would empty it (0 beats), which is no exercise at all and
    # must not be chosen over ADD_ONE's 2/4 bar — dropping the last cell can
    # never win, so the fitter adds a cell instead.
    plan = fit(4, LayoutHints(cell=4, seam=None, levers=(Lever.ADD_ONE, Lever.DROP_ONE)))
    assert plan.time_signature == (2, 4)
    assert plan.bars == 1
    assert plan.levers_applied == (Lever.ADD_ONE,)


def test_plan_voice_realizes_the_chosen_lever_on_the_notes() -> None:
    # plan_voice fits the note count and then applies the chosen lever to the
    # notes: the 4-note apex cell is repeated, taking 44 notes to 48.
    notes: Voice = [_n(23 + i) for i in range(44)]
    out, plan = plan_voice(notes, LayoutHints(cell=4, seam=23, levers=(Lever.APEX_REPEAT,)))
    assert len(out) == 48
    assert plan.levers_applied == (Lever.APEX_REPEAT,)


def test_fit_raises_only_when_nothing_tiles_even_with_levers() -> None:
    # 14 notes / cell 2 = 7 beats has no sane bar and no lever is declared, so
    # the search exhausts and re-raises its outer message (spec §4.6).
    with pytest.raises(ValueError, match="no whole-bar fit"):
        fit(14, LayoutHints(cell=2, seam=None, levers=()))
