"""Canonical arpeggio seed shapes and their derivation (spec §6, decision 12).

Arpeggio fingering is genuinely ambiguous — the third can sit on the root's
string or the string above, and different qualities read differently — so this
family does not infer it. It encodes **one canonical seed shape per quality**
as reviewable data and *derives* every higher octave from that seed by
transposition, rather than hand-enumerating each `(quality, inversion,
position)`. This replaces `_across`'s "hold a string when the next can't reach"
rule, whose partial coverage is defect 4.

A seed is the one-octave plucking shape a bassist reads: the root and each
successive chord tone climb one string, so `SEED_SHAPES[quality]` is the
`(string_offset, fret_offset)` of the root, third, fifth and seventh relative to
wherever the root is placed. Because every bass profile is tuned in perfect
fourths — five semitones a string (`instrument.py`) — a chord tone `n` semitones
above the root sitting on `string_offset` strings up takes `fret_offset =
n - 5 * string_offset`, and an octave repeats the shape shifted up
`_OCTAVE_STRING_STEP` strings (ten semitones) plus two frets. That uniform
spacing is what lets one seed derive the whole neck: correct a seed at Task F1
and every derived placement follows with no code change.

**The seed shapes are PROVISIONAL musical data.** They ship so the family can be
built, but they are the instructor's call to confirm and are gated on the
validation task (Task F1, `melete#152`). Deriving from the seed keeps that a pure
data edit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from melete import theory

if TYPE_CHECKING:
    from collections.abc import Sequence

    from melete.instrument import InstrumentProfile

_FAMILY = "arpeggios"

#: Strings an octave spans in perfect-fourths tuning: ten of its twelve
#: semitones are two strings, and the remaining two are frets. This is what a
#: higher octave shifts the seed by, so the shape reads identically an octave up.
_OCTAVE_STRING_STEP = 2

_OCTAVE_FRET_STEP = 2


def _seed(quality: str) -> tuple[tuple[int, int], ...]:
    """The one-tone-per-string seed for `quality`, derived from its chord tones.

    Each chord tone climbs one string from the last (root on string offset 0,
    third on 1, fifth on 2, seventh on 3); the fret offset is forced by the
    fourths tuning so the placement sounds the tone. Building the seed from
    `theory.CHORDS` keeps the shape and the pitches it names from drifting
    apart — a quality respelled in `theory` respells its seed with it.
    """
    intervals = theory.chord_pitches(root=0, quality=quality)
    return tuple(
        (string_offset, interval - 5 * string_offset)
        for string_offset, interval in enumerate(intervals)
    )


#: One canonical seed shape per quality the pool drills (spec §6). PROVISIONAL —
#: instructor-validated at Task F1 (`melete#152`). Root, third, fifth and
#: seventh each climb one string; the fret offsets fall out of fourths tuning.
SEED_SHAPES: dict[str, tuple[tuple[int, int], ...]] = {
    quality: _seed(quality) for quality in ("maj7", "min7", "dom7", "m7b5", "min6")
}


def shape_places(
    profile: InstrumentProfile,
    root_place: tuple[int, int],
    quality: str,
    tones: Sequence[int],
) -> list[tuple[int, int]]:
    """Tile `quality`'s seed shape from `root_place` up the strings across `tones`.

    Each tone takes the string the seed assigns it — the seed pattern for its
    position within the octave, raised `_OCTAVE_STRING_STEP` strings per octave
    above the root — and the fret that *sounds* the tone on that string, so pitch
    is always preserved (`profile.tuning[string] + fret == tone`). With enough
    tones the tiling climbs to the top string (the fix for defect 4).

    A tone whose string leaves the instrument, or whose fret leaves the neck, is
    **raised, never clamped** (spec §10): the caller's validity gate resamples
    rather than engrave a note somewhere it was not asked for.
    """
    if quality not in SEED_SHAPES:
        msg = (
            f"{_FAMILY}: no seed shape for quality {quality!r}; "
            f"known qualities are {sorted(SEED_SHAPES)}"
        )
        raise ValueError(msg)

    seed = SEED_SHAPES[quality]
    root_string, _root_fret = root_place
    octave_len = len(seed)
    string_count = len(profile.tuning)

    places: list[tuple[int, int]] = []
    for index, pitch in enumerate(tones):
        octave, position = divmod(index, octave_len)
        string_offset, _fret_offset = seed[position]
        string = root_string + string_offset + _OCTAVE_STRING_STEP * octave
        if not 0 <= string < string_count:
            msg = (
                f"{_FAMILY}: tone {pitch} of a {quality} anchored at {root_place} lands on "
                f"string {string} of profile {profile.name!r}, which has strings "
                f"0 to {string_count - 1}. The shape is derived, never clamped (spec §10), "
                f"so this arpeggio is unrealizable here rather than moved onto the neck"
            )
            raise ValueError(msg)
        fret = pitch - profile.tuning[string]
        if not 0 <= fret <= profile.fret_count:
            msg = (
                f"{_FAMILY}: tone {pitch} of a {quality} anchored at {root_place} needs fret "
                f"{fret} on string {string} of profile {profile.name!r}, which has frets "
                f"0 to {profile.fret_count}. The shape is derived, never clamped (spec §10), "
                f"so this arpeggio is unrealizable here rather than moved onto the neck"
            )
            raise ValueError(msg)
        places.append((string, fret))
    return places
