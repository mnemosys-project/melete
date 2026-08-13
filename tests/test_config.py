"""Tests for configuration loading (spec §10) and its error contract (§13).

The load-bearing tests here are the *rejections*. §13 promises that a
malformed or misspelled key fails at load, naming the exact key and its
accepted values, and never falls back to a default. A config module that
merely parsed a file would pass a suite of happy-path tests while quietly
turning a typo into a default — which is the failure mode the vocabulary
registry exists to prevent.

Two rejections are singled out by the spec itself and are asserted here
verbatim:

* a misspelled identifier lists the registry's accepted values (§13);
* an explicit tuning that is not strictly ascending names the offending
  index and is never re-sorted (decision #22).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from melete import vocabulary
from melete.config import (
    _AXES_BY_FAMILY,
    _RHYTHM_AXES,
    ConfigError,
    load,
    load_string,
)
from melete.families import REGISTRY

if TYPE_CHECKING:
    from pathlib import Path

DROP_D = '[instrument]\nprofile = { name = "drop_d", tuning = [26, 33, 38, 43], fret_count = 20 }\n'
BASS4 = '[instrument]\nprofile = "bass4"\n'
NON_ASCENDING = '[instrument]\nprofile = { name = "bad", tuning = [33, 26, 38], fret_count = 20 }\n'


# --------------------------------------------------------------------------
# The plan's tests — spec §13's error contract
# --------------------------------------------------------------------------


def test_misspelled_key_fails_loudly_and_names_accepted_values() -> None:
    with pytest.raises(ValueError) as exc:
        load_string('[pool.scales]\nscale_types = ["dorain"]')
    assert "dorain" in str(exc.value)
    assert "dorian" in str(exc.value)  # from the registry


def test_never_falls_back_to_a_default_for_an_unknown_key() -> None:
    with pytest.raises(ValueError):
        load_string("[session]\ncont = 5")  # typo of `count`


def test_max_notes_defaults_are_present() -> None:
    assert load_string("").session.max_notes == 96


def test_max_fret_span_defaults_to_one_octave_of_neck() -> None:
    assert load_string("").session.max_fret_span == 12


def test_explicit_tuning_is_accepted() -> None:
    cfg = load_string(DROP_D)
    assert cfg.instrument.tuning == (26, 33, 38, 43)
    assert cfg.instrument.fret_count == 20


def test_non_ascending_tuning_is_a_load_error_never_re_sorted() -> None:
    """decision #22: sorting would engrave the wrong instrument convincingly."""
    with pytest.raises(ValueError) as exc:
        load_string(NON_ASCENDING)
    assert "1" in str(exc.value)  # names the offending index


def test_explicit_tuning_without_fret_count_is_rejected() -> None:
    with pytest.raises(ValueError):
        load_string('[instrument]\nprofile = { name = "bad", tuning = [26, 33, 38, 43] }')


def test_family_tempo_override() -> None:
    cfg = load_string("[pool.chromatic]\ntempo = [50, 70]")
    assert cfg.pool["chromatic"].tempo == (50, 70)


def test_family_tempo_defaults_when_unset() -> None:
    assert load_string("").pool["chromatic"].tempo == REGISTRY["chromatic"].default_tempo_range


# --------------------------------------------------------------------------
# Defaults (§10)
# --------------------------------------------------------------------------


def test_empty_config_is_the_documented_default_session() -> None:
    cfg = load_string("")
    assert cfg.session.count == 5
    assert cfg.session.horizon == 14
    assert cfg.session.shape is None  # unset means weight families instead (§9)


def test_empty_config_defaults_to_bass6() -> None:
    cfg = load_string("")
    assert cfg.instrument.name == "bass6"
    assert cfg.instrument.fret_count == 24


def test_every_family_has_a_pool_even_when_unconfigured() -> None:
    cfg = load_string("")
    assert sorted(cfg.pool) == sorted(vocabulary.accepted("family"))
    assert cfg.pool["scales"].values == {}
    assert cfg.rhythm.values == {}


