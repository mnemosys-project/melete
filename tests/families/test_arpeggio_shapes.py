import pytest

from melete import theory
from melete.families import arpeggio_shapes as shapes
from melete.instrument import PROFILES

BASS6 = PROFILES["bass6"]


def test_every_quality_the_pool_drills_has_a_seed():
    for quality in ("maj7", "min7", "dom7", "m7b5", "min6"):
        assert quality in shapes.SEED_SHAPES


def test_min7_shape_preserves_pitch_and_climbs_to_the_top_string():
    root = BASS6.tuning[0] + 10  # a low-string root
    tones = theory.chord_pitches(root, "min7")
    tones = tones + [t + 12 for t in tones] + [tones[0] + 24]  # two octaves + close
    places = shapes.shape_places(BASS6, (0, 10), "min7", tones)
    assert places[0][0] == 0  # starts low string
    assert max(s for s, _f in places) == len(BASS6.tuning) - 1  # uses the top string
    for pitch, (s, f) in zip(tones, places, strict=True):
        assert BASS6.tuning[s] + f == pitch


def test_off_neck_tone_raises():
    with pytest.raises(ValueError, match="arpeggios"):
        shapes.shape_places(BASS6, (5, 23), "maj7", [200])


def test_tone_off_the_top_string_raises():
    # A maj7 anchored on the top string climbs its third to a string that does
    # not exist. The shape is derived, never clamped, so this raises (spec §10).
    top = len(BASS6.tuning) - 1
    root = BASS6.tuning[top]
    tones = theory.chord_pitches(root, "maj7")  # root fits; third needs string+1
    with pytest.raises(ValueError, match="arpeggios"):
        shapes.shape_places(BASS6, (top, 0), "maj7", tones)


def test_unknown_quality_raises():
    with pytest.raises(ValueError, match="no seed shape"):
        shapes.shape_places(BASS6, (0, 0), "sus4", [BASS6.tuning[0]])
