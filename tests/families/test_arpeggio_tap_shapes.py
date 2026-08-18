"""The universal two-hand tap box (Task B1, epic #67).

B0 (`melete#188`) captured that the four triads share **one** universal
two-hand box: the strings, hands, and the third/right-hand fingers are
identical across `maj`/`min`/`dim`/`aug`. Two things move with the quality, both
derived rather than tabulated — the third's and fifth's frets, and (F2,
`melete#202`, corpus rule R2) the left-hand **root finger**, which mirrors the
third's fret gap: ring (3) for a min/dim third, middle (2) for a maj/aug third.
These tests pin that finding — the box, the derived-and-pitch-preserving
placement, the quality-aware root finger, and the refusal of a non-triad
quality.
"""

from __future__ import annotations

import pytest

from melete import theory
from melete.families import arpeggio_tap_shapes as tap
from melete.instrument import PROFILES
from melete.score import Hand

BASS6 = PROFILES["bass6"]

#: Fourths tuning: a string is five semitones above the one below it.
_FOURTH = 5
_OCTAVE = 12

#: The four triad qualities B0 captured; the box is shared across them.
_TRIADS = ("maj", "min", "dim", "aug")

#: R2 — the left-hand root finger mirrors the third's fret gap: ring (3) for a
#: minor/diminished third (two frets back), middle (2) for a major/augmented
#: third (one fret back).
_ROOT_FINGER = {"maj": 2, "aug": 2, "min": 3, "dim": 3}


def test_box_has_the_four_fixed_positions():
    # Spec §5 / B0: root, third, fifth, octave-root; strings 0,1,1,2;
    # hands L,L,R,R. Third and right-hand fingers are fixed (1,1,2); the root
    # finger is derived per quality (R2) so the box declares it None.
    assert [p.string_offset for p in tap.TAP_BOX] == [0, 1, 1, 2]
    assert [p.hand for p in tap.TAP_BOX] == [Hand.LEFT, Hand.LEFT, Hand.RIGHT, Hand.RIGHT]
    assert [p.finger for p in tap.TAP_BOX] == [None, 1, 1, 2]
    assert [p.role for p in tap.TAP_BOX] == ["root", "third", "fifth", "octave-root"]


@pytest.mark.parametrize("quality", _TRIADS)
def test_root_finger_is_quality_aware_per_r2(quality):
    # F2 / R2: maj & aug root = middle (2); min & dim root = ring (3).
    places = tap.box_places(BASS6, (0, 5), quality)
    root_finger = places[0][3]
    assert root_finger == _ROOT_FINGER[quality]


@pytest.mark.parametrize("quality", _TRIADS)
def test_third_and_right_hand_fingers_are_unchanged(quality):
    # R2/R3: third = index (1); fifth = index (1); octave-root = middle (2) —
    # fixed across every quality. Only the root finger moves with the quality.
    places = tap.box_places(BASS6, (0, 5), quality)
    _root, third, fifth, octave = places
    assert third[3] == 1
    assert fifth[3] == 1
    assert octave[3] == 2


@pytest.mark.parametrize("quality", _TRIADS)
def test_box_places_sound_the_triad_chord_tones_with_pitch_preserved(quality):
    root_place = (0, 5)  # E on the low string of the bass, room for the box
    root_pitch = BASS6.tuning[root_place[0]] + root_place[1]
    expected = theory.chord_pitches(root_pitch, quality) + [root_pitch + _OCTAVE]

    places = tap.box_places(BASS6, root_place, quality)

    assert len(places) == 4
    for (string, fret, _hand, _finger), pitch in zip(places, expected, strict=True):
        # The central invariant (spec §14): the placement sounds the pitch.
        assert BASS6.tuning[string] + fret == pitch


@pytest.mark.parametrize("quality", _TRIADS)
def test_box_places_frets_are_derived_from_the_fourths_tuning(quality):
    # Not tabulated: each fret is the fourths derivation root_fret + i - 5*offset.
    root_place = (0, 5)
    root_fret = root_place[1]
    intervals = (*theory.CHORDS[quality], _OCTAVE)  # root, third, fifth, octave-root

    places = tap.box_places(BASS6, root_place, quality)

    for (_string, fret, _hand, _finger), position, interval in zip(
        places, tap.TAP_BOX, intervals, strict=True
    ):
        assert fret == root_fret + interval - _FOURTH * position.string_offset


