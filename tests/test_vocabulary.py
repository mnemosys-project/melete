"""Tests for the canonical identifier registry.

Spec §14: "every identifier used in §7, §8, and the §10 example config
resolves; every axis value has a display name."

The load-bearing tests here are the drift guards. `theory` owns the scale and
chord identifiers; this module owns only their prose. The moment those two
sets disagree, §13's promise to name a key's accepted values is a promise the
code cannot keep — so the disagreement must fail a test, not a cover page.
"""

from __future__ import annotations

import re

import pytest

from melete import theory
from melete.vocabulary import AXES, _named, accepted, display

# Every axis §7 and §8 enumerate. Numeric and computed axes - `root`,
# `start_fret`, `span`, `string_set`, `range_octaves`, `permutation`,
# `interval` - are ranges rather than vocabularies and are deliberately absent.
EXPECTED_AXES = {
    "family",
    "scale_type",
    "quality",
    "traversal",
    "pattern",
    "direction",
    "string_traversal",
    "shift",
    "accent_pattern",
    "note_value_pattern",
    "context",
    "string_skip",
    "inversion",
}

# The identifiers the §10 example configuration actually writes.
EXAMPLE_CONFIG_IDENTIFIERS = {
    "family": ["chromatic", "scales", "arpeggios", "intervals"],
    "scale_type": ["ionian", "dorian", "phrygian", "major_pentatonic", "blues"],
    "pattern": ["straight", "thirds", "groups_of_3", "groups_of_4"],
    "traversal": ["positional", "three_note_per_string"],
    "accent_pattern": ["none", "every_3"],
    "note_value_pattern": ["straight", "long_short"],
}


# --------------------------------------------------------------------------
# Coverage of the spec's axes
# --------------------------------------------------------------------------


def test_registry_covers_exactly_the_enumerated_axes() -> None:
    assert set(AXES) == EXPECTED_AXES


def test_no_axis_is_empty() -> None:
    for axis, values in AXES.items():
        assert values, f"axis {axis!r} has no accepted values"


def test_identifiers_are_snake_case() -> None:
    for axis, values in AXES.items():
        for identifier in values:
            assert re.fullmatch(r"[a-z0-9_]+", identifier), (
                f"{axis} identifier {identifier!r} is not snake_case"
            )


def test_every_identifier_has_a_non_empty_display_name() -> None:
    for axis, values in AXES.items():
        for identifier, name in values.items():
            assert name.strip(), f"{axis}.{identifier} has no display name"


def test_display_names_are_prose_not_identifiers() -> None:
    # Display names land in a cover-page sentence (§12), so an underscore in
    # one means a raw identifier leaked into printed prose.
    for axis, values in AXES.items():
        for identifier, name in values.items():
            assert "_" not in name, f"{axis}.{identifier} display name is not prose"


# --------------------------------------------------------------------------
# The drift guards - the entire point of the registry
# --------------------------------------------------------------------------


def test_scale_types_match_theory_exactly() -> None:
    assert set(AXES["scale_type"]) == set(theory.SCALES)


def test_no_scale_type_lacks_a_display_name() -> None:
    missing = set(theory.SCALES) - set(AXES["scale_type"])
    assert not missing, f"scale types with no display name: {sorted(missing)}"


def test_no_display_name_names_a_scale_theory_does_not_have() -> None:
    orphans = set(AXES["scale_type"]) - set(theory.SCALES)
    assert not orphans, f"display names for unknown scale types: {sorted(orphans)}"


def test_chord_qualities_match_theory_exactly() -> None:
    assert set(AXES["quality"]) == set(theory.CHORDS)


def test_no_chord_quality_lacks_a_display_name() -> None:
    missing = set(theory.CHORDS) - set(AXES["quality"])
    assert not missing, f"chord qualities with no display name: {sorted(missing)}"


def test_no_display_name_names_a_chord_theory_does_not_have() -> None:
    orphans = set(AXES["quality"]) - set(theory.CHORDS)
    assert not orphans, f"display names for unknown chord qualities: {sorted(orphans)}"


def test_theory_identifiers_resolve_through_display() -> None:
    for scale_type in theory.SCALES:
        assert display("scale_type", scale_type)
    for quality in theory.CHORDS:
        assert display("quality", quality)


def test_named_rejects_an_identifier_with_no_display_name() -> None:
    # The import-time guard that makes the drift loud: `theory` growing an
    # entry this module has not named cannot produce a half-built axis.
    with pytest.raises(KeyError) as excinfo:
        _named("scale_type", ["dorian", "bebop_dominant"], {"dorian": "Dorian"})
    assert "bebop_dominant" in str(excinfo.value)
    assert "scale_type" in str(excinfo.value)


def test_named_preserves_the_owning_module_order() -> None:
    built = _named("quality", ["min", "maj"], {"maj": "major", "min": "minor"})
    assert list(built) == ["min", "maj"]


# --------------------------------------------------------------------------
# Display names
# --------------------------------------------------------------------------


def test_display_names_are_human_readable() -> None:
    assert display("traversal", "three_note_per_string") == "three-notes-per-string"
    assert display("scale_type", "dorian") == "Dorian"


def test_cover_page_sentence_reads_as_prose() -> None:
    # §12's example entry named the subdivision ("...triplet eighths"), but the
    # subdivision is no longer a display axis (#119) — the layout fitter derives
    # it (#118) and it does not travel in `params`. What the registry still
    # composes is the family half of that sentence.
    parts = [
        display("scale_type", "dorian"),
        display("traversal", "three_note_per_string"),
    ]
    assert ", ".join(parts) == "Dorian, three-notes-per-string"


def test_direction_reads_as_a_direction() -> None:
    assert display("direction", "up") == "ascending"
    assert display("direction", "down") == "descending"


def test_inversions_display_in_full() -> None:
    assert display("inversion", "root") == "root position"
    assert display("inversion", "first") == "first inversion"


# --------------------------------------------------------------------------
# The accepted-value listing
# --------------------------------------------------------------------------


def test_accepted_is_sorted_for_stable_error_messages() -> None:
    assert accepted("traversal") == sorted(accepted("traversal"))


def test_accepted_returns_every_identifier_on_the_axis() -> None:
    assert set(accepted("accent_pattern")) == set(AXES["accent_pattern"])


def test_accepted_rejects_an_unknown_axis_naming_the_axes() -> None:
    with pytest.raises(KeyError) as excinfo:
        accepted("tempo")
    assert "tempo" in str(excinfo.value)
    assert "scale_type" in str(excinfo.value)


# --------------------------------------------------------------------------
# The error contract of §13
# --------------------------------------------------------------------------


def test_unknown_identifier_names_accepted_values() -> None:
    with pytest.raises(KeyError) as excinfo:
        display("traversal", "nonsense")
    assert "nonsense" in str(excinfo.value)
    assert "positional" in str(excinfo.value)


def test_unknown_axis_in_display_names_the_axes() -> None:
    with pytest.raises(KeyError) as excinfo:
        display("tempo", "fast")
    assert "tempo" in str(excinfo.value)
    assert "accent_pattern" in str(excinfo.value)


# --------------------------------------------------------------------------
# The §10 example configuration
# --------------------------------------------------------------------------


def test_every_example_config_identifier_resolves() -> None:
    for axis, identifiers in EXAMPLE_CONFIG_IDENTIFIERS.items():
        for identifier in identifiers:
            assert display(axis, identifier)
