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
