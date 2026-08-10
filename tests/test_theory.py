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
    IMPLIED_PARENT,
    PITCH_CLASSES,
    SCALES,
    Key,
    SpelledPitch,
    chord_pitches,
    parent_scale,
    scale_pitches,
    spell,
    tier,
    tonic_spelling,
)

# C4 = 60 throughout, per the Score IR.
C4 = 60

# The pitch class each letter names unaltered. Duplicated here on purpose: a
# test that imported the implementation's own table could not catch it being
# wrong.
NATURALS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

DIATONIC_MODES = (
    "ionian",
    "dorian",
    "phrygian",
    "lydian",
    "mixolydian",
    "aeolian",
    "locrian",
)


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


# --------------------------------------------------------------------------
# Tiers, parents and the chord mapping (spec §10a)
# --------------------------------------------------------------------------


def test_the_seven_diatonic_modes_are_tier_1() -> None:
    for mode in DIATONIC_MODES:
        assert tier(mode) == 1
        assert parent_scale(mode) is None


def test_minor_family_scales_are_tier_2_with_a_parent() -> None:
    assert tier("melodic_minor") == 2
    assert parent_scale("melodic_minor") == "aeolian"
    assert tier("harmonic_minor") == 2
    assert parent_scale("blues") == "aeolian"
    assert parent_scale("major_pentatonic") == "ionian"


def test_symmetric_scales_are_tier_3_and_parentless() -> None:
    for name in ("whole_tone", "diminished_whole_half", "diminished_half_whole"):
        assert tier(name) == 3
        assert parent_scale(name) is None


def test_every_scale_type_has_a_tier() -> None:
    """A scale added to SCALES without a tier is a silent spelling bug."""
    for name in SCALES:
        assert tier(name) in (1, 2, 3)


def test_every_tier_2_scale_has_a_parent_and_no_other_scale_does() -> None:
    for name in SCALES:
        assert (parent_scale(name) is not None) == (tier(name) == 2)


def test_every_chord_quality_maps_to_a_real_scale() -> None:
    assert set(IMPLIED_PARENT) == set(CHORDS)
    assert all(parent in SCALES for parent in IMPLIED_PARENT.values())
    assert IMPLIED_PARENT["maj7"] == "ionian"
    assert IMPLIED_PARENT["m7b5"] == "locrian"


def test_unknown_scale_type_names_accepted_values() -> None:
    for call in (tier, parent_scale):
        with pytest.raises(KeyError) as exc:
            call("dorain")
        assert "dorain" in str(exc.value)
        assert "dorian" in str(exc.value)


# --------------------------------------------------------------------------
# Spelling (spec §10a)
# --------------------------------------------------------------------------


def written(spelled: SpelledPitch) -> str:
    """`SpelledPitch` as an ASCII note name: alteration is semitones, not glyphs."""
    if spelled.alteration > 0:
        return spelled.letter + "#" * spelled.alteration
    return spelled.letter + "b" * -spelled.alteration


def letters(key: Key, octaves: int = 1) -> str:
    """The scale's degrees, without the closing octave."""
    pitches = scale_pitches(C4 + key.tonic, key.scale_type, octaves)
    return " ".join(written(p) for p in spell(key, pitches[:-1]))


def test_spelled_pitch_is_notation_neutral() -> None:
    """No LilyPond, no Unicode: `letter`, semitones and an octave number."""
    spelled = SpelledPitch(letter="F", alteration=1, octave=4)
    assert (spelled.letter, spelled.alteration, spelled.octave) == ("F", 1, 4)


def test_f_sharp_dorian_is_spelled_with_sharps() -> None:
    """The original defect: this engraved as Gb Ab Bbb Cb Db Ebb Fb."""
    assert letters(Key(6, "dorian")) == "F# G# A B C# D# E"


def test_the_tonic_letter_minimises_signature_accidentals() -> None:
    assert tonic_spelling(Key(6, "dorian")) == ("F", 1)  # F#, 4 sharps
    assert tonic_spelling(Key(1, "ionian")) == ("D", -1)  # Db, 5 flats


