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

**Two boxes.** `TAP_BOX` is the one-octave, four-tone triad box. A seventh chord
adds a tone and taps on its own two-string grid, `SEVENTH_TAP_BOX` (corpus R11,
Task G1 `melete#208`): each string's lower-fret note left-hand-tapped, its
higher-fret note right-hand-tapped, so string N carries root (left) + third
(right) and string N+1 carries fifth (left) + seventh (right). Its frets derive
the same pitch-preserving way, and its fingering is **derived** from the same
corpus rules as the triad box — nothing is tabulated per quality. The right hand
plays the lower and higher notes of its pair with index (1) and middle (2) (R3);
on the left the root is index (1) and the **fifth finger mirrors its fret gap
above the root** (R2), so a perfect fifth (three frets up) takes the ring (3) and
a diminished fifth (two frets up) the middle (2). Each box refuses the other's
qualities rather than forcing a chord through the wrong shape (spec §9): a
non-triad raises in `box_places`, a non-seventh in `seventh_box_places`.
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


#: The five seventh qualities the seventh box covers (corpus R11), by their exact
#: `theory.CHORDS` keys. The box is a seventh-chord shape, so any other quality —
#: a triad, or a four-tone sixth chord — is refused rather than forced through it
#: (an explicit allowlist, not a tone-count test, since sixth chords also have
#: four tones).
#:
#: Public because it is the single source of truth for *tap-eligibility*: `config`
#: validates `[pool.arpeggios] tapped_qualities` against exactly this set, and
#: `arpeggios.derive` checks membership in it when routing a drawn seventh to the
#: two-hand journey. A sixth quality respelled here as tappable would become
#: tappable everywhere at once, with no second list to keep in step.
SEVENTH_QUALITIES: tuple[str, ...] = ("maj7", "min7", "dom7", "m7b5", "dim7")

#: The fifth's interval sits at index 2 of a chord's interval tuple
#: (root, third, fifth, seventh). Its fret gap above the root sets the left-hand
#: fifth finger (R2).
_FIFTH_TONE = 2


#: The seventh-chord two-hand tap box (corpus R11, spec §5 extended to sevenths),
#: PROVISIONAL until its own instructor gate. A seventh chord's four tones tap on
#: a two-string grid: string N carries root (LEFT) + third (RIGHT), string N+1
#: carries fifth (LEFT) + seventh (RIGHT) — so the left hand takes the lower-fret
#: note of each string and the right hand the higher-fret note. Unlike the triad
#: box there is no octave-tiling overlap: the four tones exactly fill the grid.
#: The right-hand fingers are fixed by R3 (index (1) on the lower note, middle (2)
#: on the higher), the left-hand root is index (1), and the left-hand fifth finger
#: is **derived** per quality (R2) — so it is `None` here and `seventh_box_places`
#: fills it from the fifth's fret gap above the root (ring (3) for a perfect
#: fifth, middle (2) for a diminished fifth).
SEVENTH_TAP_BOX: tuple[TapPosition, ...] = (
    TapPosition(role="root", string_offset=0, hand=Hand.LEFT, finger=1),
    TapPosition(role="third", string_offset=0, hand=Hand.RIGHT, finger=1),
    TapPosition(role="fifth", string_offset=1, hand=Hand.LEFT, finger=None),
    TapPosition(role="seventh", string_offset=1, hand=Hand.RIGHT, finger=2),
)


def _fifth_finger(fifth_interval: int) -> int:
    """The left-hand fifth finger for a fifth `fifth_interval` semitones up (R2).

    On the box's next-string-up (a fourth, `_FOURTH` semitones) the fifth sounds
    `fifth_interval` semitones above the root and sits `fifth_interval - _FOURTH`
    frets *above* it. The root is the index finger (`_LEFT_INDEX`); the fifth is
    played that many frets — hence fingers — higher, so finger spacing mirrors
    fret spacing. A perfect fifth (7) yields the ring finger (3); a diminished
    fifth (6) yields the middle finger (2). Ergonomic derivation, not a table —
    the mirror image of `_root_finger` on the triad box.
    """
    return _LEFT_INDEX + (fifth_interval - _FOURTH)


def _seventh_intervals(quality: str) -> tuple[int, ...]:
    """The four box intervals for a seventh chord: root, third, fifth, seventh.

    Intervals come straight from `theory.CHORDS`, so a quality respelled there
    respells the box with it (nothing here is quality-specific). A quality that
    is not one of the five seventh qualities (`SEVENTH_QUALITIES`) — a triad, or
    a four-tone sixth chord — raises rather than being forced through the
    seventh's two-string grid (spec §9).
    """
    if quality not in theory.CHORDS:
        msg = f"{_FAMILY}: unknown quality {quality!r}; accepted: {sorted(theory.CHORDS)}"
        raise ValueError(msg)
    if quality not in SEVENTH_QUALITIES:
        msg = (
            f"{_FAMILY}: the two-hand tap box for R11 is a seventh-chord shape, but "
            f"{quality!r} is not a seventh quality. Accepted sevenths: "
            f"{list(SEVENTH_QUALITIES)}"
        )
        raise ValueError(msg)
    return theory.CHORDS[quality]


def seventh_box_places(
    profile: InstrumentProfile,
    root_place: tuple[int, int],
    quality: str,
) -> list[tuple[int, int, Hand, int]]:
    """Apply the seventh box to `quality`'s chord tones from `root_place` (R11).

    Returns one `(string, fret, hand, finger)` per box position — root, third,
    fifth, seventh. Strings and hands are `SEVENTH_TAP_BOX`'s fixed choreography
    (string offsets 0, 0, 1, 1; hands LEFT, RIGHT, LEFT, RIGHT), as are the root,
    third and seventh fingers (index, index, middle). Two things are **derived**,
    not tabulated: each fret, and the left-hand fifth finger. The tone sounds
    `root_pitch + interval`, placed on the box's string, and the fret is whatever
    the profile's tuning needs to sound it — on the target fourths tuning that is
    `root_fret + interval - 5 * string_offset`, and pitch is preserved by
    construction on any tuning (`profile.tuning[string] + fret == pitch`). The
    fifth finger mirrors the fifth's fret gap above the root (R2): ring (3) for a
    perfect fifth, middle (2) for a diminished fifth.

    A non-seventh `quality` raises (spec §9): the grid is a seventh-chord shape.
    """
    intervals = _seventh_intervals(quality)
    root_string, root_fret = root_place
    root_pitch = profile.tuning[root_string] + root_fret
    fifth_finger = _fifth_finger(intervals[_FIFTH_TONE])

    places: list[tuple[int, int, Hand, int]] = []
    for position, interval in zip(SEVENTH_TAP_BOX, intervals, strict=True):
        string = root_string + position.string_offset
        pitch = root_pitch + interval
        fret = pitch - profile.tuning[string]
        finger = position.finger if position.finger is not None else fifth_finger
        places.append((string, fret, position.hand, finger))
    return places
