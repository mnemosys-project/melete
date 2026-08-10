"""Instrument profiles and fretboard queries.

Exercises reference string *indices* and interval relationships; no exercise
hardcodes a string name, a tuning or a string count. Instruments are
configurations, which is what makes multiple bass profiles nearly free.

The contract this module defines is the central invariant of the whole system:

    pitch == profile.tuning[string] + fret

`pitch_at` is one direction of it and `positions` is the other. Every family
test asserts it against generated notes.

`fret_count` is declared per profile and is never inferred. It determines which
specifications are valid, which determines the candidate pool, which determines
what the selector draws — two installations disagreeing about it would produce
different sheets from the same seed.

`position_span` is the second such number and is here for the same reason plus
one of its own. A family is a pure `params -> Score` function (§7) and the
profile is the only thing it is handed besides its parameters, so a bound a
family must respect has nowhere else to live — but it also *belongs* here:
how many frets fall under one hand is a fact about fret spacing, which is a
fact about the instrument. `hand_span` is the query that reads it.
"""

from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

# Absolute pitches, C4 = 60. Named so the tunings below read as an instrument
# rather than as arithmetic.
_B0 = 23
_E1 = 28
_A1 = 33
_D2 = 38
_G2 = 43
_C3 = 48

# Each tuning extends the one above it, exactly as the instruments do: the
# five-string adds a low B beneath the four-string, and the six-string adds a
# high C above that.
_BASS4_TUNING = (_E1, _A1, _D2, _G2)
_BASS5_TUNING = (_B0, *_BASS4_TUNING)
_BASS6_TUNING = (*_BASS5_TUNING, _C3)

_SHORT_FRETBOARD = 20
_LONG_FRETBOARD = 24

#: How far the fretting hand reaches without shifting, as a **span**: the
#: distance from its lowest fretted note to its highest.
#:
#: Four fingers cover four frets, and reaching one fret beyond them is ordinary
#: technique rather than a stretch a player would notice, so one hand position
#: is five frets and the span between its outermost notes is four. That is the
#: number a real position measures: exercise 2 of `sessions/2026-08-10` — the
#: one the issue #57 table calls a genuine position — spans frets 2 to 6.
#:
#: It is a default rather than a constant because it follows the fret spacing:
#: a short-scale instrument puts more frets under the same hand, and a player
#: whose reach disagrees overrides it in `[instrument] position_span` (§10).
DEFAULT_POSITION_SPAN = 4


@dataclass(frozen=True)
class InstrumentProfile:
    """One instrument: a name, a tuning low to high, and a declared fret count.

    `tuning` holds absolute pitches with index 0 as the *lowest* string. The
    ordering is validated rather than repaired: sorting a malformed tuning
    would shift every string index and engrave the wrong instrument
    convincingly, which is precisely the silent failure the design forbids.

    `position_span` says how much neck one hand position covers, and it is what
    makes `positional` mean a position rather than a label (issue #57).
    """

    name: str
    tuning: tuple[int, ...]
    fret_count: int
    position_span: int = DEFAULT_POSITION_SPAN

    def __post_init__(self) -> None:
        if not self.tuning:
            msg = f"profile {self.name!r} has an empty tuning; at least one string is required"
            raise ValueError(msg)

        for index, (lower, higher) in enumerate(pairwise(self.tuning), start=1):
            if higher <= lower:
                msg = (
                    f"profile {self.name!r} tuning is not strictly ascending at "
                    f"index {index}: {higher} does not exceed {lower}. Index 0 is "
                    f"the lowest string and every family depends on that ordering, "
                    f"so this is an error rather than a re-sortable input."
                )
                raise ValueError(msg)

        if self.fret_count < 1:
            msg = f"profile {self.name!r} has fret_count {self.fret_count}; expected at least 1"
            raise ValueError(msg)

        if self.position_span < 1:
            msg = (
                f"profile {self.name!r} has position_span {self.position_span}; expected at "
                f"least 1, since a hand that reaches no further than one fret is not a hand"
            )
            raise ValueError(msg)


PROFILES: dict[str, InstrumentProfile] = {
    "bass4": InstrumentProfile("bass4", _BASS4_TUNING, _SHORT_FRETBOARD),
    "bass5": InstrumentProfile("bass5", _BASS5_TUNING, _LONG_FRETBOARD),
    "bass6": InstrumentProfile("bass6", _BASS6_TUNING, _LONG_FRETBOARD),
}

DEFAULT_PROFILE = "bass6"


def resolve_profile(name: str) -> InstrumentProfile:
    """Resolve a built-in profile name, or raise naming it and what is accepted.

    A misspelled profile never falls back to a default: the fret count and
    string count it would silently substitute are exactly what decide whether a
    specification is valid.
    """
    if name not in PROFILES:
        msg = f"unknown profile {name!r}; accepted: {sorted(PROFILES)}"
        raise KeyError(msg)
    return PROFILES[name]


def _has_fret(profile: InstrumentProfile, fret: int) -> bool:
    """Whether `fret` exists on this profile; fret 0 is the open string."""
    return 0 <= fret <= profile.fret_count


def pitch_at(profile: InstrumentProfile, string: int, fret: int) -> int:
    """The absolute pitch sounded by stopping `string` at `fret`.

    Out-of-range positions raise. A family emitting a note off the fretboard is
    a bug in that family, and a negative string index would otherwise index
    quietly from the top string and produce plausible-looking tablature for the
    wrong instrument.
    """
    if not 0 <= string < len(profile.tuning):
        msg = (
            f"string {string} is out of range for profile {profile.name!r}: "
            f"expected 0 to {len(profile.tuning) - 1}"
        )
        raise ValueError(msg)

    if not _has_fret(profile, fret):
        msg = (
            f"fret {fret} is out of range for profile {profile.name!r}: "
            f"expected 0 to {profile.fret_count}"
        )
        raise ValueError(msg)

    return profile.tuning[string] + fret


def hand_span(frets: Iterable[int]) -> int:
    """How far the fretting hand must reach to play `frets`.

    The distance from the lowest fretted note to the highest, which is the
    quantity both playability bounds are stated in: `position_span` above, and
    §10's `[session] max_fret_span` for exercises that shift deliberately.

    **Open strings do not count.** Fret 0 is sounded by the plucking hand while
    the fretting hand stays where it is, so an open string neither extends the
    reach nor pins it to the nut: the classic A minor pentatonic box is the
    open A against frets 3, 5 and 7, which is one position plus an open string
    and not an eight-fret stretch. A passage of open strings alone asks nothing
    of the hand at all, and answers 0.
    """
    fretted = [fret for fret in frets if fret > 0]
    if not fretted:
        return 0
    return max(fretted) - min(fretted)


def positions(profile: InstrumentProfile, pitch: int) -> list[tuple[int, int]]:
    """Every (string, fret) that sounds `pitch`, ordered from the lowest string.

    A pitch the instrument cannot reach yields an empty list rather than an
    error: "this profile cannot play that note" is an ordinary answer that the
    validity gate acts on, not a failure.
    """
    return [
        (string, pitch - open_pitch)
        for string, open_pitch in enumerate(profile.tuning)
        if _has_fret(profile, pitch - open_pitch)
    ]