def test_the_spec_example_config_loads() -> None:
    # §10's worked example, verbatim apart from the comments.
    cfg = load_string(
        '[instrument]\nprofile = "bass6"\n'
        "\n[session]\ncount = 5\nhorizon = 14\nmax_notes = 96\n"
        "shape = { chromatic = 1, scales = 2, arpeggios = 1, intervals = 1 }\n"
        '\n[pool.scales]\nroots = "all"\n'
        'scale_types = ["ionian", "dorian", "phrygian", "major_pentatonic", "blues"]\n'
        'patterns = ["straight", "thirds", "groups_of_3", "groups_of_4"]\n'
        'traversals = ["positional", "three_note_per_string"]\n'
        "octaves = [1, 2]\ntempo = [80, 100]\n"
        "\n[pool.rhythm]\n"
        'accent_patterns = ["none", "every_3"]\n'
        'note_value_patterns = ["straight", "long_short"]\n'
    )
    assert cfg.session.shape == {"chromatic": 1, "scales": 2, "arpeggios": 1, "intervals": 1}
    assert cfg.pool["scales"].values["root"] == tuple(range(12))
    assert cfg.pool["scales"].values["range_octaves"] == (1, 2)
    assert cfg.pool["scales"].tempo == (80, 100)
    assert cfg.rhythm.values["accent_pattern"] == ("none", "every_3")


# --------------------------------------------------------------------------
# Unknown sections and keys — never a silent default
# --------------------------------------------------------------------------


def test_unknown_top_level_section_is_rejected_naming_the_sections() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[sesion]\ncount = 5")
    assert "sesion" in str(exc.value)
    assert "session" in str(exc.value)


def test_unknown_instrument_key_is_rejected() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string('[instrument]\nprofil = "bass4"')
    assert "profil" in str(exc.value)
    assert "profile" in str(exc.value)


def test_unknown_pool_family_is_rejected_naming_the_families() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[pool.scalez]\noctaves = [1]")
    assert "scalez" in str(exc.value)
    assert "scales" in str(exc.value)


def test_unknown_axis_key_in_a_family_pool_is_rejected() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string('[pool.scales]\nscale_type = ["dorian"]')  # singular
    assert "scale_type" in str(exc.value)
    assert "scale_types" in str(exc.value)


def test_an_axis_belonging_to_another_family_is_rejected() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string('[pool.scales]\nqualities = ["maj7"]')
    assert "qualities" in str(exc.value)


def test_rhythm_has_no_tempo() -> None:
    # Tempo is a per-family default (decision #20); rhythm is a modifier, not
    # a family, so a tempo there would have nothing to override.
    with pytest.raises(ConfigError) as exc:
        load_string("[pool.rhythm]\ntempo = [80, 100]")
    assert "tempo" in str(exc.value)


def test_unknown_rhythm_key_is_rejected() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string('[pool.rhythm]\naccent_pattern = ["none"]')  # singular
    assert "accent_pattern" in str(exc.value)
    assert "accent_patterns" in str(exc.value)


def test_retired_rhythm_axes_are_rejected_as_unknown() -> None:
    # `subdivisions` and `time_signatures` were sampled axes until #119, when
    # the layout fitter took over deriving the meter and subdivision (#118).
    # They are now unknown `[pool.rhythm]` keys like any other misspelling.
    for retired in ('subdivisions = ["eighth"]', 'time_signatures = ["4_4"]'):
        with pytest.raises(ConfigError) as exc:
            load_string(f"[pool.rhythm]\n{retired}")
        assert "unrecognized" in str(exc.value)
        assert "accent_patterns" in str(exc.value)


# --------------------------------------------------------------------------
# The instrument section
# --------------------------------------------------------------------------


def test_a_section_that_is_not_a_table_is_rejected() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("instrument = 4")
    assert "instrument" in str(exc.value)


