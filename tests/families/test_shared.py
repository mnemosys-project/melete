"""Tests for the helpers the families share (spec §7, §13).

These test `_shared` directly rather than through a family, which is the point
of the module existing: `chromatic` and `scales` each cover their own use of
these helpers incidentally, but only from one side. A family test cannot show
that the parameter reader says "arpeggios" when arpeggios asks it to, or that
`apply_direction` is genuinely indifferent to what it is ordering — and those
are the two properties tasks B7 and B8 are about to depend on.

`apply_direction`'s turnaround has a test of its own here for the reason the
plan singles it out: the last element is played once, and the slice that says
so is the easiest line in this codebase to write backwards.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from melete.families._shared import (
    Parameters,
    apply_direction,
    boxed,
    directed_by_cell,
    there_and_back,
)
from melete.instrument import PROFILES, hand_span

BASS6 = PROFILES["bass6"]

#: What a `positional` caller passes as the axes it could not satisfy (§13).
AXIS_LIST = "root, scale_type, range_octaves and string_set"

#: A family that does not exist, named to prove the reader is parameterized
#: rather than quietly hard-coded to one of the two families that use it.
AXES = ("root", "direction", "scale_type")


def reader(family: str = "arpeggios", **values: object) -> Parameters:
    """A `Parameters` over `values`, for a family with `AXES`."""
    return Parameters(family, AXES, values)


# --------------------------------------------------------------------------
# `Parameters`: §13's contract for a bad parameter, written once
# --------------------------------------------------------------------------


def test_a_present_parameter_is_returned_untouched() -> None:
    sentinel = object()
    assert reader(root=sentinel).value("root") is sentinel


def test_a_missing_parameter_names_the_family_the_axis_and_every_axis() -> None:
    with pytest.raises(ValueError, match=r"^arpeggios: parameter 'root' is required") as caught:
        reader().value("root")
    assert str(caught.value).endswith("the family's axes are ['root', 'direction', 'scale_type']")


def test_the_family_name_comes_from_the_caller() -> None:
    # The one thing that differed between `chromatic`'s and `scales`' copies of
    # these three readings. A shared helper that named one of them would put the
    # wrong family in the other's errors.
    for family in ("chromatic", "scales", "intervals"):
        with pytest.raises(ValueError, match=rf"^{family}: parameter 'root' is required"):
            reader(family).value("root")


def test_an_identifier_in_the_registry_is_returned() -> None:
    assert reader(direction="up_down").identifier("direction") == "up_down"


def test_an_unknown_identifier_lists_the_accepted_values() -> None:
    with pytest.raises(ValueError, match=r"arpeggios: unknown direction 'sideways'.*up_down"):
        reader(direction="sideways").identifier("direction")


def test_a_non_string_identifier_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"arpeggios: unknown direction 3;"):
        reader(direction=3).identifier("direction")


def test_an_identifier_is_checked_against_its_own_axis() -> None:
    # `dorian` is a registry identifier, but not one of `direction`'s. Each axis
    # is a separate namespace and the reader never searches across them.
    with pytest.raises(ValueError, match=r"unknown direction 'dorian'"):
        reader(direction="dorian").identifier("direction")


def test_an_integer_axis_is_returned() -> None:
    assert reader(root=-3).integer("root") == -3


def test_a_non_integer_range_axis_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"arpeggios: root must be an integer, got '33'"):
        reader(root="33").integer("root")


def test_a_boolean_is_not_an_integer() -> None:
    # `True` is not root 1, however willingly Python would add it.
    with pytest.raises(ValueError, match=r"arpeggios: root must be an integer, got True"):
        reader(root=True).integer("root")


def test_a_missing_axis_is_reported_before_its_type_is() -> None:
    # Both readings go through `value`, so an absent axis is always the
    # missing-axis error and never a type complaint about `None`.
    with pytest.raises(ValueError, match=r"parameter 'root' is required"):
        reader().integer("root")
    with pytest.raises(ValueError, match=r"parameter 'direction' is required"):
        reader().identifier("direction")


def test_extra_parameters_are_ignored_rather_than_rejected() -> None:
    # §8's rhythm axes travel in the same dictionary as §7's family axes.
    assert reader(root=33, subdivision="eighth").integer("root") == 33


# --------------------------------------------------------------------------
# `boxed`: `positional` means a position, or it means nothing (issue #57)
# --------------------------------------------------------------------------


def test_a_layout_that_fits_the_hand_is_returned() -> None:
    # Three degrees of A Ionian across the E and A strings: every one of them
    # lies under a hand at the fifth fret.
    places = boxed(BASS6, [33, 35, 37], (1, 2), "scales", AXIS_LIST)
    assert hand_span(fret for _string, fret in places) <= BASS6.position_span


def test_content_wider_than_a_position_raises_rather_than_reporting_success() -> None:
    # An octave apart on one string is twelve frets of neck. The nearest layout
    # is the *least bad* one, and calling that "positional" is the mislabelling
    # issue #57 exists to stop.
    with pytest.raises(ValueError, match=r"one position") as raised:
        boxed(BASS6, [35, 47], (2,), "scales", AXIS_LIST)

    message = str(raised.value)
    assert message.startswith("scales:")
    assert "12 frets" in message
    assert AXIS_LIST in message


def test_an_open_string_does_not_widen_the_position() -> None:
    # A minor pentatonic from the open A string: frets 3, 5 and 7 are one
    # position and the open root is sounded without the fretting hand at all.
    places = boxed(BASS6, [33, 36, 38, 40, 43, 45], (2, 3), "scales", AXIS_LIST)
    assert places == [(2, 0), (2, 3), (2, 5), (2, 7), (3, 5), (3, 7)]


def test_the_position_is_the_profile_s_and_not_a_constant_of_this_module() -> None:
    # A hand covers as many frets as the instrument's spacing allows, so the
    # bound is read from the profile the exercise is laid out on.
    narrow = replace(BASS6, position_span=1)
    with pytest.raises(ValueError, match=r"against a position of 1"):
        boxed(narrow, [33, 35, 37], (1, 2), "scales", AXIS_LIST)


# --------------------------------------------------------------------------
# `there_and_back`: the turnaround is played once
# --------------------------------------------------------------------------


def test_there_and_back_does_not_replay_the_turnaround() -> None:
    assert there_and_back([1, 2, 3]) == [1, 2, 3, 2, 1]


def test_there_and_back_over_one_element_is_a_single_pass() -> None:
    # There is nothing to return along, so the element is not doubled.
    assert there_and_back(["only"]) == ["only"]


def test_there_and_back_over_two_elements_returns_to_the_first() -> None:
    assert there_and_back((1, 2)) == [1, 2, 1]


# --------------------------------------------------------------------------
# `apply_direction`: §7's `direction` axis, indifferent to what it orders
# --------------------------------------------------------------------------


def test_up_keeps_the_order() -> None:
    assert apply_direction([1, 2, 3], "up") == [1, 2, 3]


def test_down_reverses() -> None:
    assert apply_direction([1, 2, 3], "down") == [3, 2, 1]


def test_up_down_does_not_repeat_the_apex() -> None:
    assert apply_direction([1, 2, 3], "up_down") == [1, 2, 3, 2, 1]


@pytest.mark.parametrize("direction", ["up", "down", "up_down"])
def test_the_caller_s_sequence_is_never_returned_or_mutated(direction: str) -> None:
    # Every family hands in a list it is still holding, and `chromatic` goes on
    # to read the min and max of its own.
    items = [1, 2, 3]
    ordered = apply_direction(items, direction)
    assert ordered is not items
    assert items == [1, 2, 3]


def test_it_orders_whatever_it_is_given() -> None:
    # `scales` orders degree indices and `chromatic` orders string indices; a
    # helper that knew which would be a family in disguise.
    assert apply_direction(("low", "mid", "high"), "up_down") == [
        "low",
        "mid",
        "high",
        "mid",
        "low",
    ]


@pytest.mark.parametrize("direction", ["up", "down", "up_down"])
def test_no_direction_adds_or_drops_content(direction: str) -> None:
    assert set(apply_direction([1, 2, 3, 4], direction)) == {1, 2, 3, 4}


def test_a_single_element_is_one_note_in_every_direction() -> None:
    for direction in ("up", "down", "up_down"):
        assert apply_direction([7], direction) == [7]


# --------------------------------------------------------------------------
# `directed_by_cell`: `direction` at the cell boundary, whole cells throughout
# --------------------------------------------------------------------------

#: Three two-note cells: (0, 2), (1, 3), (2, 4), as a `windowed` thirds run.
_THIRDS = [0, 2, 1, 3, 2, 4]


def test_directed_by_cell_up_keeps_the_order() -> None:
    assert directed_by_cell(_THIRDS, "up", 2) == [0, 2, 1, 3, 2, 4]


def test_directed_by_cell_down_is_the_note_level_retrograde() -> None:
    # `down` never turns around, so it stays the full note-level retrograde a
    # descending figure is (scales/arpeggios), not a cell-order reversal: the
    # descending third is the top pair played high note first.
    assert directed_by_cell(_THIRDS, "down", 2) == [4, 2, 3, 1, 2, 0]


def test_directed_by_cell_up_down_turns_around_a_whole_cell_early() -> None:
    # Ascend, then retrograde the ascent minus its apex cell (2, 4): the apex is
    # played once and the count stays a whole number of cells (5 cells, 10 notes,
    # not the untileable 11 a note-level turnaround would leave) — the §132 fix.
    assert directed_by_cell(_THIRDS, "up_down", 2) == [0, 2, 1, 3, 2, 4, 3, 1, 2, 0]


@pytest.mark.parametrize("direction", ["up", "down", "up_down"])
def test_directed_by_cell_is_apply_direction_when_the_cell_is_one_note(direction: str) -> None:
    # For a single-note cell the cell and the note are the same thing, so the
    # cell-level turnaround must reduce exactly to the note-level one.
    items = [10, 11, 12, 13]
    assert directed_by_cell(items, direction, 1) == apply_direction(items, direction)


@pytest.mark.parametrize("direction", ["up", "down", "up_down"])
def test_directed_by_cell_always_yields_whole_cells(direction: str) -> None:
    # The property the fix rests on: however the direction turns the cells, the
    # result is always a whole number of cells, so the fitter has integral beats.
    assert len(directed_by_cell(_THIRDS, direction, 2)) % 2 == 0
