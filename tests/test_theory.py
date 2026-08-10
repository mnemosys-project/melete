"""Tests for 12-TET pitch, scale and chord math.

Spec §14 calls for exhaustive coverage here: all 12 roots against every scale
type, verified against known interval content. `theory` and `instrument` are the
most reused modules in the system, so a defect here surfaces as wrong notes in
every family at once.
"""

from __future__ import annotations

from itertools import pairwise

import pytest

from melete.theory import (
    CHORDS,
    PITCH_CLASSES,
    SCALES,
    chord_pitches,
    scale_pitches,
)

# C4 = 60 throughout, per the Score IR.
C4 = 60


# --------------------------------------------------------------------------
# Pitch classes
# --------------------------------------------------------------------------


def test_there_are_twelve_pitch_classes_in_order() -> None:
    assert len(PITCH_CLASSES) == 12
    assert PITCH_CLASSES[0] == "C"
    assert PITCH_CLASSES[C4 % 12] == "C"
    assert PITCH_CLASSES[(C4 + 7) % 12] == "G"


# --------------------------------------------------------------------------
# Scale content
# --------------------------------------------------------------------------


def test_ionian_intervals() -> None:
    assert scale_pitches(C4, "ionian", 1) == [60, 62, 64, 65, 67, 69, 71, 72]


def test_dorian_differs_from_ionian_at_third_and_seventh() -> None:
    ionian = scale_pitches(C4, "ionian", 1)
    dorian = scale_pitches(C4, "dorian", 1)
    assert dorian[2] == ionian[2] - 1
    assert dorian[6] == ionian[6] - 1
    # Every other degree is identical.
    for degree in (0, 1, 3, 4, 5, 7):
        assert dorian[degree] == ionian[degree]


def test_blues_has_six_notes_per_octave() -> None:
    assert len(scale_pitches(C4, "blues", 1)) == 7  # six, plus the octave


def test_blues_contains_the_flat_five() -> None:
    assert C4 + 6 in scale_pitches(C4, "blues", 1)


def test_phrygian_dominant_has_a_flat_second_and_major_third() -> None:
    """The harmonic-minor mode that does not fall out of the major scale."""
    pitches = scale_pitches(C4, "phrygian_dominant", 1)
    assert pitches[1] == C4 + 1
    assert pitches[2] == C4 + 4


def test_altered_scale_is_the_seventh_mode_of_melodic_minor() -> None:
    altered = scale_pitches(C4, "altered", 1)
    melodic = scale_pitches(C4 + 1, "melodic_minor", 1)
    assert {p % 12 for p in altered[:-1]} == {p % 12 for p in melodic[:-1]}


def test_whole_tone_steps_are_all_two_semitones() -> None:
    pitches = scale_pitches(C4, "whole_tone", 1)
    assert all(b - a == 2 for a, b in pairwise(pitches))


def test_diminished_scales_alternate_their_step_pattern() -> None:
    wh = scale_pitches(C4, "diminished_whole_half", 1)
    hw = scale_pitches(C4, "diminished_half_whole", 1)
    assert [b - a for a, b in pairwise(wh)] == [2, 1] * 4
    assert [b - a for a, b in pairwise(hw)] == [1, 2] * 4


def test_multiple_octaves_span_the_right_distance() -> None:
    for octaves in (1, 2, 3):
        pitches = scale_pitches(C4, "ionian", octaves)
        assert pitches[0] == C4
        assert pitches[-1] == C4 + 12 * octaves
        assert len(pitches) == 7 * octaves + 1


def test_unknown_scale_type_names_the_key_and_its_accepted_values() -> None:
    """Spec §13: never fall back, and name what was accepted."""
    with pytest.raises(KeyError) as exc:
        scale_pitches(C4, "dorain", 1)
    message = str(exc.value)
    assert "dorain" in message
    assert "dorian" in message


def test_octaves_below_one_is_rejected() -> None:
    with pytest.raises(ValueError, match="octaves"):
        scale_pitches(C4, "ionian", 0)