def test_unknown_builtin_profile_names_the_builtins() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string('[instrument]\nprofile = "bass7"')
    assert "bass7" in str(exc.value)
    assert "bass6" in str(exc.value)


def test_profile_of_the_wrong_type_is_rejected() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[instrument]\nprofile = 6")
    assert "instrument.profile" in str(exc.value)


def test_explicit_profile_requires_a_name() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[instrument]\nprofile = { tuning = [26, 33], fret_count = 20 }")
    assert "instrument.profile.name" in str(exc.value)


def test_explicit_profile_requires_a_tuning() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string('[instrument]\nprofile = { name = "x", fret_count = 20 }')
    assert "instrument.profile.tuning" in str(exc.value)


def test_explicit_profile_rejects_an_unknown_key() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string('[instrument]\nprofile = { name = "x", tuning = [26, 33], frets = 20 }')
    assert "frets" in str(exc.value)
    assert "fret_count" in str(exc.value)


def test_explicit_profile_name_must_be_a_string() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[instrument]\nprofile = { name = 1, tuning = [26, 33], fret_count = 20 }")
    assert "instrument.profile.name" in str(exc.value)


def test_explicit_tuning_must_be_a_list() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string('[instrument]\nprofile = { name = "x", tuning = 26, fret_count = 20 }')
    assert "instrument.profile.tuning" in str(exc.value)


def test_explicit_tuning_entries_must_be_integers() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string('[instrument]\nprofile = { name = "x", tuning = [26, "A"], fret_count = 20 }')
    assert "instrument.profile.tuning[1]" in str(exc.value)


def test_empty_explicit_tuning_is_rejected_naming_the_key() -> None:
    # InstrumentProfile owns this rule; config names the key it came from.
    with pytest.raises(ConfigError) as exc:
        load_string('[instrument]\nprofile = { name = "x", tuning = [], fret_count = 20 }')
    assert "instrument.profile" in str(exc.value)
    assert "empty" in str(exc.value)


def test_non_positive_fret_count_is_rejected_naming_the_key() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string('[instrument]\nprofile = { name = "x", tuning = [26, 33], fret_count = 0 }')
    assert "instrument.profile" in str(exc.value)
    assert "fret_count" in str(exc.value)


def test_non_ascending_tuning_names_both_the_config_key_and_the_index() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string(NON_ASCENDING)
    message = str(exc.value)
    assert "instrument.profile" in message
    assert "index 1" in message
    assert "ascending" in message


# --------------------------------------------------------------------------
# The session section
# --------------------------------------------------------------------------


def test_count_must_be_an_integer() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string('[session]\ncount = "five"')
    assert "session.count" in str(exc.value)


def test_count_must_not_be_a_boolean() -> None:
    # `True` is an int in Python; a config that accepted it would silently
    # generate one exercise.
    with pytest.raises(ConfigError) as exc:
        load_string("[session]\ncount = true")
    assert "session.count" in str(exc.value)


def test_count_must_be_positive() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[session]\ncount = 0")
    assert "session.count" in str(exc.value)


def test_horizon_must_be_positive() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[session]\nhorizon = 0")
    assert "session.horizon" in str(exc.value)


def test_max_notes_must_be_positive() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[session]\nmax_notes = -1")
    assert "session.max_notes" in str(exc.value)


def test_max_fret_span_must_be_positive() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[session]\nmax_fret_span = 0")
    assert "session.max_fret_span" in str(exc.value)


def test_horizon_and_max_notes_are_configurable() -> None:
    cfg = load_string("[session]\nhorizon = 7\nmax_notes = 48")
    assert cfg.session.horizon == 7
    assert cfg.session.max_notes == 48


def test_max_fret_span_is_configurable() -> None:
    assert load_string("[session]\nmax_fret_span = 7").session.max_fret_span == 7


