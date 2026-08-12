"""Pitch, interval, scale and chord math, and the spelling of both.

Pure 12-TET integer arithmetic, C4 = 60. No I/O, no randomness, no knowledge of
instruments or notation — an exercise family decides *which* notes; this module
only says what a scale or a chord contains, and what each of those notes is
*called*.

Every collection here is keyed by the canonical identifier used in
configuration. Unknown identifiers raise naming the key **and** its accepted
values, because §13 forbids falling back to a default for a misspelled key.

## Spelling is a function of the key (spec §10a)

`Note.pitch` is an integer, and in twelve-tone equal temperament F♯ and G♭ are
the same integer. An integer therefore **cannot** carry a spelling. Deriving
note names from a fixed all-flats table — which is what `PITCH_CLASSES` is —
engraved F♯ Dorian as G♭ A♭ B𝄫 C♭ D♭ E𝄫 F♭: not an awkward rendering of F♯
Dorian but a different key, while the tablature stayed correct and the two
staves disagreed silently.

`spell` is the missing layer. It takes a `Key` and returns notation-neutral
`SpelledPitch` values — letter, alteration in semitones, octave — and knows
nothing about alphaTex or Unicode accidentals; `alphatab/emit.py` writes them
down.

**The tonic's letter is derived, never stored.** `Key.tonic` stays a pitch
class, so `root` stays an integer everywhere upstream — in the families, the
configuration and the selector — and exactly one derivation ever asks about
letters. `tonic_spelling` tries every candidate spelling of that pitch class,
discards any the scale cannot spell within a double accidental, and keeps the
one whose key signature carries the fewest accidentals. F♯ Dorian beats G♭
Dorian four accidentals to eight; D♭ major beats C♯ major five to seven. Ties
break toward the smaller alteration and then toward flats, so the choice is
deterministic and a sheet replays identically.

## Three tiers, one entry point

**Tier 1 — the seven diatonic modes.** Seven degrees, seven letters, each used
once. Fully determined by the tonic letter and the interval pattern.

**Tier 2 — scales with a parent.** Melodic and harmonic minor and their modes
still have seven degrees, so the letter rule still holds and they are spelled
by their own intervals; their *signature* is the parent's, which is why the
raised sixth and seventh appear as accidentals, exactly as they are written by
hand. The pentatonics and blues have fewer than seven degrees and are spelled
as the parent spells them — a subset borrows letters, it does not invent them.
The blue note is the one tone no parent names, and it is spelled as a ♭5.

**Tier 3 — symmetric and keyless.** Whole-tone, both diminished scales, and
anything with no key at all. No signature, and no parent to inherit from, so
direction is the only signal available: ascending takes sharps, descending
takes flats. Six notes cannot occupy seven letters and eight cannot avoid
repeating one, so letters skip and repeat here. That is accepted, not worked
around.

Chords are spelled by function — root, third, fifth and seventh take the
letters of degrees 1, 3, 5 and 7 — which is a different rule. Rather than give
`Key` a second form, `IMPLIED_PARENT` maps each chord quality onto a scale
whose spelling already contains the chord's, and the tiers above do the rest.

Tier 1 is determined; tiers 2 and 3 are convention, and convention is what a
reader with formal training will send back with corrections. Both therefore
live behind `spell` alone, so that revision is a change to one function rather
than to four family modules.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

#: Superseded by `spell` for notation: an all-flats table cannot distinguish F♯
#: from G♭ and so cannot spell a key (spec §10a). Nothing reads it to spell a
#: staff any more; its surviving consumers use it only for pitch-class display
#: names (the families' exercise titles) and for the pitch-class count.
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

#: Tier 1 (spec §10a): seven degrees, seven letters, no judgment involved.
_TIER_1: tuple[str, ...] = (
    "ionian",
    "dorian",
    "phrygian",
    "lydian",
    "mixolydian",
    "aeolian",
    "locrian",
)

#: Tier 2: the scale borrows its key signature from a parent, and — when it has
#: fewer than seven degrees — its note names as well.
_PARENTS: dict[str, str] = {
    # modes of the melodic minor scale
    "melodic_minor": "aeolian",
    "dorian_b2": "aeolian",
    "lydian_augmented": "aeolian",
    "lydian_dominant": "aeolian",
    "mixolydian_b6": "aeolian",
    "locrian_natural2": "aeolian",
    "altered": "aeolian",
    # modes of the harmonic minor scale
    "harmonic_minor": "aeolian",
    "locrian_natural6": "aeolian",
    "ionian_sharp5": "aeolian",
    "dorian_sharp4": "aeolian",
    "phrygian_dominant": "aeolian",
    "lydian_sharp2": "aeolian",
    "ultralocrian": "aeolian",
    # subsets, spelled as the parent spells them
    "major_pentatonic": "ionian",
    "minor_pentatonic": "aeolian",
    "blues": "aeolian",
}

#: Tier 3: symmetric, no signature, spelled by direction.
_TIER_3: tuple[str, ...] = (
    "whole_tone",
    "diminished_whole_half",
    "diminished_half_whole",
)

#: Chord quality → a scale whose spelling contains the chord's (spec §10a).
#:
#: Every quality maps to a scale that actually *contains* its chord tones, which
#: is the whole point of the mechanism: the chord's letters then fall out of the
#: parent's. That is why `min6` implies dorian and `min_maj7` implies melodic
#: minor rather than aeolian — the added sixth and the major seventh are not in
#: aeolian, and a parent that does not name a tone cannot lend it a letter. The
#: fully diminished seventh needs a doubly diminished seventh degree that no
#: seven-note scale supplies, so `dim` and `dim7` stay on the diminished scale
#: and are spelled by direction like everything else in tier 3.
IMPLIED_PARENT: dict[str, str] = {
    "maj": "ionian",
    "maj6": "ionian",
    "maj7": "ionian",
    "min": "aeolian",
    "min7": "aeolian",
    "min6": "dorian",
    "min_maj7": "melodic_minor",
    "dom7": "mixolydian",
    "m7b5": "locrian",
    "dim": "diminished_whole_half",
    "dim7": "diminished_whole_half",
    "aug": "whole_tone",
}

_SEMITONES_PER_OCTAVE = 12
_TRITONE = _SEMITONES_PER_OCTAVE // 2

#: Letter names in ascending order, and the pitch class each names unaltered.
_LETTERS = "CDEFGAB"
_NATURALS: dict[str, int] = {
    "C": 0,
    "D": 2,
    "E": 4,
    "F": 5,
    "G": 7,
    "A": 9,
    "B": 11,
}
_DEGREES = len(_LETTERS)

#: A double sharp or double flat is the most any spelling may ask for.
_MAX_ALTERATION = 2

#: The alterations a tonic may carry. A tonic needing more than one accidental
#: is a key nobody writes, so the candidate set is closed rather than searched.
_TONIC_ALTERATIONS = (-1, 0, 1)

_DIATONIC_TIER = 1
_PARENTED_TIER = 2
_SYMMETRIC_TIER = 3

#: C4 = 60, so pitch 0 is C-1 and the written octave is one below the integer's.
_OCTAVE_ORIGIN = 1


@dataclass(frozen=True)
class Key:
    """The tonal center an exercise is spelled against.

    `tonic` is a pitch class, not a letter: pitch class 6 is F♯ in one key and
    G♭ in another, and which one it is falls out of `scale_type` rather than
    being asserted here. See `tonic_spelling`.
    """

    tonic: int
    scale_type: str


@dataclass(frozen=True)
class SpelledPitch:
    """One note as it is *written*, in no particular notation.

    `alteration` is semitones — −2 to +2 — and never a glyph, so nothing here
    commits to alphaTex, to Unicode, or to English note names.

    `octave` belongs to the letter rather than to the sounding pitch, because
    that is what an octave number means on a staff: C♭5 is written a letter
    above the B4 it sounds, and B♯4 a letter below the C5 it sounds.
    """

    letter: str
    alteration: int
    octave: int


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


def tier(scale_type: str) -> int:
    """Which of §10a's three spelling tiers a scale belongs to.

    Tier 2 is the default rather than an enumeration: a scale added to `SCALES`
    and forgotten here is spelled by the letter rule against a parent, which
    fails loudly, instead of silently falling through to the direction rule,
    which would quietly produce a plausible-looking wrong answer.
    """
    _lookup(SCALES, "scale_type", scale_type)
    if scale_type in _TIER_1:
        return _DIATONIC_TIER
    if scale_type in _TIER_3:
        return _SYMMETRIC_TIER
    return _PARENTED_TIER


def parent_scale(scale_type: str) -> str | None:
    """The scale a tier 2 scale borrows its key signature from, else `None`."""
    _lookup(SCALES, "scale_type", scale_type)
    return _PARENTS.get(scale_type)


def _signature_offsets(scale_type: str) -> tuple[int, ...]:
    """The scale whose accidentals the key signature prints.

    A tier 2 scale prints its parent's signature, so its parent's accidentals
    are what choosing the tonic letter must minimise. Choosing against the
    scale's own accidentals instead would pick A♭ for harmonic minor on pitch
    class 8 and then print G♯ minor's five sharps against it.
    """
    parent = _PARENTS.get(scale_type)
    if parent is None:
        return SCALES[scale_type]
    return SCALES[parent]


def _spelling_offsets(scale_type: str) -> tuple[int, ...]:
    """The seven degrees the letter rule walks.

    A scale with seven degrees is spelled by its own intervals — that is what
    makes melodic minor's raised sixth an accidental against the signature
    rather than a different letter. A subset has too few degrees for the letter
    rule to have anything to say, so it borrows the parent's names.
    """
    offsets = SCALES[scale_type]
    if len(offsets) < _DEGREES:
        return SCALES[_PARENTS[scale_type]]
    return offsets


def _alteration(pitch_class: int, letter: str) -> int:
    """How far `letter` must be bent to sound `pitch_class`, as a signed count."""
    distance = (pitch_class - _NATURALS[letter]) % _SEMITONES_PER_OCTAVE
    return (distance + _TRITONE) % _SEMITONES_PER_OCTAVE - _TRITONE


def _by_direction(pitch_class: int, *, sharp: bool) -> tuple[str, int]:
    """Spell a pitch class with no key to consult: nearest letter, then direction.

    A natural always wins outright, because it is the only letter within zero
    semitones. The direction only decides the five pitch classes that sit
    exactly between two letters, and there it is the whole of the tier 3 rule —
    ascending takes the sharp of the letter below, descending the flat of the
    letter above.
    """
    lean = -1 if sharp else 1
    return min(
        ((letter, _alteration(pitch_class, letter)) for letter in _LETTERS),
        key=lambda named: (abs(named[1]), lean * named[1]),
    )


def _degree_spelling(
    letter: str, alteration: int, offsets: tuple[int, ...]
) -> dict[int, tuple[str, int]]:
    """Name every degree of a scale, keyed by its offset from the tonic.

    One letter per degree, walked in order from the tonic's, and the alteration
    is whatever it takes to make that letter sound the degree.
    """
    origin = _LETTERS.index(letter)
    tonic = (_NATURALS[letter] + alteration) % _SEMITONES_PER_OCTAVE
    spelling: dict[int, tuple[str, int]] = {}
    for degree, offset in enumerate(offsets):
        named = _LETTERS[(origin + degree) % _DEGREES]
        pitch_class = (tonic + offset) % _SEMITONES_PER_OCTAVE
        spelling[offset] = (named, _alteration(pitch_class, named))
    return spelling


def _tonic_candidates(pitch_class: int) -> list[tuple[str, int]]:
    """Every letter that can name `pitch_class` with at most one accidental."""
    return [
        (letter, alteration)
        for alteration in _TONIC_ALTERATIONS
        for letter, natural in _NATURALS.items()
        if (natural + alteration) % _SEMITONES_PER_OCTAVE == pitch_class
    ]


def tonic_spelling(key: Key) -> tuple[str, int]:
    """The letter and alteration the tonic is written with.

    Derived rather than stored, and derived by counting: of the spellings that
    name the tonic's pitch class, keep those the scale can spell within a
    double accidental, and take the one whose key signature has the fewest
    accidentals. Ties break toward the smaller alteration and then toward
    flats, which is what makes pitch class 6 major G♭ rather than a coin flip
    between two six-accidental signatures.

    A symmetric scale has no signature to minimise, so its tonic follows the
    ascending direction rule instead.
    """
    if tier(key.scale_type) == _SYMMETRIC_TIER:
        return _by_direction(key.tonic, sharp=True)

    spelled = _spelling_offsets(key.scale_type)
    signature = _signature_offsets(key.scale_type)
    ranked: list[tuple[tuple[int, int, int], str, int]] = []
    for letter, alteration in _tonic_candidates(key.tonic):
        degrees = _degree_spelling(letter, alteration, spelled)
        if any(abs(bend) > _MAX_ALTERATION for _, bend in degrees.values()):
            continue
        accidentals = sum(
            abs(bend) for _, bend in _degree_spelling(letter, alteration, signature).values()
        )
        ranked.append(((accidentals, abs(alteration), alteration), letter, alteration))

    if not ranked:
        msg = (
            f"no letter can spell {key.scale_type!r} on pitch class {key.tonic} "
            f"without exceeding a double accidental"
        )
        raise ValueError(msg)

    best = min(ranked, key=lambda entry: entry[0])
    return best[1], best[2]


def _spelled(pitch: int, named: tuple[str, int]) -> SpelledPitch:
    """Attach the octave the *letter* sits in, which is not always the pitch's."""
    letter, alteration = named
    natural = pitch - alteration
    octave = natural // _SEMITONES_PER_OCTAVE - _OCTAVE_ORIGIN
    return SpelledPitch(letter=letter, alteration=alteration, octave=octave)


