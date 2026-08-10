"""Load and validate `config.toml` (spec §10).

The configuration file is the interface: there is no GUI and no flag for most
of what is tunable here. That makes this module the place where a typo either
becomes a loud failure or becomes a silently different practice sheet.

§13 states the contract, and every rejection below is one of its rows:

* **A malformed or misspelled key fails at load, naming the exact key and its
  accepted values, and never falls back to a default.** A misspelled
  `scale_types` entry that quietly dropped to the default pool would produce a
  perfectly plausible sheet that is not the one the user asked for.
* **An explicit tuning that is not strictly ascending is an error naming the
  offending index, never re-sorted** (decision #22). Sorting would shift every
  string index and engrave the wrong instrument convincingly.

"Naming the accepted values" needs an enumerated set to name, and this module
never keeps one of its own: identifier axes are validated against
`vocabulary.accepted(axis)` and range axes against the resolved
`InstrumentProfile`. A hardcoded list here would be a second source of truth
and would drift from the registry the families dispatch on.

Two vocabularies are genuinely local, and both are stated as such below:
`STAVES` (§10's output switch, which is not a sampled axis) and `DEFAULT_TEMPO`
(§7's per-family ranges, which belong to the family modules that do not exist
yet — see the note on that constant).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from itertools import pairwise
from itertools import permutations as _orderings
from typing import TYPE_CHECKING, Any, NoReturn, cast

from melete import vocabulary
from melete.instrument import (
    DEFAULT_PROFILE,
    PROFILES,
    InstrumentProfile,
    resolve_profile,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence
    from pathlib import Path

#: One value of one parameter axis. Identifiers are strings, range-like axes
#: are integers, and the two structured axes — `permutation` and `string_set` —
#: are tuples of integers.
AxisValue = str | int | tuple[int, ...]

#: The staff-mode switch of §10. Not a sampled axis and therefore deliberately
#: absent from `vocabulary`, which enumerates the §7 and §8 parameter axes: it
#: is an output setting, so this module owns it and this is its only spelling.
STAVES: tuple[str, ...] = ("both", "tab", "notation")

#: §7's per-family tempo ranges. Tempo is a per-family default overridable in
#: configuration and is never a sampled axis (decision #20).
#:
#: **This table is on loan.** §7 assigns the default to the *family*, and it
#: lives here only because `families/` does not exist yet (tasks B5–B8). When
#: it does, each family should declare its own range and this table should
#: become a lookup over the family registry rather than a literal — otherwise
#: it is a second source of truth for a value the family owns.
DEFAULT_TEMPO: dict[str, tuple[int, int]] = {
    "chromatic": (60, 80),
    "scales": (80, 100),
    "arpeggios": (80, 100),
    "intervals": (70, 90),
}

DEFAULT_COUNT = 5
DEFAULT_HORIZON = 14
DEFAULT_MAX_NOTES = 96

#: `[pool.rhythm]` is a section of `[pool]` but not a family: rhythm is a
#: cross-cutting modifier (§8, decision #3), so it carries axes but no tempo.
RHYTHM = "rhythm"

#: The shorthand that expands an axis to every value it accepts.
ALL = "all"

_FINGERS = (1, 2, 3, 4)
_TEMPO_BOUNDS = 2
_PITCH_CLASSES = 12
_MAX_OCTAVES = 3
_SMALLEST_INTERVAL = 2
_LARGEST_INTERVAL = 10


class ConfigError(ValueError):
    """A configuration that cannot be loaded.

    A `ValueError`, because that is what an invalid value is and what the
    dataclass validation in `instrument` already raises; a distinct type,
    because the CLI prints these to a user rather than as a traceback.
    """


# --------------------------------------------------------------------------
# The public shape
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class OutputConfig:
    """§10's `[output]`: what gets engraved."""

    staves: str
    key_signatures: bool


@dataclass(frozen=True)
class SessionConfig:
    """§10's `[session]`: how many exercises, and the bounds around them.

    `shape` is the declared mix of families (§9). Left unset it is `None`
    rather than an empty mapping, because "no shape" means *weight the
    families instead* and an empty mapping would read as "no exercises".
    """

    count: int
    horizon: int
    max_notes: int
    shape: Mapping[str, int] | None


@dataclass(frozen=True)
class FamilyPool:
    """One `[pool.<family>]` section: the candidate values §9 samples from.

    `values` is keyed by the *singular* axis name the selector samples —
    `scale_type`, not `scale_types` — so a pool entry and a session-log entry
    name the same axis. An axis the user did not configure is absent rather
    than defaulted: the pool is what the configuration says, and nothing else.
    """

    family: str
    tempo: tuple[int, int]
    values: Mapping[str, tuple[AxisValue, ...]]