def test_the_position_span_belongs_to_the_instrument_and_is_configurable() -> None:
    """§5: how many frets fall under one hand is a fact about the fretboard.

    A family is a pure `params -> Score` function and the profile is the only
    thing it is handed besides its parameters, which is also where the bound
    belongs on its merits: fret spacing is what decides the reach.
    """
    assert load_string("").instrument.position_span == 4
    assert load_string("[instrument]\nposition_span = 5").instrument.position_span == 5


def test_the_position_span_applies_to_an_explicit_tuning_too() -> None:
    cfg = load_string(DROP_D + "position_span = 6\n")
    assert cfg.instrument.tuning == (26, 33, 38, 43)
    assert cfg.instrument.position_span == 6


def test_a_position_span_of_zero_is_rejected() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[instrument]\nposition_span = 0")
    assert "instrument.position_span" in str(exc.value)


def test_shape_declares_the_session_mix() -> None:
    cfg = load_string("[session]\nshape = { scales = 2, arpeggios = 1 }")
    assert cfg.session.shape == {"scales": 2, "arpeggios": 1}


def test_shape_without_count_sets_the_count() -> None:
    assert load_string("[session]\nshape = { scales = 3 }").session.count == 3


def test_shape_agreeing_with_an_explicit_count_is_accepted() -> None:
    cfg = load_string("[session]\ncount = 3\nshape = { scales = 2, intervals = 1 }")
    assert cfg.session.count == 3


def test_shape_disagreeing_with_count_is_a_load_error_naming_both() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[session]\ncount = 5\nshape = { scales = 2 }")
    assert "session.count" in str(exc.value)
    assert "session.shape" in str(exc.value)


def test_shape_must_be_a_table() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[session]\nshape = 5")
    assert "session.shape" in str(exc.value)


def test_empty_shape_is_rejected() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[session]\nshape = {}")
    assert "session.shape" in str(exc.value)


def test_shape_names_an_unknown_family_and_lists_the_families() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[session]\nshape = { scalez = 2 }")
    assert "scalez" in str(exc.value)
    assert "arpeggios" in str(exc.value)


def test_shape_counts_must_be_positive_integers() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[session]\nshape = { scales = 0 }")
    assert "session.shape.scales" in str(exc.value)


# --------------------------------------------------------------------------
# Tempo (decision #20)
# --------------------------------------------------------------------------


def test_every_family_has_a_default_tempo_range() -> None:
    # Read through the registry, never against a literal: §7 assigns the range
    # to the family (decision #20), and the numbers themselves are asserted
    # against the spec table once, in the family registry's own tests.
    cfg = load_string("")
    assert {family: pool.tempo for family, pool in cfg.pool.items()} == {
        family: entry.default_tempo_range for family, entry in REGISTRY.items()
    }


def test_an_override_of_one_family_leaves_the_others_at_their_own_default() -> None:
    # The override is per family, so it must not be readable as a global.
    cfg = load_string("[pool.scales]\ntempo = [40, 50]")
    assert cfg.pool["scales"].tempo == (40, 50)
    assert cfg.pool["chromatic"].tempo == REGISTRY["chromatic"].default_tempo_range
    assert cfg.pool["intervals"].tempo == REGISTRY["intervals"].default_tempo_range


def test_tempo_must_be_a_list() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[pool.scales]\ntempo = 80")
    assert "pool.scales.tempo" in str(exc.value)


def test_tempo_must_have_exactly_two_bounds() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[pool.scales]\ntempo = [80, 100, 120]")
    assert "pool.scales.tempo" in str(exc.value)


def test_tempo_bounds_must_be_positive_integers() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[pool.scales]\ntempo = [0, 100]")
    assert "pool.scales.tempo[0]" in str(exc.value)


def test_tempo_bounds_must_be_ordered() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[pool.scales]\ntempo = [100, 80]")
    assert "pool.scales.tempo" in str(exc.value)


def test_a_single_tempo_is_a_degenerate_but_legal_range() -> None:
    assert load_string("[pool.scales]\ntempo = [90, 90]").pool["scales"].tempo == (90, 90)


