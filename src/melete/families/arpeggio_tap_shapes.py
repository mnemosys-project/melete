"""The universal two-hand tap box and its placement (Task B1, epic #67, spec §5).

B0 (`melete#188`, `docs/reports/triad-tap-shapes-capture.md`) captured the
instructor's own tapped-triad playing and found the four triads share **one**
universal two-hand box, not twelve per-quality shapes. Within one octave —
root to octave-root — the strings, hands and the third/right-hand fingers are
identical across `maj`/`min`/`dim`/`aug`:

    root         string S     LEFT  ring (3) or middle (2)   ← quality-aware (R2)
    third        string S+1   LEFT  index  (1)
    fifth        string S+1   RIGHT index  (1)
    octave-root  string S+2   RIGHT middle (2)

Two things move with the quality, and both are **derived** rather than
tabulated. The third's and fifth's *frets* shift with their intervals; and the
left-hand *root finger* mirrors the third's fret gap (corpus rule R2,
`melete#200` / F2, `melete#202`). The third is always the index finger, and the
root is played the same number of frets — hence fingers — above it, so a
minor/diminished third (two frets back) takes the ring finger (3) and a
major/augmented third (one fret back) the middle finger (2). Finger spacing
mirrors fret spacing; it is an ergonomic derivation, not a table. Everything
else is the fixed `TAP_BOX`.

Frets derive as in the one-hand seed (`arpeggio_shapes._seed`): a chord tone `i`
semitones above the root, placed `string_offset` strings up (each a perfect
fourth, five semitones), sounds at `root_fret + i - 5 * string_offset`, and
deriving the fret from the profile's own tuning preserves pitch by construction
(`tuning[string] + fret == pitch`).

**Scope (F2).** Only the first-octave box's quality-aware root finger is
handled here. The octave- and direction-dependent finger shifts (R4/R5) are the
future fingering *solve* and are out of scope.

**PROVISIONAL — instructor-gated, Task E1.** The box is the instructor's taught
technique captured in a working session; it ships so the family can be built,
but Task E1 (`melete#…`, the analogue of the one-hand seed's `melete#152`) is the
formal sign-off before generated sheets are trusted. Deriving from the interval
keeps that confirmation a pure data edit.

**Triads only.** The box is a one-octave, four-tone shape; seventh chords add a
tone and need their own captured box (an explicit next iteration, spec §2). A
non-triad quality raises rather than being forced through the box (spec §9).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from melete import theory
from melete.score import Hand

if TYPE_CHECKING:
    from melete.instrument import InstrumentProfile

_FAMILY = "arpeggios"

#: A perfect fourth — five semitones — is one string in the target tuning, so a
#: tone `string_offset` strings up is `5 * string_offset` semitones higher for
#: the same fret. This is what lets the box's fixed string offsets preserve
#: pitch with a derived fret (spec §5, mirroring `arpeggio_shapes`).
_FOURTH = 5

#: One octave is twelve semitones; the octave-root closes the box a twelfth
#: above its root.
_OCTAVE = 12

#: How many chord tones a triad has. The box is a one-octave triad shape; a
#: quality with a different tone count (a seventh) is not a triad and raises.
_TRIAD_TONES = 3

#: The third's interval sits at index 1 of the box's interval tuple
#: (root, third, fifth, octave-root). Its fret gap sets the left-hand root
#: finger (R2).
_THIRD_TONE = 1

#: The left-hand third is always the index finger (R2); the root finger is the
#: index finger plus the fret gap up to it.
_LEFT_INDEX = 1


@dataclass(frozen=True)
class TapPosition:
    """One tapped note in the universal box: its role and fixed choreography.

    `string_offset` and `hand` are the fixed, quality-independent data B0
    captured. `finger` is fixed for the third and the two right-hand tones, but
    `None` for the root, whose finger is *derived* per quality (R2) — like the
    fret, which is never stored either. `box_places` derives both per quality
    and anchor, so a quality is placed by its intervals, not by a table.
    """

    role: str
    string_offset: int
    hand: Hand
    finger: int | None


#: The single universal two-hand box (spec §5), PROVISIONAL until Task E1.
#: Strings climb 0, 1, 1, 2; the left hand takes the lower pair (root, third),
#: the right hand the upper pair (fifth, octave-root) with index then middle.
#: The third and right-hand fingers are fixed; the root finger is **derived**
#: per quality (R2), so it is `None` here — `box_places` fills it from the
#: third's fret gap (ring (3) for min/dim, middle (2) for maj/aug).
TAP_BOX: tuple[TapPosition, ...] = (
    TapPosition(role="root", string_offset=0, hand=Hand.LEFT, finger=None),
    TapPosition(role="third", string_offset=1, hand=Hand.LEFT, finger=1),
    TapPosition(role="fifth", string_offset=1, hand=Hand.RIGHT, finger=1),
    TapPosition(role="octave-root", string_offset=2, hand=Hand.RIGHT, finger=2),
)


def _root_finger(third_interval: int) -> int:
    """The left-hand root finger for a third `third_interval` semitones up (R2).

    On the box's next-string-up (a fourth, `_FOURTH` semitones) the third sounds
    `third_interval` semitones above the root but sits `_FOURTH - third_interval`
    frets *below* it. The third is the index finger (`_LEFT_INDEX`); the root is
    played that many frets — hence fingers — higher, so finger spacing mirrors
    fret spacing. A minor/diminished third (3) yields the ring finger (3); a
    major/augmented third (4) yields the middle finger (2). Ergonomic
    derivation, not a table.
    """
    return _LEFT_INDEX + (_FOURTH - third_interval)


def _triad_intervals(quality: str) -> tuple[int, ...]:
    """The four box intervals for a triad: root, third, fifth, octave-root.

    Intervals come straight from `theory.CHORDS`, so a quality respelled there
    respells the box with it (nothing here is quality-specific). A quality that
    is not a three-tone triad — a seventh, most importantly — raises rather than
    being forced through a one-octave, four-tone box (spec §9).
    """
    if quality not in theory.CHORDS:
        msg = f"{_FAMILY}: unknown quality {quality!r}; accepted: {sorted(theory.CHORDS)}"
        raise ValueError(msg)
    intervals = theory.CHORDS[quality]
    if len(intervals) != _TRIAD_TONES:
        msg = (
            f"{_FAMILY}: the two-hand tap box is a triad shape, but {quality!r} has "
            f"{len(intervals)} chord tones, not {_TRIAD_TONES}. Sevenths add a tone and "
            f"need their own captured box (spec §2); they are not forced through this one"
        )
        raise ValueError(msg)
    return (*intervals, _OCTAVE)  # root, third, fifth, octave-root


def box_places(
    profile: InstrumentProfile,
    root_place: tuple[int, int],
    quality: str,
) -> list[tuple[int, int, Hand, int]]:
    """Apply the universal box to `quality`'s chord tones from `root_place`.

    Returns one `(string, fret, hand, finger)` per box position — root, third,
    fifth, octave-root. Strings and hands are `TAP_BOX`'s fixed choreography, as
    are the third and right-hand fingers. Two things are **derived**, not
    tabulated: each fret, and the left-hand root finger. The tone sounds
    `root_pitch + interval`, placed on the box's string, and the fret is whatever
    the profile's tuning needs to sound it — on the target fourths tuning that is
    `root_fret + interval - 5 * string_offset`, and pitch is preserved by
    construction on any tuning (`profile.tuning[string] + fret == pitch`). The
    root finger mirrors the third's fret gap (R2): ring (3) for a min/dim third,
    middle (2) for a maj/aug third.

    A non-triad `quality` raises (spec §9): the box is a one-octave triad shape.
    """
    intervals = _triad_intervals(quality)
    root_string, root_fret = root_place
    root_pitch = profile.tuning[root_string] + root_fret
    root_finger = _root_finger(intervals[_THIRD_TONE])

    places: list[tuple[int, int, Hand, int]] = []
    for position, interval in zip(TAP_BOX, intervals, strict=True):
        string = root_string + position.string_offset
        pitch = root_pitch + interval
        fret = pitch - profile.tuning[string]
        finger = position.finger if position.finger is not None else root_finger
        places.append((string, fret, position.hand, finger))
    return places