@dataclass(frozen=True)
class RhythmPool:
    """`[pool.rhythm]`: §8's four axes, and no tempo (see `RHYTHM`)."""

    values: Mapping[str, tuple[AxisValue, ...]]


@dataclass(frozen=True)
class Config:
    """A validated configuration. Every field is resolved, never raw TOML."""

    instrument: InstrumentProfile
    output: OutputConfig
    session: SessionConfig
    pool: Mapping[str, FamilyPool]
    rhythm: RhythmPool


# --------------------------------------------------------------------------
# Primitive validation. Every message names the key it came from.
# --------------------------------------------------------------------------


def _fail(key: str, problem: str, accepted: Iterable[object] | None = None) -> NoReturn:
    """Raise naming the exact key, and its accepted values where there is a set."""
    message = f"{key}: {problem}"
    if accepted is not None:
        message += f"; accepted: {list(accepted)}"
    raise ConfigError(message)


def _reject_unknown(where: str, table: Mapping[str, Any], known: Iterable[str]) -> None:
    """Fail on any key the section does not define.

    §13's "never fall back to a default for a misspelled key" is enforced here
    rather than per key: a key nobody reads is indistinguishable from a
    misspelling of one that is read.
    """
    known = sorted(known)
    unknown = sorted(set(table) - set(known))
    if unknown:
        _fail(where, f"unrecognized key(s) {unknown}", known)


