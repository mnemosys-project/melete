import pytest

from melete.families._shared import box
from melete.instrument import PROFILES

BASS6 = PROFILES["bass6"]  # tuning B0 E1 A1 D2 G2 C3


def test_box_pins_to_the_anchor_not_the_lowest_travel_base():
    # Bb1=34 sits at fret 11 on the low B string (index 0); it also sounds at
    # (2, 1) on the A string. Anchored at fret 11, the box must pin it to
    # (0, 11), not drift to the lower-fret A-string position a travel search
    # would have chosen (the defect-2 Bb-on-the-A-string drift).
    places = box(
        BASS6, [34], strings=(0, 1, 2, 3, 4, 5), anchors=(11,), family="scales", axes="root"
    )
    assert places == [(0, 11)]
    assert BASS6.tuning[0] + 11 == 34  # invariant


def test_box_raises_when_wider_than_one_position():
    # Two octaves of a pentatonic across three strings cannot fit one hand.
    with pytest.raises(ValueError, match="scales"):
        box(
            BASS6,
            [23, 35, 47],
            strings=(0, 1, 2),
            anchors=(0,),
            family="scales",
            axes="root, scale_type",
        )


def test_open_string_is_a_valid_position(spec_decision_5=True):
    # B0=23 is the open low string. Anchored at the nut, box must place it at
    # fret 0, not reject it — open strings are computed, not special-cased.
    places = box(
        BASS6, [23], strings=(0, 1, 2, 3, 4, 5), anchors=(0,), family="scales", axes="root"
    )
    assert places == [(0, 0)]


def test_two_anchor_box_is_the_67_seam():
    with pytest.raises(NotImplementedError, match="#67"):
        box(BASS6, [23, 35], strings=(0, 1), anchors=(0, 7), family="tapping", axes="hands")