def spell(key: Key | None, pitches: Sequence[int], descending: bool = False) -> list[SpelledPitch]:
    """Write down `pitches` as they are spelled in `key` (spec §10a).

    The single entry point for all three tiers, deliberately: tier 1 is
    determined but tiers 2 and 3 are convention, and the revision we expect
    from a reader with formal training should be a change here rather than
    across four family modules.

    `key` of `None` means the exercise has no tonal center — which is true of
    everything the `chromatic` family produces — and is a real value, not an
    omission. It spells by direction, as tier 3 does.

    `descending` selects sharps or flats for the pitch classes that sit between
    two letters, and only matters where there is no key to consult. A key
    spells the same in both directions; that is what having a key means.

    A pitch outside the scale — the blue note, or a chord tone the implied
    parent does not contain — falls back to the nearest letter, preferring
    flats, so the blue note is a ♭5 rather than a ♯4.
    """
    if key is None or tier(key.scale_type) == _SYMMETRIC_TIER:
        return [
            _spelled(pitch, _by_direction(pitch % _SEMITONES_PER_OCTAVE, sharp=not descending))
            for pitch in pitches
        ]

    letter, alteration = tonic_spelling(key)
    degrees = _degree_spelling(letter, alteration, _spelling_offsets(key.scale_type))
    written: list[SpelledPitch] = []
    for pitch in pitches:
        offset = (pitch - key.tonic) % _SEMITONES_PER_OCTAVE
        named = degrees.get(offset)
        if named is None:
            named = _by_direction(pitch % _SEMITONES_PER_OCTAVE, sharp=False)
        written.append(_spelled(pitch, named))
    return written
