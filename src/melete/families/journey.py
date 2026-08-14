"""The one-hand journey: outer string to opposite outer string, up and down.

Extent is governed by reaching the opposite outer string (spec §5); octave count
is whatever that yields on the instrument. Placement per fingering style lives
here; the families choose a style and their pitch content.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from melete.families._shared import box, directed_by_cell
from melete.instrument import positions

if TYPE_CHECKING:
    from collections.abc import Sequence

    from melete.instrument import InstrumentProfile


def per_string(
    profile: InstrumentProfile,
    pitches: Sequence[int],
    notes_per_string: int,
    family: str,
    axes: str,
) -> tuple[list[int], list[tuple[int, int]]]:
    """`notes_per_string` consecutive pitches on each string, low string up.

    Climbs outward one string at a time from the lowest, reaching the highest
    string by construction (the fix for defect 4). A pitch that falls off the
    neck raises rather than truncating the journey to fit (spec §5, §10).
    """
    used: list[int] = []
    places: list[tuple[int, int]] = []
    for string in range(len(profile.tuning)):
        for pitch in pitches[len(used) : len(used) + notes_per_string]:
            fret = pitch - profile.tuning[string]
            if not 0 <= fret <= profile.fret_count:
                msg = (
                    f"{family}: pitch {pitch} needs fret {fret} on string {string} of "
                    f"{profile.name!r} (frets 0..{profile.fret_count}); {axes} cannot all be "
                    f"satisfied. The journey is never truncated to fit (spec §5)"
                )
                raise ValueError(msg)
            used.append(pitch)
            places.append((string, fret))
    return used, places


def boxed_span(
    profile: InstrumentProfile,
    pitches: Sequence[int],
    family: str,
    axes: str,
) -> tuple[list[int], list[tuple[int, int]]]:
    """The longest leading run of `pitches` that fits one hand across all strings.

    Anchored at the lowest string's first available fret for the opening pitch,
    the box grows pitch by pitch while it still fits one position; extent ends at
    the highest string the box reaches.
    """
    strings = tuple(range(len(profile.tuning)))
    base = min(f for s, f in positions(profile, pitches[0]) if s == 0)
    used: list[int] = []
    places: list[tuple[int, int]] = []
    for pitch in pitches:
        try:
            candidate = box(profile, [*used, pitch], strings, (base,), family, axes)
        except ValueError:
            break
        used.append(pitch)
        places = candidate
    return used, places


def updown(order: Sequence[int], cell: int) -> list[int]:
    """The single direction this epic produces: up, then the retrograde (spec §5)."""
    return directed_by_cell(list(order), "up_down", cell)