# --------------------------------------------------------------------------
# The exhaustive sweep (spec §14)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("root", range(C4, C4 + 12))
@pytest.mark.parametrize("scale_type", sorted(SCALES))
def test_every_scale_is_strictly_ascending_and_closes_the_octave(
    root: int, scale_type: str
) -> None:
    pitches = scale_pitches(root, scale_type, 2)
    assert pitches == sorted(pitches)
    assert len(set(pitches)) == len(pitches)
    assert pitches[0] == root
    assert pitches[-1] == root + 24


@pytest.mark.parametrize("scale_type", sorted(SCALES))
def test_no_scale_repeats_a_pitch_class_within_an_octave(scale_type: str) -> None:
    offsets = SCALES[scale_type]
    assert len(set(offsets)) == len(offsets)
    assert offsets[0] == 0
    assert all(0 <= o < 12 for o in offsets)
    assert list(offsets) == sorted(offsets)


def test_the_seven_modes_of_the_major_scale_share_its_pitch_classes() -> None:
    modes = (
        "ionian",
        "dorian",
        "phrygian",
        "lydian",
        "mixolydian",
        "aeolian",
        "locrian",
    )
    reference = {p % 12 for p in scale_pitches(C4, "ionian", 1)}
    for index, mode in enumerate(modes):
        root = C4 + SCALES["ionian"][index]
        assert {p % 12 for p in scale_pitches(root, mode, 1)} == reference


# --------------------------------------------------------------------------
# Chords
# --------------------------------------------------------------------------


def test_major_triad() -> None:
    assert chord_pitches(C4, "maj", 0) == [60, 64, 67]


def test_minor_triad_flattens_the_third() -> None:
    assert chord_pitches(C4, "min", 0) == [60, 63, 67]


def test_dominant_seventh() -> None:
    assert chord_pitches(C4, "dom7", 0) == [60, 64, 67, 70]


def test_major_seventh_differs_from_dominant_at_the_seventh() -> None:
    assert chord_pitches(C4, "maj7", 0)[3] == chord_pitches(C4, "dom7", 0)[3] + 1


def test_diminished_seventh_is_a_stack_of_minor_thirds() -> None:
    pitches = chord_pitches(C4, "dim7", 0)
    assert [b - a for a, b in pairwise(pitches)] == [3, 3, 3]


def test_first_inversion_moves_the_root_up_an_octave() -> None:
    assert chord_pitches(C4, "maj7", 1) == [64, 67, 71, 72]


def test_inversions_preserve_pitch_classes_and_stay_ascending() -> None:
    root_position = {p % 12 for p in chord_pitches(C4, "maj7", 0)}
    for inversion in range(4):
        pitches = chord_pitches(C4, "maj7", inversion)
        assert {p % 12 for p in pitches} == root_position
        assert pitches == sorted(pitches)


def test_inversion_beyond_the_chord_tone_count_is_rejected() -> None:
    """A triad has no third inversion; wrapping silently would be a bug."""
    with pytest.raises(ValueError, match="inversion"):
        chord_pitches(C4, "maj", 3)


def test_unknown_chord_quality_names_the_key_and_its_accepted_values() -> None:
    with pytest.raises(KeyError) as exc:
        chord_pitches(C4, "maj9", 0)
    message = str(exc.value)
    assert "maj9" in message
    assert "maj7" in message


@pytest.mark.parametrize("root", range(C4, C4 + 12))
@pytest.mark.parametrize("quality", sorted(CHORDS))
def test_every_chord_at_every_root_is_ascending_and_correctly_sized(
    root: int, quality: str
) -> None:
    for inversion in range(len(CHORDS[quality])):
        pitches = chord_pitches(root, quality, inversion)
        assert len(pitches) == len(CHORDS[quality])
        assert pitches == sorted(pitches)
        assert len({p % 12 for p in pitches}) == len(CHORDS[quality])
