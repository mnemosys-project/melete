"""Canonical parameter identifiers and their human-readable display names.

One registry, three consumers (spec §13, decision #19):

    config      validates identifiers and, on failure, names the key and
                lists its accepted values verbatim from here
    families/   dispatch on the canonical identifier
    session,    render the display names into the cover page's plain-language
    cover page  summary: "D Dorian, three-notes-per-string, triplet eighths"

Without one registry those three grow private vocabularies and drift apart,
and §13's promise to "name the accepted values" is unimplementable because no
enumerated set exists.

Two halves, deliberately kept together. The *identifier* half is what
configuration writes and what code dispatches on; the *display* half is what
§12 prints. Splitting them would reintroduce exactly the drift this module
exists to prevent.

Axes that are ranges rather than vocabularies — `root`, `start_string`,
`start_fret`, `span`, `string_set`, `range_octaves`, `permutation`,
`interval` — are absent on purpose. They are validated against the instrument
profile (§5), not against an enumerated set, and listing a frozen subset here
would be a second source of truth for something the profile already decides.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from melete import theory

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


def _named(
    axis: str,
    identifiers: Iterable[str],
    display_names: Mapping[str, str],
) -> dict[str, str]:
    """Attach display names to identifiers owned by another module.

    `theory` owns the scale and chord identifiers; this module owns only their
    prose. Building those axes from `theory`'s keys rather than from a retyped
    list is what makes the two impossible to drift apart silently: a scale
    added to `theory.SCALES` with no display name here fails at import, loudly
    and by name, instead of surfacing later as a blank word on a cover page.

    The insertion order of `identifiers` is preserved so the registry reads in
    the owning module's order — modes grouped by parent scale, not alphabetised.
    """
    wanted = list(identifiers)
    unnamed = [identifier for identifier in wanted if identifier not in display_names]
    if unnamed:
        msg = f"{axis} identifiers with no display name: {sorted(unnamed)}"
        raise KeyError(msg)
    return {identifier: display_names[identifier] for identifier in wanted}


# Prose for every identifier in `theory.SCALES`. Modal names are capitalised
# because they are proper nouns; descriptive names are not.
_SCALE_TYPE_DISPLAY: dict[str, str] = {
    "ionian": "Ionian",
    "dorian": "Dorian",
    "phrygian": "Phrygian",
    "lydian": "Lydian",
    "mixolydian": "Mixolydian",
    "aeolian": "Aeolian",
    "locrian": "Locrian",
    "melodic_minor": "melodic minor",
    "dorian_b2": "Dorian b2",
    "lydian_augmented": "Lydian augmented",
    "lydian_dominant": "Lydian dominant",
    "mixolydian_b6": "Mixolydian b6",
    "locrian_natural2": "Locrian natural 2",
    "altered": "altered",
    "harmonic_minor": "harmonic minor",
    "locrian_natural6": "Locrian natural 6",
    "ionian_sharp5": "Ionian #5",
    "dorian_sharp4": "Dorian #4",
    "phrygian_dominant": "Phrygian dominant",
    "lydian_sharp2": "Lydian #2",
    "ultralocrian": "Ultralocrian",
    "major_pentatonic": "major pentatonic",
    "minor_pentatonic": "minor pentatonic",
    "blues": "blues",
    "whole_tone": "whole-tone",
    "diminished_whole_half": "whole-half diminished",
    "diminished_half_whole": "half-whole diminished",
}

# Prose for every identifier in `theory.CHORDS`. Spelled out rather than
# abbreviated: the cover page is read at a music stand, not parsed.
_QUALITY_DISPLAY: dict[str, str] = {
    "maj": "major",
    "min": "minor",
    "dim": "diminished",
    "aug": "augmented",
    "maj7": "major 7th",
    "min7": "minor 7th",
    "dom7": "dominant 7th",
    "m7b5": "half-diminished 7th",
    "dim7": "diminished 7th",
    "min_maj7": "minor-major 7th",
    "maj6": "major 6th",
    "min6": "minor 6th",
}

AXES: dict[str, dict[str, str]] = {
    # --- §7: which family realizes the exercise -------------------------
    "family": {
        "chromatic": "chromatic",
        "scales": "scales",
        "arpeggios": "arpeggios",
        "intervals": "intervals",
    },
    # --- §7 `scales`, §7 `arpeggios`: owned by theory -------------------
    "scale_type": _named("scale_type", theory.SCALES, _SCALE_TYPE_DISPLAY),
    "quality": _named("quality", theory.CHORDS, _QUALITY_DISPLAY),
    # --- §7: how the shape is laid across the fretboard -----------------
    # The union of the `scales` and `arpeggios` traversal columns: one axis,
    # because a family validates the subset it can realize.
    "traversal": {
        "positional": "positional",
        "three_note_per_string": "three-notes-per-string",
        "octave_per_string": "one-octave-per-string",
        "single_string": "single-string linear",
        "across_strings": "across strings",
    },
    # --- §7: the order the notes are visited in -------------------------
    # The union of the three families' `pattern` columns.
    "pattern": {
        "straight": "straight",
        "thirds": "thirds",
        "fourths": "fourths",
        "groups_of_3": "groups of 3",
        "groups_of_4": "groups of 4",
        "numeric_1235": "1-2-3-5",
        "numeric_1353": "1-3-5-3",
        "broken": "broken",
        "sweep_ordered": "sweep-ordered",
        "ascending_pairs": "ascending pairs",
        "descending_pairs": "descending pairs",
        "alternating": "alternating",
    },
    # --- §7: one axis, not two -----------------------------------------
    # `chromatic` spells this ascending/descending/both and the other three
    # families spell it up/down/up-down. They are the same axis and the
    # selector samples it once, so the registry carries one set of
    # identifiers and prints the prose form.
    "direction": {
        "up": "ascending",
        "down": "descending",
        "up_down": "up and down",
    },
    # --- §7 `chromatic` -------------------------------------------------
    "string_traversal": {
        "adjacent": "adjacent strings",
        "skip_1": "skipping one string",
        "single_string": "single string",
    },
    "shift": {
        "none": "no shift",
        "fret_per_cycle": "up one fret per cycle",
        "position_per_cycle": "up one position per cycle",
    },
    # --- §8: the rhythm modifier ---------------------------------------
    # The `subdivision` and `time_signature` axes are gone (#119): the layout
    # fitter derives the meter and subdivision (#118), so neither is sampled or
    # named here any longer. `rhythm.SUBDIVISIONS` still maps the fitter's
    # subdivision to a written duration, but that is the fitter's table, not a
    # display vocabulary.
    "accent_pattern": {
        "none": "no accents",
        "every_3": "accent every 3",
        "every_5": "accent every 5",
        "displaced": "accent displaced by one",
    },
    "note_value_pattern": {
        "straight": "straight",
        "long_short": "long-short",
        "short_long": "short-long",
    },
    # --- §7 `intervals` -------------------------------------------------
    "context": {
        "chromatic": "chromatic",
        "diatonic": "diatonic",
    },
    # The spec writes these as the numbers 0, 1 and 2. They are identifiers
    # here like every other value, so one lookup path serves every axis.
    "string_skip": {
        "0": "adjacent strings",
        "1": "skipping one string",
        "2": "skipping two strings",
    },
    # --- §7 `arpeggios` -------------------------------------------------
    "inversion": {
        "root": "root position",
        "first": "first inversion",
        "second": "second inversion",
        "third": "third inversion",
    },
}


def accepted(axis: str) -> list[str]:
    """Every identifier the axis accepts, sorted.

    Sorted rather than in registry order because this list is quoted verbatim
    into error messages (§13), and an error message that reorders itself
    between runs is one nobody can diff.
    """
    if axis not in AXES:
        msg = f"unknown axis {axis!r}; accepted: {sorted(AXES)}"
        raise KeyError(msg)
    return sorted(AXES[axis])


def display(axis: str, identifier: str) -> str:
    """The human-readable name §12's cover page prints for one identifier.

    An unknown axis or identifier raises naming the key *and* its accepted
    values. There is no fallback: §13 forbids guessing at a misspelled key,
    and a cover page that printed a raw identifier would be a silent failure
    of exactly the kind this module exists to prevent.
    """
    known = accepted(axis)  # raises first, naming the axes, if the axis is wrong
    if identifier not in known:
        msg = f"unknown {axis} {identifier!r}; accepted: {known}"
        raise KeyError(msg)
    return AXES[axis][identifier]