def test_a_tie_on_accidental_count_breaks_toward_flats() -> None:
    """Gb major and F# major are both six accidentals; the rule must not coin-flip."""
    assert tonic_spelling(Key(6, "ionian")) == ("G", -1)
    assert letters(Key(6, "ionian")) == "Gb Ab Bb Cb Db Eb F"


def test_a_diatonic_scale_uses_each_letter_once() -> None:
    for tonic in range(12):
        for mode in DIATONIC_MODES:
            names = letters(Key(tonic, mode)).split()
            assert len({n[0] for n in names}) == 7


def test_spelling_always_sounds_the_right_pitch() -> None:
    """The central invariant's analogue. This is the assertion that matters."""
    for tonic in range(12):
        for scale_type in SCALES:
            pitches = scale_pitches(C4 + tonic, scale_type, 1)
            spelled = spell(Key(tonic, scale_type), pitches)
            for pitch, note in zip(pitches, spelled, strict=True):
                assert (NATURALS[note.letter] + note.alteration) % 12 == pitch % 12


def test_the_octave_number_follows_the_letter_not_the_pitch() -> None:
    """Cb5 sounds B4 and B#4 sounds C5; the written octave is the letter's."""
    for tonic in range(12):
        for scale_type in SCALES:
            pitches = scale_pitches(C4 + tonic, scale_type, 2)
            spelled = spell(Key(tonic, scale_type), pitches)
            for pitch, note in zip(pitches, spelled, strict=True):
                natural = (note.octave + 1) * 12 + NATURALS[note.letter]
                assert natural + note.alteration == pitch


def test_a_flat_tonic_can_carry_the_scale_across_an_octave_line() -> None:
    """Gb major's fourth degree is Cb5 — written a letter above the B4 it sounds."""
    pitches = scale_pitches(C4 + 6, "ionian", 1)
    spelled = spell(Key(6, "ionian"), pitches)
    assert spelled[3] == SpelledPitch(letter="C", alteration=-1, octave=5)
    assert pitches[3] == 71  # B4


def test_a_sharp_seventh_can_carry_the_scale_across_an_octave_line() -> None:
    """C# harmonic minor's leading tone is B#4 — written below the C5 it sounds."""
    pitches = scale_pitches(C4 + 1, "harmonic_minor", 1)
    spelled = spell(Key(1, "harmonic_minor"), pitches)
    assert spelled[6] == SpelledPitch(letter="B", alteration=1, octave=4)
    assert pitches[6] == 72  # C5


def test_no_key_signature_needs_a_double_accidental() -> None:
    for tonic in range(12):
        for scale_type in SCALES:
            _, alteration = tonic_spelling(Key(tonic, scale_type))
            assert abs(alteration) <= 1


def test_no_spelling_needs_more_than_a_double_accidental() -> None:
    for tonic in range(12):
        for scale_type in SCALES:
            pitches = scale_pitches(C4 + tonic, scale_type, 1)
            for note in spell(Key(tonic, scale_type), pitches):
                assert abs(note.alteration) <= 2


def test_a_tier_2_scale_shares_its_parents_tonic_letter() -> None:
    """The signature printed is the parent's, so the tonic must be the parent's."""
    for tonic in range(12):
        for scale_type in SCALES:
            parent = parent_scale(scale_type)
            if parent is not None:
                assert tonic_spelling(Key(tonic, scale_type)) == tonic_spelling(Key(tonic, parent))


def test_melodic_and_harmonic_minor_keep_seven_letters() -> None:
    """Tier 2 still has seven degrees, so the letter rule still holds."""
    assert letters(Key(0, "melodic_minor")) == "C D Eb F G A B"
    assert letters(Key(0, "harmonic_minor")) == "C D Eb F G Ab B"
    assert letters(Key(6, "harmonic_minor")) == "F# G# A B C# D E#"