def test_box_strings_and_hands_are_identical_across_the_four_triads():
    root_place = (0, 5)
    # Strings and hands are the same for every quality; only the frets and the
    # root finger move.
    structures = {
        quality: [
            (string, hand)
            for string, _fret, hand, _finger in tap.box_places(BASS6, root_place, quality)
        ]
        for quality in _TRIADS
    }
    reference = structures["maj"]
    for quality in _TRIADS:
        assert structures[quality] == reference


def test_box_places_stamps_the_universal_hands():
    places = tap.box_places(BASS6, (0, 5), "maj")
    assert [hand for _s, _f, hand, _finger in places] == [
        Hand.LEFT,
        Hand.LEFT,
        Hand.RIGHT,
        Hand.RIGHT,
    ]
    # For a major triad R2 gives a middle-finger root, so the fingers are the
    # middle root, index third, index fifth, and middle octave-root.
    assert [finger for _s, _f, _hand, finger in places] == [2, 1, 1, 2]


def test_seventh_quality_raises():
    # A seventh is in theory.CHORDS but has four tones, so it is not a triad and
    # is refused rather than forced through the one-octave box (spec §2, §9).
    with pytest.raises(ValueError, match="triad"):
        tap.box_places(BASS6, (0, 5), "maj7")


def test_unknown_quality_raises():
    with pytest.raises(ValueError, match="unknown quality"):
        tap.box_places(BASS6, (0, 5), "sus4")


# --- The seventh-chord tap box (Task G1, corpus R11) --------------------------
#
# A seventh chord's four tones tap on a two-string grid: each string's lower-fret
# note is left-hand-tapped, its higher-fret note right-hand-tapped (R11). String
# N carries root (left) + third (right); string N+1 carries fifth (left) +
# seventh (right). So left = root+fifth, right = third+seventh. Frets are derived
# from the chord intervals so pitch is preserved; fingering is derived the same
# way (R2/R3): root=index(1), third=index(1), seventh=middle(2), and the left-hand
# fifth mirrors its fret gap above the root — ring(3) for a perfect fifth,
# middle(2) for a diminished fifth.

#: The five seventh qualities the box covers — the exact keys in theory.CHORDS.
_SEVENTHS = ("maj7", "min7", "dom7", "m7b5", "dim7")

#: R2 — the left-hand fifth finger mirrors the fifth's fret gap above the root:
#: ring (3) for a perfect fifth (interval 7), middle (2) for a diminished fifth
#: (interval 6). maj7/dom7/min7 have a perfect fifth; m7b5/dim7 a diminished one.
_FIFTH_FINGER = {"maj7": 3, "dom7": 3, "min7": 3, "m7b5": 2, "dim7": 2}


def test_seventh_box_has_the_four_fixed_positions():
    # R11: root, third, fifth, seventh; string offsets 0,0,1,1; hands L,R,L,R.
    # Root/third/seventh fingers are quality-independent (1,1,2) so they are
    # static; the fifth finger is derived per quality (R2) so the box declares it
    # None.
    assert [p.string_offset for p in tap.SEVENTH_TAP_BOX] == [0, 0, 1, 1]
    assert [p.hand for p in tap.SEVENTH_TAP_BOX] == [
        Hand.LEFT,
        Hand.RIGHT,
        Hand.LEFT,
        Hand.RIGHT,
    ]
    assert [p.finger for p in tap.SEVENTH_TAP_BOX] == [1, 1, None, 2]
    assert [p.role for p in tap.SEVENTH_TAP_BOX] == ["root", "third", "fifth", "seventh"]


@pytest.mark.parametrize("quality", _SEVENTHS)
def test_seventh_box_places_sound_the_chord_tones_with_pitch_preserved(quality):
    root_place = (0, 5)  # low string of the bass, room for the two-string grid
    root_pitch = BASS6.tuning[root_place[0]] + root_place[1]
    expected = theory.chord_pitches(root_pitch, quality)

    places = tap.seventh_box_places(BASS6, root_place, quality)

    assert len(places) == 4
    for (string, fret, _hand, _finger), pitch in zip(places, expected, strict=True):
        # The central invariant (spec §14): the placement sounds the pitch.
        assert BASS6.tuning[string] + fret == pitch