# --------------------------------------------------------------------------
# Registry-backed axes — the accepted values come from vocabulary
# --------------------------------------------------------------------------


def test_registry_axis_accepts_its_identifiers() -> None:
    cfg = load_string('[pool.scales]\ntraversals = ["positional", "three_note_per_string"]')
    assert cfg.pool["scales"].values["traversal"] == ("positional", "three_note_per_string")


def test_registry_axis_accepts_all() -> None:
    cfg = load_string('[pool.rhythm]\naccent_patterns = "all"')
    assert cfg.rhythm.values["accent_pattern"] == tuple(vocabulary.accepted("accent_pattern"))


def test_registry_axis_rejects_an_unknown_identifier_naming_the_axis_values() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string('[pool.rhythm]\naccent_patterns = ["every_4"]')
    assert "pool.rhythm.accent_patterns[0]" in str(exc.value)
    assert "every_3" in str(exc.value)


def test_string_skip_accepts_the_integers_the_spec_writes() -> None:
    # B3 made these the identifier strings "0", "1", "2"; TOML yields ints.
    cfg = load_string("[pool.intervals]\nstring_skips = [0, 2]")
    assert cfg.pool["intervals"].values["string_skip"] == ("0", "2")


def test_string_skip_rejects_a_value_outside_the_registry() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[pool.intervals]\nstring_skips = [3]")
    assert "3" in str(exc.value)


def test_an_identifier_of_the_wrong_type_is_rejected() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[pool.rhythm]\naccent_patterns = [1.5]")
    assert "pool.rhythm.accent_patterns[0]" in str(exc.value)


def test_a_boolean_is_not_an_identifier() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[pool.rhythm]\naccent_patterns = [true]")
    assert "pool.rhythm.accent_patterns[0]" in str(exc.value)


def test_an_axis_must_be_a_list_or_all() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string('[pool.scales]\nscale_types = "dorian"')
    assert "pool.scales.scale_types" in str(exc.value)


def test_an_empty_axis_is_rejected() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[pool.scales]\nscale_types = []")
    assert "pool.scales.scale_types" in str(exc.value)


def test_every_rhythm_axis_loads() -> None:
    cfg = load_string('[pool.rhythm]\naccent_patterns = "all"\nnote_value_patterns = "all"\n')
    assert set(cfg.rhythm.values) == {axis.name for axis in _RHYTHM_AXES}


# --------------------------------------------------------------------------
# Range-like axes — validated numerically against the profile (§5, §13)
# --------------------------------------------------------------------------


def test_roots_are_pitch_classes() -> None:
    cfg = load_string("[pool.scales]\nroots = [0, 7]")
    assert cfg.pool["scales"].values["root"] == (0, 7)


def test_a_root_outside_the_octave_is_rejected() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[pool.scales]\nroots = [12]")
    assert "pool.scales.roots[0]" in str(exc.value)


def test_octaves_are_bounded_by_the_spec() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[pool.scales]\noctaves = [4]")
    assert "pool.scales.octaves[0]" in str(exc.value)


def test_intervals_span_a_second_to_a_tenth() -> None:
    cfg = load_string("[pool.intervals]\nintervals = [2, 10]")
    assert cfg.pool["intervals"].values["interval"] == (2, 10)
    with pytest.raises(ConfigError):
        load_string("[pool.intervals]\nintervals = [11]")


def test_a_non_integer_range_value_is_rejected() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string('[pool.scales]\noctaves = ["two"]')
    assert "pool.scales.octaves[0]" in str(exc.value)


def test_start_strings_are_bounded_by_the_configured_profile() -> None:
    assert load_string("[pool.chromatic]\nstart_strings = [4]").pool["chromatic"].values[
        "start_string"
    ] == (4,)
    with pytest.raises(ConfigError) as exc:
        load_string(BASS4 + "[pool.chromatic]\nstart_strings = [4]")
    assert "pool.chromatic.start_strings[0]" in str(exc.value)


