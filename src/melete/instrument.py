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
"""

from dataclasses import dataclass
from itertools import pairwise

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


@dataclass(frozen=True)
class InstrumentProfile:
    """One instrument: a name, a tuning low to high, and a declared fret count.

    `tuning` holds absolute pitches with index 0 as the *lowest* string. The
    ordering is validated rather than repaired: sorting a malformed tuning
    would shift every string index and engrave the wrong instrument
    convincingly, which is precisely the silent failure the design forbids.
    """

    name: str
    tuning: tuple[int, ...]
    fret_count: int

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