@pytest.mark.parametrize("quality", _SEVENTHS)
def test_seventh_box_frets_are_derived_from_the_fourths_tuning(quality):
    # Not tabulated: each fret is the fourths derivation root_fret + i - 5*offset.
    root_place = (0, 5)
    root_fret = root_place[1]
    intervals = theory.CHORDS[quality]  # root, third, fifth, seventh

    places = tap.seventh_box_places(BASS6, root_place, quality)

    for (_string, fret, _hand, _finger), position, interval in zip(
        places, tap.SEVENTH_TAP_BOX, intervals, strict=True
    ):
        assert fret == root_fret + interval - _FOURTH * position.string_offset


@pytest.mark.parametrize("quality", _SEVENTHS)
def test_seventh_box_stamps_the_two_hand_grid(quality):
    places = tap.seventh_box_places(BASS6, (0, 5), quality)
    assert [hand for _s, _f, hand, _finger in places] == [
        Hand.LEFT,
        Hand.RIGHT,
        Hand.LEFT,
        Hand.RIGHT,
    ]


@pytest.mark.parametrize("quality", _SEVENTHS)
def test_seventh_box_fingers_are_derived_per_r2_r3(quality):
    # R3: root=index(1), third=index(1), seventh=middle(2) — quality-independent.
    # R2: the left-hand fifth finger mirrors its fret gap above the root, so a
    # perfect fifth takes ring(3) and a diminished fifth middle(2).
    places = tap.seventh_box_places(BASS6, (0, 5), quality)
    fingers = [finger for _s, _f, _hand, finger in places]
    assert fingers == [1, 1, _FIFTH_FINGER[quality], 2]


@pytest.mark.parametrize("quality", _SEVENTHS)
def test_seventh_box_fifth_finger_is_derived_from_the_interval(quality):
    # Not tabulated per quality: the fifth finger is fifth_interval - 4.
    fifth_interval = theory.CHORDS[quality][2]
    _root, _third, fifth, _seventh = tap.seventh_box_places(BASS6, (0, 5), quality)
    assert fifth[3] == fifth_interval - 4


@pytest.mark.parametrize("quality", _SEVENTHS)
def test_seventh_box_left_is_lower_fret_right_is_higher(quality):
    # R11: on each of the two strings the left-hand note is the lower fret and
    # the right-hand note the higher fret.
    root, third, fifth, seventh = tap.seventh_box_places(BASS6, (0, 5), quality)
    # String N: root (left) below third (right).
    assert root[0] == third[0]
    assert root[1] < third[1]
    # String N+1: fifth (left) below seventh (right).
    assert fifth[0] == seventh[0]
    assert fifth[1] < seventh[1]
    # The two strings are adjacent, climbing one string.
    assert fifth[0] == root[0] + 1


@pytest.mark.parametrize("quality", _SEVENTHS)
def test_seventh_box_places_are_on_two_strings(quality):
    places = tap.seventh_box_places(BASS6, (0, 5), quality)
    assert {string for string, _f, _h, _fin in places} == {0, 1}


def test_triad_quality_raises_in_seventh_box():
    # A triad has three tones, not a seventh — refused rather than forced through
    # the four-tone two-string grid.
    with pytest.raises(ValueError, match="seventh"):
        tap.seventh_box_places(BASS6, (0, 5), "maj")


def test_sixth_quality_raises_in_seventh_box():
    # maj6 is a four-tone chord but not a seventh; the box refuses it (an explicit
    # allowlist of the five seventh qualities, not a tone-count check).
    with pytest.raises(ValueError, match="seventh"):
        tap.seventh_box_places(BASS6, (0, 5), "maj6")


def test_unknown_quality_raises_in_seventh_box():
    with pytest.raises(ValueError, match="unknown quality"):
        tap.seventh_box_places(BASS6, (0, 5), "sus4")