def _table(key: str, raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        _fail(key, f"expected a table, got {raw!r}")
    return cast("dict[str, Any]", raw)


def _string(key: str, raw: object) -> str:
    if not isinstance(raw, str):
        _fail(key, f"expected a string, got {raw!r}")
    return raw


def _boolean(key: str, raw: object) -> bool:
    if not isinstance(raw, bool):
        _fail(key, f"expected true or false, got {raw!r}")
    return raw


def _integer(key: str, raw: object) -> int:
    # `bool` is a subclass of `int`: `count = true` would otherwise load as 1.
    if isinstance(raw, bool) or not isinstance(raw, int):
        _fail(key, f"expected an integer, got {raw!r}")
    return raw


def _positive(key: str, raw: object) -> int:
    value = _integer(key, raw)
    if value < 1:
        _fail(key, f"expected a positive integer, got {value}")
    return value


def _list(key: str, raw: object) -> list[Any]:
    if not isinstance(raw, list):
        _fail(key, f"expected a list, got {raw!r}")
    return raw


# --------------------------------------------------------------------------
# Parameter axes
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Axis:
    """One tunable axis of one pool section.

    `key` is the plural key written in TOML; `name` is the singular axis the
    selector samples. `universe` enumerates every accepted value — it is what
    `"all"` expands to and what an unknown value is reported against — and is
    `None` for axes whose validity is structural rather than enumerable.
    """

    key: str
    name: str
    element: Callable[[InstrumentProfile, str, object], AxisValue]
    universe: Callable[[InstrumentProfile], tuple[AxisValue, ...]] | None


def _identifier(_profile: InstrumentProfile, key: str, raw: object) -> AxisValue:
    """One registry identifier.

    Integers are accepted and stringified because `string_skip`'s identifiers
    are the digit strings `"0"`, `"1"` and `"2"` while TOML yields integers.
    Nothing is trusted by that conversion: the value still has to be in the
    axis's universe, so `scale_types = [3]` is rejected like any other unknown.
    """
    if isinstance(raw, bool) or not isinstance(raw, str | int):
        _fail(key, f"expected an identifier, got {raw!r}")
    return str(raw)


def _number(_profile: InstrumentProfile, key: str, raw: object) -> AxisValue:
    return _integer(key, raw)


def _permutation(_profile: InstrumentProfile, key: str, raw: object) -> AxisValue:
    """One ordering of the four fretting fingers, as written in TOML."""
    entries = _list(key, raw)
    return tuple(_integer(f"{key}[{index}]", entry) for index, entry in enumerate(entries))


def _string_set(profile: InstrumentProfile, key: str, raw: object) -> AxisValue:
    """A subset of the instrument's strings, low to high.

    Validated structurally rather than against an enumeration: every non-empty
    subset of six strings is sixty-three values, and an error message listing
    them is not one anybody could read. Naming the profile's index range *is*
    naming the accepted values here, which is why §13's registry deliberately
    excludes range-like axes.

    Strictly ascending for the same reason a tuning is (decision #22): the
    order of the indices is the instrument.
    """
    entries = _list(key, raw)
    indices = tuple(_integer(f"{key}[{index}]", entry) for index, entry in enumerate(entries))
    if not indices:
        _fail(key, "is empty; a string set names at least one string")

    strings = range(len(profile.tuning))
    for position, index in enumerate(indices):
        if index not in strings:
            _fail(
                f"{key}[{position}]",
                f"string index {index} is out of range for profile {profile.name!r}",
                strings,
            )
    for position, (lower, higher) in enumerate(pairwise(indices), start=1):
        if higher <= lower:
            _fail(
                f"{key}[{position}]",
                f"string indices must be strictly ascending: {higher} does not exceed {lower}",
            )
    return indices


def _registry(key: str, axis: str) -> _Axis:
    """An axis whose accepted values are `vocabulary`'s, and only ever those.

    The axis name and the sampled name are the same word by construction —
    the registry's axes are §7's and §8's axes — so only the plural TOML
    spelling is given separately.

    The registry is read once, at import, so an axis this module names but
    `vocabulary` does not have fails on import rather than on the first
    configuration that happens to set that key.
    """
    values: tuple[AxisValue, ...] = tuple(vocabulary.accepted(axis))

    def universe(_profile: InstrumentProfile) -> tuple[AxisValue, ...]:
        return values

    return _Axis(key=key, name=axis, element=_identifier, universe=universe)


def _numeric(
    key: str,
    name: str,
    bounds: Callable[[InstrumentProfile], range],
) -> _Axis:
    """An axis validated numerically, against the spec or the active profile."""

    def universe(profile: InstrumentProfile) -> tuple[AxisValue, ...]:
        return tuple(bounds(profile))

    return _Axis(key=key, name=name, element=_number, universe=universe)


def _all_permutations(_profile: InstrumentProfile) -> tuple[AxisValue, ...]:
    return tuple(_orderings(_FINGERS))


# §7's axis columns, one `_Axis` per axis, shared between the families that
# name the same axis. `range_octaves` is spelled `octaves` in TOML because
# that is what §10's example writes.
_ROOT = _numeric("roots", "root", lambda _profile: range(_PITCH_CLASSES))
_OCTAVES = _numeric("octaves", "range_octaves", lambda _profile: range(1, _MAX_OCTAVES + 1))
_INTERVAL = _numeric(
    "intervals",
    "interval",
    lambda _profile: range(_SMALLEST_INTERVAL, _LARGEST_INTERVAL + 1),
)
_START_STRING = _numeric("start_strings", "start_string", lambda p: range(len(p.tuning)))
_SPAN = _numeric("spans", "span", lambda p: range(1, len(p.tuning) + 1))
_START_FRET = _numeric("start_frets", "start_fret", lambda p: range(p.fret_count + 1))

_PERMUTATION = _Axis("permutations", "permutation", _permutation, _all_permutations)
_STRING_SET = _Axis("string_sets", "string_set", _string_set, None)

_SCALE_TYPE = _registry("scale_types", "scale_type")
_QUALITY = _registry("qualities", "quality")
_INVERSION = _registry("inversions", "inversion")
_TRAVERSAL = _registry("traversals", "traversal")
_PATTERN = _registry("patterns", "pattern")
_DIRECTION = _registry("directions", "direction")
_STRING_TRAVERSAL = _registry("string_traversals", "string_traversal")
_SHIFT = _registry("shifts", "shift")
_CONTEXT = _registry("contexts", "context")
_STRING_SKIP = _registry("string_skips", "string_skip")

_SUBDIVISION = _registry("subdivisions", "subdivision")
_TIME_SIGNATURE = _registry("time_signatures", "time_signature")
_ACCENT_PATTERN = _registry("accent_patterns", "accent_pattern")
_NOTE_VALUE_PATTERN = _registry("note_value_patterns", "note_value_pattern")

#: §7's parameter table, family by family. The keys are the families
#: `vocabulary` enumerates — a test asserts that, so a family added to the
#: registry without a pool here fails loudly rather than silently losing its
#: tuning surface.
_AXES_BY_FAMILY: dict[str, tuple[_Axis, ...]] = {
    "chromatic": (
        _PERMUTATION,
        _START_STRING,
        _START_FRET,
        _DIRECTION,
        _STRING_TRAVERSAL,
        _SHIFT,
        _SPAN,
    ),
    "scales": (_ROOT, _SCALE_TYPE, _TRAVERSAL, _STRING_SET, _PATTERN, _OCTAVES, _DIRECTION),
    "arpeggios": (
        _ROOT,
        _QUALITY,
        _INVERSION,
        _TRAVERSAL,
        _STRING_SET,
        _PATTERN,
        _OCTAVES,
        _DIRECTION,
    ),
    "intervals": (_INTERVAL, _CONTEXT, _STRING_SKIP, _STRING_SET, _DIRECTION, _PATTERN),
}

#: §8's four axes. Rhythm is one modifier over every family, so it has one
#: pool rather than one per family.
_RHYTHM_AXES: tuple[_Axis, ...] = (
    _SUBDIVISION,
    _TIME_SIGNATURE,
    _ACCENT_PATTERN,
    _NOTE_VALUE_PATTERN,
)


def _axis_values(
    axis: _Axis,
    profile: InstrumentProfile,
    key: str,
    raw: object,
) -> tuple[AxisValue, ...]:
    """Every candidate value of one axis, validated and in the written order."""
    universe = None if axis.universe is None else axis.universe(profile)

    if raw == ALL:
        if universe is None:
            _fail(key, f'has no "{ALL}" shorthand; list the values explicitly')
        return universe

    entries = _list(key, raw)
    if not entries:
        _fail(key, "is empty; an axis with no candidate values cannot be sampled")

    values: list[AxisValue] = []
    for index, entry in enumerate(entries):
        element_key = f"{key}[{index}]"
        value = axis.element(profile, element_key, entry)
        if universe is not None and value not in universe:
            _fail(element_key, f"unknown value {value!r}", universe)
        values.append(value)
    return tuple(values)


def _pool_values(
    axes: Sequence[_Axis],
    profile: InstrumentProfile,
    where: str,
    section: Mapping[str, Any],
) -> dict[str, tuple[AxisValue, ...]]:
    return {
        axis.name: _axis_values(axis, profile, f"{where}.{axis.key}", section[axis.key])
        for axis in axes
        if axis.key in section
    }


# --------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------


def _instrument(raw: object) -> InstrumentProfile:
    section = _table("instrument", raw)
    _reject_unknown("instrument", section, ("profile",))
    profile = section.get("profile", DEFAULT_PROFILE)

    if isinstance(profile, str):
        try:
            return resolve_profile(profile)
        except KeyError as exc:
            msg = (
                f"instrument.profile: unknown built-in profile {profile!r}. An explicit "
                f"tuning is written as a table with name, tuning and fret_count; "
                f"accepted built-ins: {sorted(PROFILES)}"
            )
            raise ConfigError(msg) from exc

    if isinstance(profile, dict):
        return _explicit_profile(cast("dict[str, Any]", profile))

    _fail(
        "instrument.profile",
        f"expected a built-in name or an explicit tuning table, got {profile!r}",
        sorted(PROFILES),
    )


#: Why each key of an explicit profile is required. `fret_count` is the one
#: users will want to omit, and §5 is explicit that it is never inferred.
_EXPLICIT_PROFILE_KEYS = {
    "name": "an explicit profile is named, so the cover page and session log can identify it",
    "tuning": "absolute pitches, low to high; index 0 is the lowest string (§5)",
    "fret_count": (
        "the fret count decides which specifications are valid, therefore the candidate "
        "pool, therefore the draw, so it is declared and never inferred (§5)"
    ),
}


def _explicit_profile(table: Mapping[str, Any]) -> InstrumentProfile:
    """Build a profile from `{ name, tuning, fret_count }`.

    The ordering and range rules belong to `InstrumentProfile.__post_init__`,
    which already raises naming the offending index. They are not repeated
    here — a second copy would be a second source of truth for the rule
    decision #22 turns on. What this does add is the configuration key, so the
    message says *where in the file* to look as well as what is wrong.
    """
    _reject_unknown("instrument.profile", table, _EXPLICIT_PROFILE_KEYS)
    for key, reason in _EXPLICIT_PROFILE_KEYS.items():
        if key not in table:
            _fail(f"instrument.profile.{key}", f"is required — {reason}")

    name = _string("instrument.profile.name", table["name"])
    pitches = _list("instrument.profile.tuning", table["tuning"])
    tuning = tuple(
        _integer(f"instrument.profile.tuning[{index}]", pitch)
        for index, pitch in enumerate(pitches)
    )
    fret_count = _integer("instrument.profile.fret_count", table["fret_count"])

    try:
        return InstrumentProfile(name=name, tuning=tuning, fret_count=fret_count)
    except ValueError as exc:
        msg = f"instrument.profile: {exc}"
        raise ConfigError(msg) from exc


def _output(raw: object) -> OutputConfig:
    section = _table("output", raw)
    _reject_unknown("output", section, ("staves", "key_signatures"))

    staves = _string("output.staves", section.get("staves", STAVES[0]))
    if staves not in STAVES:
        _fail("output.staves", f"unknown staff mode {staves!r}", STAVES)

    return OutputConfig(
        staves=staves,
        key_signatures=_boolean("output.key_signatures", section.get("key_signatures", False)),
    )


def _shape(raw: object) -> dict[str, int]:
    table = _table("session.shape", raw)
    _reject_unknown("session.shape", table, vocabulary.accepted("family"))
    if not table:
        _fail("session.shape", "declares no families; omit it to weight families instead (§9)")
    return {family: _positive(f"session.shape.{family}", count) for family, count in table.items()}


def _session(raw: object) -> SessionConfig:
    section = _table("session", raw)
    _reject_unknown("session", section, ("count", "horizon", "max_notes", "shape"))

    shape = _shape(section["shape"]) if "shape" in section else None
    count = _positive("session.count", section["count"]) if "count" in section else None

    if shape is not None:
        declared = sum(shape.values())
        if count is None:
            count = declared
        elif count != declared:
            _fail(
                "session.count",
                f"is {count} but session.shape declares {declared} exercises. One of them is "
                f"wrong and guessing which would silently generate the wrong session",
            )
    elif count is None:
        count = DEFAULT_COUNT

    return SessionConfig(
        count=count,
        horizon=_positive("session.horizon", section.get("horizon", DEFAULT_HORIZON)),
        max_notes=_positive("session.max_notes", section.get("max_notes", DEFAULT_MAX_NOTES)),
        shape=shape,
    )


def _pool(raw: object, profile: InstrumentProfile) -> tuple[dict[str, FamilyPool], RhythmPool]:
    section = _table("pool", raw)
    families = vocabulary.accepted("family")
    _reject_unknown("pool", section, [*families, RHYTHM])

    pools: dict[str, FamilyPool] = {}
    for family in families:
        where = f"pool.{family}"
        axes = _AXES_BY_FAMILY[family]
        table = _table(where, section.get(family, {}))
        _reject_unknown(where, table, [*(axis.key for axis in axes), "tempo"])
        tempo = (
            _tempo(f"{where}.tempo", table["tempo"]) if "tempo" in table else DEFAULT_TEMPO[family]
        )
        pools[family] = FamilyPool(
            family=family,
            tempo=tempo,
            values=_pool_values(axes, profile, where, table),
        )

    where = f"pool.{RHYTHM}"
    table = _table(where, section.get(RHYTHM, {}))
    _reject_unknown(where, table, [axis.key for axis in _RHYTHM_AXES])
    rhythm = RhythmPool(values=_pool_values(_RHYTHM_AXES, profile, where, table))

    return pools, rhythm


def _tempo(key: str, raw: object) -> tuple[int, int]:
    """A `[low, high]` beats-per-minute range (§7, decision #20)."""
    bounds = _list(key, raw)
    if len(bounds) != _TEMPO_BOUNDS:
        _fail(key, f"expected a two-element range like [80, 100], got {raw!r}")
    low = _positive(f"{key}[0]", bounds[0])
    high = _positive(f"{key}[1]", bounds[1])
    if low > high:
        _fail(key, f"lower bound {low} exceeds upper bound {high}")
    return (low, high)


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------


def load_string(text: str) -> Config:
    """Load a configuration from TOML text.

    The unit-testable half of `load`, and the form every test in this suite
    uses: the validation rules are what matter, and none of them are about
    files.
    """
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        msg = f"the configuration is not valid TOML: {exc}"
        raise ConfigError(msg) from exc

    _reject_unknown("config", raw, ("instrument", "output", "session", "pool"))

    profile = _instrument(raw.get("instrument", {}))
    pools, rhythm = _pool(raw.get("pool", {}), profile)
    return Config(
        instrument=profile,
        output=_output(raw.get("output", {})),
        session=_session(raw.get("session", {})),
        pool=pools,
        rhythm=rhythm,
    )


def load(path: Path) -> Config:
    """Load and validate the configuration at `path`.

    A missing or unreadable file names the path. It is not a recoverable
    condition and there is no default configuration to fall back on: the file
    *is* the interface (§3).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"cannot read the configuration at {path}: {exc}"
        raise ConfigError(msg) from exc

    try:
        return load_string(text)
    except ConfigError as exc:
        msg = f"{path}: {exc}"
        raise ConfigError(msg) from exc