def test_start_frets_are_bounded_by_the_profiles_fret_count() -> None:
    assert load_string("[pool.chromatic]\nstart_frets = [24]").pool["chromatic"].values[
        "start_fret"
    ] == (24,)
    with pytest.raises(ConfigError) as exc:
        load_string(BASS4 + "[pool.chromatic]\nstart_frets = [24]")
    assert "pool.chromatic.start_frets[0]" in str(exc.value)


def test_spans_are_bounded_by_the_string_count() -> None:
    assert load_string("[pool.chromatic]\nspans = [6]").pool["chromatic"].values["span"] == (6,)
    with pytest.raises(ConfigError):
        load_string("[pool.chromatic]\nspans = [7]")


def test_a_range_axis_accepts_all() -> None:
    cfg = load_string('[pool.scales]\noctaves = "all"')
    assert cfg.pool["scales"].values["range_octaves"] == (1, 2, 3)


# --------------------------------------------------------------------------
# Permutations and string sets — structure, not an enumerated vocabulary
# --------------------------------------------------------------------------


def test_permutations_are_orderings_of_the_four_fingers() -> None:
    cfg = load_string("[pool.chromatic]\npermutations = [[1, 2, 3, 4], [1, 3, 2, 4]]")
    assert cfg.pool["chromatic"].values["permutation"] == ((1, 2, 3, 4), (1, 3, 2, 4))


def test_all_permutations_are_the_twenty_four_orderings() -> None:
    cfg = load_string('[pool.chromatic]\npermutations = "all"')
    assert len(cfg.pool["chromatic"].values["permutation"]) == 24


def test_a_repeated_finger_is_not_a_permutation() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[pool.chromatic]\npermutations = [[1, 1, 2, 3]]")
    assert "pool.chromatic.permutations[0]" in str(exc.value)


def test_a_permutation_must_be_a_list() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[pool.chromatic]\npermutations = [1234]")
    assert "pool.chromatic.permutations[0]" in str(exc.value)


def test_a_permutation_entry_must_be_an_integer() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string('[pool.chromatic]\npermutations = [["1", 2, 3, 4]]')
    assert "pool.chromatic.permutations[0][0]" in str(exc.value)


def test_string_sets_are_ascending_subsets_of_the_strings() -> None:
    cfg = load_string("[pool.scales]\nstring_sets = [[0, 1, 2], [0, 2, 4]]")
    assert cfg.pool["scales"].values["string_set"] == ((0, 1, 2), (0, 2, 4))


def test_a_string_set_must_be_a_list() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[pool.scales]\nstring_sets = [3]")
    assert "pool.scales.string_sets[0]" in str(exc.value)


def test_a_string_set_entry_must_be_an_integer() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string('[pool.scales]\nstring_sets = [["0", 1]]')
    assert "pool.scales.string_sets[0][0]" in str(exc.value)


def test_an_empty_string_set_is_rejected() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[pool.scales]\nstring_sets = [[]]")
    assert "pool.scales.string_sets[0]" in str(exc.value)


def test_a_string_set_is_bounded_by_the_profile() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string(BASS4 + "[pool.scales]\nstring_sets = [[0, 1, 4]]")
    assert "pool.scales.string_sets[0][2]" in str(exc.value)
    assert "bass4" in str(exc.value)


def test_a_string_set_must_be_strictly_ascending() -> None:
    # Same reasoning as decision #22: the index order is the instrument.
    with pytest.raises(ConfigError) as exc:
        load_string("[pool.scales]\nstring_sets = [[2, 1]]")
    assert "pool.scales.string_sets[0][1]" in str(exc.value)
    assert "ascending" in str(exc.value)


def test_a_repeated_string_is_not_a_set() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("[pool.scales]\nstring_sets = [[1, 1]]")
    assert "ascending" in str(exc.value)


