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

import pytest

from melete.families._shared import Parameters, apply_direction, there_and_back

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
