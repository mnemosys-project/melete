"""Pitch, interval, scale and chord math.

Pure 12-TET integer arithmetic, C4 = 60. No I/O, no randomness, no knowledge of
instruments or notation — an exercise family decides *which* notes; this module
only says what a scale or a chord contains.

Every collection here is keyed by the canonical identifier used in
configuration. Unknown identifiers raise naming the key **and** its accepted
values, because §13 forbids falling back to a default for a misspelled key.
"""

PITCH_CLASSES: tuple[str, ...] = (
    "C",
    "Db",
    "D",
    "Eb",
    "E",
    "F",
    "Gb",
    "G",
    "Ab",
    "A",
    "Bb",
    "B",
)

# Semitone offsets from the root. Each tuple is strictly ascending, starts at 0,
# and stays within one octave; the octave itself is appended by scale_pitches.
SCALES: dict[str, tuple[int, ...]] = {
    # --- modes of the major scale ---
    "ionian": (0, 2, 4, 5, 7, 9, 11),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "aeolian": (0, 2, 3, 5, 7, 8, 10),
    "locrian": (0, 1, 3, 5, 6, 8, 10),
    # --- modes of the melodic minor scale ---
    "melodic_minor": (0, 2, 3, 5, 7, 9, 11),
    "dorian_b2": (0, 1, 3, 5, 7, 9, 10),
    "lydian_augmented": (0, 2, 4, 6, 8, 9, 11),
    "lydian_dominant": (0, 2, 4, 6, 7, 9, 10),
    "mixolydian_b6": (0, 2, 4, 5, 7, 8, 10),
    "locrian_natural2": (0, 2, 3, 5, 6, 8, 10),
    "altered": (0, 1, 3, 4, 6, 8, 10),
    # --- modes of the harmonic minor scale ---
    "harmonic_minor": (0, 2, 3, 5, 7, 8, 11),
    "locrian_natural6": (0, 1, 3, 5, 6, 9, 10),
    "ionian_sharp5": (0, 2, 4, 5, 8, 9, 11),
    "dorian_sharp4": (0, 2, 3, 6, 7, 9, 10),
    "phrygian_dominant": (0, 1, 4, 5, 7, 8, 10),
    "lydian_sharp2": (0, 3, 4, 6, 7, 9, 11),
    "ultralocrian": (0, 1, 3, 4, 6, 8, 9),
    # --- pentatonic, blues and symmetric ---
    "major_pentatonic": (0, 2, 4, 7, 9),
    "minor_pentatonic": (0, 3, 5, 7, 10),
    "blues": (0, 3, 5, 6, 7, 10),
    "whole_tone": (0, 2, 4, 6, 8, 10),
    "diminished_whole_half": (0, 2, 3, 5, 6, 8, 9, 11),
    "diminished_half_whole": (0, 1, 3, 4, 6, 7, 9, 10),
}

# Chord tones as semitone offsets from the root, in root position.
CHORDS: dict[str, tuple[int, ...]] = {
    "maj": (0, 4, 7),
    "min": (0, 3, 7),
    "dim": (0, 3, 6),
    "aug": (0, 4, 8),
    "maj7": (0, 4, 7, 11),
    "min7": (0, 3, 7, 10),
    "dom7": (0, 4, 7, 10),
    "m7b5": (0, 3, 6, 10),
    "dim7": (0, 3, 6, 9),
    "min_maj7": (0, 3, 7, 11),
    "maj6": (0, 4, 7, 9),
    "min6": (0, 3, 7, 9),
}

_SEMITONES_PER_OCTAVE = 12


def _lookup(table: dict[str, tuple[int, ...]], axis: str, name: str) -> tuple[int, ...]:
    """Resolve an identifier, or raise naming it and everything accepted."""
    if name not in table:
        msg = f"unknown {axis} {name!r}; accepted: {sorted(table)}"
        raise KeyError(msg)
    return table[name]


def scale_pitches(root: int, scale_type: str, octaves: int) -> list[int]:
    """Ascending absolute pitches across `octaves`, closing on the final octave.

    One octave of `ionian` from C4 is eight pitches, not seven: the closing
    octave is included because an exercise that stops a step short of it reads
    as unfinished.
    """
    offsets = _lookup(SCALES, "scale_type", scale_type)
    if octaves < 1:
        msg = f"octaves must be at least 1, got {octaves}"
        raise ValueError(msg)

    pitches = [
        root + offset + _SEMITONES_PER_OCTAVE * octave
        for octave in range(octaves)
        for offset in offsets
    ]
    pitches.append(root + _SEMITONES_PER_OCTAVE * octaves)
    return pitches


def chord_pitches(root: int, quality: str, inversion: int = 0) -> list[int]:
    """Ascending absolute pitches for one chord.

    An inversion rotates the chord tones and lifts the displaced ones by an
    octave, so the result is always ascending. An inversion the chord cannot
    support is an error rather than a silent wrap: a triad has no third
    inversion, and quietly returning root position would engrave the wrong
    chord convincingly.
    """
    offsets = _lookup(CHORDS, "quality", quality)
    if not 0 <= inversion < len(offsets):
        msg = (
            f"inversion {inversion} is out of range for {quality!r}: "
            f"expected 0 to {len(offsets) - 1}"
        )
        raise ValueError(msg)

    rotated = [
        *offsets[inversion:],
        *(offset + _SEMITONES_PER_OCTAVE for offset in offsets[:inversion]),
    ]
    return [root + offset for offset in rotated]
