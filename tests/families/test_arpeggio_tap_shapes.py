"""The universal two-hand tap box (Task B1, epic #67).

B0 (`melete#188`) captured that the four triads share **one** universal
two-hand box: the choreography (strings, hands, fingers) is byte-for-byte
identical across `maj`/`min`/`dim`/`aug`, and only the third's and fifth's
frets move with the quality. These tests pin that finding — the fixed box, the
derived-and-pitch-preserving placement, its quality-independence, and the
refusal of a non-triad quality.
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

#: The four triad qualities B0 captured; the box is identical across them.
_TRIADS = ("maj", "min", "dim", "aug")


def test_box_has_the_four_fixed_positions():
    # Spec §5 / B0: root, third, fifth, octave-root; strings 0,1,1,2;
    # hands L,L,R,R; fingers 3,1,1,2 — fixed and universal.
    assert [p.string_offset for p in tap.TAP_BOX] == [0, 1, 1, 2]
    assert [p.hand for p in tap.TAP_BOX] == [Hand.LEFT, Hand.LEFT, Hand.RIGHT, Hand.RIGHT]
    assert [p.finger for p in tap.TAP_BOX] == [3, 1, 1, 2]
    assert [p.role for p in tap.TAP_BOX] == ["root", "third", "fifth", "octave-root"]


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


def test_box_structure_is_identical_across_the_four_triads():
    root_place = (0, 5)
    # Strings, hands, fingers are the same for every quality; only frets move.
    structures = {
        quality: [
            (string, hand, finger)
            for string, _fret, hand, finger in tap.box_places(BASS6, root_place, quality)
        ]
        for quality in _TRIADS
    }
    reference = structures["maj"]
    for quality in _TRIADS:
        assert structures[quality] == reference


def test_box_places_stamps_the_universal_hands_and_fingers():
    places = tap.box_places(BASS6, (0, 5), "maj")
    assert [hand for _s, _f, hand, _finger in places] == [
        Hand.LEFT,
        Hand.LEFT,
        Hand.RIGHT,
        Hand.RIGHT,
    ]
    assert [finger for _s, _f, _hand, finger in places] == [3, 1, 1, 2]


def test_seventh_quality_raises():
    # A seventh is in theory.CHORDS but has four tones, so it is not a triad and
    # is refused rather than forced through the one-octave box (spec §2, §9).
    with pytest.raises(ValueError, match="triad"):
        tap.box_places(BASS6, (0, 5), "maj7")


def test_unknown_quality_raises():
    with pytest.raises(ValueError, match="unknown quality"):
        tap.box_places(BASS6, (0, 5), "sus4")