def test_pentatonics_are_spelled_as_their_parent_spells_them() -> None:
    assert letters(Key(0, "major_pentatonic")) == "C D E G A"
    assert letters(Key(0, "minor_pentatonic")) == "C Eb F G Bb"
    assert letters(Key(6, "minor_pentatonic")) == "F# A B C# E"


def test_the_blue_note_is_a_flat_five() -> None:
    """Blues is a subset of natural minor plus one tone the parent does not name."""
    assert letters(Key(0, "blues")) == "C Eb F Gb G Bb"
    assert letters(Key(4, "blues")) == "E G A Bb B D"
    assert letters(Key(9, "blues")) == "A C D Eb E G"


def test_symmetric_scales_spell_by_direction() -> None:
    pitches = scale_pitches(C4, "whole_tone", 1)
    ascending = spell(Key(0, "whole_tone"), pitches)
    descending = spell(Key(0, "whole_tone"), pitches, descending=True)
    assert any(p.alteration > 0 for p in ascending)
    assert any(p.alteration < 0 for p in descending)
    assert " ".join(written(p) for p in ascending) == "C D E F# G# A# C"
    assert " ".join(written(p) for p in descending) == "C D E Gb Ab Bb C"


def test_a_symmetric_scale_has_no_signature_to_minimise() -> None:
    """With no parent and no signature, the tonic follows the ascending rule."""
    assert tonic_spelling(Key(6, "whole_tone")) == ("F", 1)
    assert tonic_spelling(Key(0, "diminished_whole_half")) == ("C", 0)


def test_no_key_spells_chromatically_by_direction() -> None:
    up = spell(None, [60, 61, 62])
    assert (up[1].letter, up[1].alteration) == ("C", 1)  # C#
    down = spell(None, [62, 61, 60], descending=True)
    assert (down[1].letter, down[1].alteration) == ("D", -1)  # Db


def test_a_key_spells_the_same_in_both_directions() -> None:
    """Direction is tier 3's only signal; a key overrides it."""
    pitches = scale_pitches(C4 + 6, "dorian", 1)
    key = Key(6, "dorian")
    assert spell(key, pitches) == spell(key, pitches, descending=True)


def test_a_scale_no_letter_sequence_can_spell_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guessing a spelling would be worse than refusing to produce one."""
    monkeypatch.setitem(SCALES, "impossible", (0, 1, 2, 3, 4, 5, 6))
    with pytest.raises(ValueError, match="impossible"):
        tonic_spelling(Key(0, "impossible"))


# --------------------------------------------------------------------------
# Chords spell through their implied parent (spec §10a, Arpeggios)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("root", range(12))
@pytest.mark.parametrize("quality", sorted(CHORDS))
def test_every_chord_tone_sounds_the_pitch_it_names(root: int, quality: str) -> None:
    pitches = chord_pitches(C4 + root, quality)
    key = Key(root, IMPLIED_PARENT[quality])
    for pitch, note in zip(pitches, spell(key, pitches), strict=True):
        assert (NATURALS[note.letter] + note.alteration) % 12 == pitch % 12


def chord_letters(root: int, quality: str) -> str:
    pitches = chord_pitches(C4 + root, quality)
    return " ".join(written(p) for p in spell(Key(root, IMPLIED_PARENT[quality]), pitches))


def test_chord_tones_take_the_letters_of_their_degrees() -> None:
    assert chord_letters(0, "maj7") == "C E G B"
    assert chord_letters(0, "min7") == "C Eb G Bb"
    assert chord_letters(0, "m7b5") == "C Eb Gb Bb"
    assert chord_letters(0, "dom7") == "C E G Bb"


def test_the_added_sixth_and_the_major_seventh_of_a_minor_chord_are_not_borrowed() -> None:
    """min6 and min_maj7 are not subsets of aeolian, so they imply another parent."""
    assert chord_letters(0, "min6") == "C Eb G A"
    assert chord_letters(0, "min_maj7") == "C Eb G B"
    assert chord_letters(6, "min6") == "F# A C# D#"
    assert chord_letters(6, "min_maj7") == "F# A C# E#"