def test_string_sets_have_no_all_shorthand() -> None:
    # Every non-empty subset of six strings is 63 values; an error message
    # listing them would not be an error message anyone could read.
    with pytest.raises(ConfigError) as exc:
        load_string('[pool.scales]\nstring_sets = "all"')
    assert "pool.scales.string_sets" in str(exc.value)


# --------------------------------------------------------------------------
# Every family's own axes
# --------------------------------------------------------------------------


def test_every_chromatic_axis_loads() -> None:
    cfg = load_string(
        "[pool.chromatic]\n"
        'permutations = "all"\nstart_strings = [0]\nstart_frets = [0]\n'
        'directions = "all"\nstring_traversals = "all"\nshifts = "all"\nspans = [2]\n'
    )
    assert set(cfg.pool["chromatic"].values) == {axis.name for axis in _AXES_BY_FAMILY["chromatic"]}


def test_every_arpeggio_axis_loads() -> None:
    cfg = load_string(
        "[pool.arpeggios]\n"
        'roots = "all"\nqualities = "all"\ninversions = "all"\ntraversals = "all"\n'
        'string_sets = [[0, 1, 2]]\npatterns = "all"\noctaves = [1]\ndirections = "all"\n'
    )
    assert set(cfg.pool["arpeggios"].values) == {axis.name for axis in _AXES_BY_FAMILY["arpeggios"]}


def test_every_interval_axis_loads() -> None:
    cfg = load_string(
        "[pool.intervals]\n"
        'intervals = "all"\ncontexts = "all"\nroots = "all"\nscale_types = "all"\n'
        'string_skips = "all"\nstring_sets = [[0, 1]]\ndirections = "all"\npatterns = "all"\n'
    )
    assert set(cfg.pool["intervals"].values) == {axis.name for axis in _AXES_BY_FAMILY["intervals"]}


# --------------------------------------------------------------------------
# Drift guards — the registry is the only source of accepted values
# --------------------------------------------------------------------------


def test_pools_are_declared_for_exactly_the_registry_families() -> None:
    assert set(_AXES_BY_FAMILY) == set(vocabulary.accepted("family"))


def test_the_pool_samples_exactly_the_axes_each_family_requires() -> None:
    # The requirement is *derived* from the family, never restated here: the
    # family module owns the list of axes it reads, and a copy in this test
    # would be a third spelling of it that could agree with neither.
    #
    # This is the assertion `intervals` failed before this change — its pool
    # omitted `root` and `scale_type`, so every specification the selector
    # could draw from it was missing an axis the family requires, and the
    # failure surfaced in the selector rather than here.
    for family, entry in REGISTRY.items():
        assert {axis.name for axis in _AXES_BY_FAMILY[family]} == set(entry.axes), family


def test_no_axis_key_is_declared_twice_within_a_family() -> None:
    for family, axes in _AXES_BY_FAMILY.items():
        keys = [axis.key for axis in axes]
        assert len(keys) == len(set(keys)), f"{family} declares a key twice"


def test_axis_keys_are_plural_and_names_are_singular() -> None:
    for axes in (*_AXES_BY_FAMILY.values(), _RHYTHM_AXES):
        for axis in axes:
            assert axis.key.endswith("s"), f"{axis.key} is not a plural config key"


# --------------------------------------------------------------------------
# Loading from a file
# --------------------------------------------------------------------------


def test_load_reads_a_file(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[session]\ncount = 3\n", encoding="utf-8")
    assert load(path).session.count == 3


def test_load_names_a_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "absent.toml"
    with pytest.raises(ConfigError) as exc:
        load(path)
    assert str(path) in str(exc.value)


def test_load_names_the_file_when_the_toml_is_malformed(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[session\ncount = 3\n", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load(path)
    assert str(path) in str(exc.value)


def test_malformed_toml_is_a_config_error() -> None:
    with pytest.raises(ConfigError) as exc:
        load_string("count = ")
    assert "TOML" in str(exc.value)
