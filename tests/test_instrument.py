"""Tests for instrument profiles and fretboard queries.

Spec §14 calls for exhaustive coverage here: every pitch maps to valid positions
on every profile. `instrument` sits under every family, so a defect here is a
wrong string or fret on every printed exercise at once.

The central invariant of §14 — `note.pitch == tuning[note.string] + note.fret` —
is the contract these two functions define. Every family test asserts it later;
this module is where it is proved for the fretboard itself.
"""

from __future__ import annotations

from itertools import pairwise

import pytest

from melete.instrument import (
    DEFAULT_PROFILE,
    PROFILES,
    InstrumentProfile,
    pitch_at,
    positions,
    resolve_profile,
)

# C4 = 60 throughout, per the Score IR.
C4 = 60
C3 = 48


def _every_position(profile: InstrumentProfile) -> list[tuple[int, int]]:
    """Every playable (string, fret) on a profile, open strings included."""
    return [
        (string, fret)
        for string in range(len(profile.tuning))
        for fret in range(profile.fret_count + 1)
    ]


# --------------------------------------------------------------------------
# The built-in profiles
# --------------------------------------------------------------------------


def test_fret_counts_are_declared_not_inferred() -> None:
    """Decision #18: fret count determines validity, therefore the draw."""
    assert PROFILES["bass4"].fret_count == 20
    assert PROFILES["bass5"].fret_count == 24
    assert PROFILES["bass6"].fret_count == 24


def test_bass4_is_standard_four_string_tuning() -> None:
    """E1 A1 D2 G2, with C4 = 60."""
    assert PROFILES["bass4"].tuning == (28, 33, 38, 43)


def test_bass5_adds_a_low_b_below_the_four_string_tuning() -> None:
    assert PROFILES["bass5"].tuning == (23, *PROFILES["bass4"].tuning)


def test_bass6_adds_a_high_c_above_the_five_string_tuning() -> None:
    assert PROFILES["bass6"].tuning == (*PROFILES["bass5"].tuning, C3)


def test_bass6_is_six_strings_low_to_high() -> None:
    tuning = PROFILES["bass6"].tuning
    assert len(tuning) == 6
    assert tuning == tuple(sorted(tuning))


@pytest.mark.parametrize("name", sorted(PROFILES))
def test_every_profile_knows_its_own_name(name: str) -> None:
    """The registry key and the profile's `name` must not drift apart."""
    assert PROFILES[name].name == name


@pytest.mark.parametrize("name", sorted(PROFILES))
def test_every_tuning_is_strictly_ascending_low_to_high(name: str) -> None:
    """Spec §5: index 0 is the lowest string and every family depends on it."""
    tuning = PROFILES[name].tuning
    assert all(higher > lower for lower, higher in pairwise(tuning))


def test_the_default_profile_is_bass6() -> None:
    assert DEFAULT_PROFILE == "bass6"
    assert DEFAULT_PROFILE in PROFILES


# --------------------------------------------------------------------------
# Profile lookup (spec §13: never fall back for a misspelled key)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(PROFILES))
def test_resolve_profile_returns_the_registered_profile(name: str) -> None:
    assert resolve_profile(name) is PROFILES[name]


def test_unknown_profile_names_the_key_and_its_accepted_values() -> None:
    with pytest.raises(KeyError) as exc:
        resolve_profile("bass7")
    message = str(exc.value)
    assert "bass7" in message
    assert "bass6" in message


# --------------------------------------------------------------------------
# Profile construction is validated
# --------------------------------------------------------------------------


def test_explicit_profiles_are_accepted() -> None:
    """The drop-D example from spec §10."""
    drop_d = InstrumentProfile("drop_d", (26, 33, 38, 43), 20)
    assert drop_d.tuning[0] == 26
    assert pitch_at(drop_d, 0, 0) == 26


def test_a_non_ascending_tuning_is_rejected_naming_the_offending_index() -> None:
    """Decision #22: re-sorting would engrave the wrong instrument convincingly."""
    with pytest.raises(ValueError, match="index 1") as exc:
        InstrumentProfile("bad", (33, 26, 38), 20)
    assert "ascending" in str(exc.value)


def test_a_repeated_pitch_in_a_tuning_is_rejected() -> None:
    """Strictly ascending, not merely non-descending."""
    with pytest.raises(ValueError, match="index 1"):
        InstrumentProfile("bad", (33, 33, 38), 20)


def test_an_empty_tuning_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one string"):
        InstrumentProfile("bad", (), 20)


def test_a_profile_without_frets_is_rejected() -> None:
    with pytest.raises(ValueError, match="fret_count"):
        InstrumentProfile("bad", (28, 33), 0)


