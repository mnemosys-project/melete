"""`box`'s two-anchor (two-hand tapping) path — spec §6, epic #67, Task B2.

The single-anchor path is covered by `test_shared_box.py` and must stay
byte-for-byte; these tests exercise only the two-anchor path realized here.

The load-bearing properties (spec §6, §10):

- each hand's fretted span satisfies `position_span`;
- both hands are non-empty;
- every note sits on a string that sounds its pitch (pitch preserved);
- the supplied partition is honoured — **there is no global fret ordering**;
  the partition, not fret order, decides which hand frets a note (§11 dec. 6);
- an unrealizable two-hand box raises `ValueError`, never a clamped layout (§9).
"""

import pytest

from melete.families._shared import box
from melete.instrument import PROFILES
from melete.score import Hand

BASS6 = PROFILES["bass6"]  # tuning B0=23 E1=28 A1=33 D2=38 G2=43 C3=48; span 4
STRINGS = (0, 1, 2, 3, 4, 5)
LEFT, RIGHT = Hand.LEFT, Hand.RIGHT


def _sounds(pitch: int, string: int, fret: int) -> bool:
    """The central invariant: the placed (string, fret) sounds `pitch`."""
    return BASS6.tuning[string] + fret == pitch


def test_two_hand_box_places_each_hand_near_its_own_anchor():
    # Left near fret 3, right near fret 10. Left: 26=(0,3), 31=(1,3);
    # right: 48=(3,10), 53=(4,10). Each hand's span is 0, both non-empty.
    result = box(
        BASS6,
        [26, 31, 48, 53],
        strings=STRINGS,
        anchors=(3, 10),
        family="tapping",
        axes="quality, inversion",
        hands=[LEFT, LEFT, RIGHT, RIGHT],
    )
    assert result == [(0, 3, LEFT), (1, 3, LEFT), (3, 10, RIGHT), (4, 10, RIGHT)]


def test_two_hand_box_preserves_pitch_on_every_note():
    pitches = [26, 31, 48, 53]
    result = box(
        BASS6,
        pitches,
        strings=STRINGS,
        anchors=(3, 10),
        family="tapping",
        axes="quality, inversion",
        hands=[LEFT, LEFT, RIGHT, RIGHT],
    )
    for pitch, (string, fret, _hand) in zip(pitches, result, strict=True):
        assert _sounds(pitch, string, fret)


def test_two_hand_box_honours_the_partition_with_no_global_fret_ordering():
    # Left anchor 6, right anchor 8 (left lower, right higher). The left tone
    # 41 lands at (2, 8); the right tone 44 lands at (3, 6). So a LEFT note sits
    # at a HIGHER fret than a RIGHT note: the hands leapfrog, and the returned
    # hand for each note is the one the partition supplied, not the one a
    # low-fret-left / high-fret-right rule would derive (spec §11 decision 6).
    result = box(
        BASS6,
        [41, 44],
        strings=STRINGS,
        anchors=(6, 8),
        family="tapping",
        axes="quality, inversion",
        hands=[LEFT, RIGHT],
    )
    assert result == [(2, 8, LEFT), (3, 6, RIGHT)]
    (_ls, left_fret, left_hand), (_rs, right_fret, right_hand) = result
    assert left_hand is LEFT and right_hand is RIGHT
    assert left_fret > right_fret  # no global fret ordering across the hands


def test_two_hand_box_raises_when_a_hand_exceeds_one_position():
    # The right hand's three tones on strings 0-2 anchored at the nut span 14
    # frets — wider than one position — so the box raises rather than clamps.
    with pytest.raises(ValueError, match="tapping"):
        box(
            BASS6,
            [26, 23, 35, 47],
            strings=(0, 1, 2),
            anchors=(3, 0),
            family="tapping",
            axes="quality, inversion",
            hands=[LEFT, RIGHT, RIGHT, RIGHT],
        )


@pytest.mark.parametrize("partition", [[LEFT, LEFT], [RIGHT, RIGHT]])
def test_two_hand_box_raises_when_a_hand_is_empty(partition):
    # A partition that names only one hand is not a two-hand box — neither an
    # all-left nor an all-right partition (both hands must be non-empty).
    with pytest.raises(ValueError, match="both hands"):
        box(
            BASS6,
            [26, 31],
            strings=STRINGS,
            anchors=(3, 10),
            family="tapping",
            axes="quality, inversion",
            hands=partition,
        )


def test_one_anchor_box_rejects_a_hand_partition():
    # The one-hand path takes no partition; passing one is a caller error, not a
    # silently ignored argument.
    with pytest.raises(ValueError, match="single hand"):
        box(
            BASS6,
            [26],
            strings=STRINGS,
            anchors=(3,),
            family="scales",
            axes="root",
            hands=[LEFT],
        )


def test_two_hand_box_raises_when_the_partition_length_mismatches():
    with pytest.raises(ValueError, match="partition"):
        box(
            BASS6,
            [26, 31, 48],
            strings=STRINGS,
            anchors=(3, 10),
            family="tapping",
            axes="quality, inversion",
            hands=[LEFT, RIGHT],
        )


def test_more_than_two_anchors_is_not_a_musical_case():
    # One or two fretting hands is the whole musical space (spec §11 decision 2);
    # three anchors is neither the one-hand nor the two-hand path.
    with pytest.raises(NotImplementedError, match="#67"):
        box(
            BASS6,
            [26, 31, 48],
            strings=STRINGS,
            anchors=(3, 7, 11),
            family="tapping",
            axes="quality, inversion",
            hands=[LEFT, RIGHT, RIGHT],
        )


def test_two_hand_box_requires_a_partition():
    with pytest.raises(ValueError, match="partition"):
        box(
            BASS6,
            [26, 31],
            strings=STRINGS,
            anchors=(3, 10),
            family="tapping",
            axes="quality, inversion",
        )