# --------------------------------------------------------------------------
# pitch_at
# --------------------------------------------------------------------------


def test_open_string_pitch() -> None:
    profile = PROFILES["bass4"]
    assert pitch_at(profile, 0, 0) == profile.tuning[0]


def test_the_twelfth_fret_is_an_octave_above_the_open_string() -> None:
    profile = PROFILES["bass6"]
    for string in range(len(profile.tuning)):
        assert pitch_at(profile, string, 12) == pitch_at(profile, string, 0) + 12


def test_the_highest_fret_is_playable() -> None:
    profile = PROFILES["bass4"]
    assert pitch_at(profile, 3, profile.fret_count) == profile.tuning[3] + profile.fret_count


def test_a_string_index_above_the_range_is_rejected() -> None:
    """Spec §13: a note off the fretboard is a bug in a family, so raise."""
    with pytest.raises(ValueError, match="string 4"):
        pitch_at(PROFILES["bass4"], 4, 0)


def test_a_negative_string_index_is_rejected_rather_than_wrapping() -> None:
    """Python would silently index from the top string; that is a wrong sheet."""
    with pytest.raises(ValueError, match="string -1"):
        pitch_at(PROFILES["bass4"], -1, 0)


def test_a_fret_above_the_fret_count_is_rejected() -> None:
    profile = PROFILES["bass4"]
    with pytest.raises(ValueError, match="fret 21"):
        pitch_at(profile, 0, profile.fret_count + 1)


def test_a_negative_fret_is_rejected() -> None:
    with pytest.raises(ValueError, match="fret -1"):
        pitch_at(PROFILES["bass4"], 0, -1)


# --------------------------------------------------------------------------
# positions
# --------------------------------------------------------------------------


def test_positions_are_all_valid() -> None:
    profile = PROFILES["bass6"]
    found = positions(profile, C3)
    assert found
    for string, fret in found:
        assert 0 <= fret <= profile.fret_count
        assert pitch_at(profile, string, fret) == C3


def test_positions_include_the_open_string_that_sounds_the_pitch() -> None:
    profile = PROFILES["bass6"]
    assert (5, 0) in positions(profile, profile.tuning[5])


def test_positions_are_ordered_from_the_lowest_string_upward() -> None:
    profile = PROFILES["bass6"]
    found = positions(profile, C4)
    assert [string for string, _ in found] == sorted(string for string, _ in found)


def test_a_pitch_below_the_lowest_open_string_has_no_positions() -> None:
    profile = PROFILES["bass6"]
    assert positions(profile, profile.tuning[0] - 1) == []


def test_a_pitch_above_the_highest_fret_has_no_positions() -> None:
    profile = PROFILES["bass6"]
    assert positions(profile, profile.tuning[-1] + profile.fret_count + 1) == []


def test_bass4_cannot_reach_the_low_b_that_bass5_can() -> None:
    """The profile is what makes a specification valid or invalid (spec §5)."""
    low_b = PROFILES["bass5"].tuning[0]
    assert positions(PROFILES["bass4"], low_b) == []
    assert positions(PROFILES["bass5"], low_b) == [(0, 0)]


# --------------------------------------------------------------------------
# The exhaustive sweep (spec §14)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(PROFILES))
def test_every_reachable_pitch_round_trips(name: str) -> None:
    """Every pitch from the lowest open string to the highest fretted note."""
    profile = PROFILES[name]
    lowest = profile.tuning[0]
    highest = profile.tuning[-1] + profile.fret_count
    for pitch in range(lowest, highest + 1):
        found = positions(profile, pitch)
        assert found, f"{name} cannot play pitch {pitch} inside its own range"
        for string, fret in found:
            assert pitch_at(profile, string, fret) == pitch


@pytest.mark.parametrize("name", sorted(PROFILES))
def test_every_playable_position_is_reported_by_positions(name: str) -> None:
    """The dual sweep: positions() omits nothing the fretboard can sound."""
    profile = PROFILES[name]
    for string, fret in _every_position(profile):
        assert (string, fret) in positions(profile, pitch_at(profile, string, fret))


@pytest.mark.parametrize("name", sorted(PROFILES))
def test_positions_reports_nothing_the_fretboard_cannot_sound(name: str) -> None:
    profile = PROFILES[name]
    playable = set(_every_position(profile))
    lowest = profile.tuning[0]
    highest = profile.tuning[-1] + profile.fret_count
    for pitch in range(lowest - 12, highest + 13):
        assert set(positions(profile, pitch)) <= playable
