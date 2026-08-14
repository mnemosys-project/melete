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

Everything this module needs to name is read from whoever owns it —
identifiers from `vocabulary`, ranges from the `InstrumentProfile`, and the
per-family tempo defaults from `families.REGISTRY`, because §7 assigns the
tempo range to the family (decision #20).

Importing `families` is safe in exactly one direction: no family imports
`config`, and none may, since a family is a pure `params -> Score` function
that knows nothing about how its parameters were configured.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, replace
from itertools import permutations as _orderings
from typing import TYPE_CHECKING, Any, NoReturn, cast

from melete import vocabulary
from melete.families import REGISTRY
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
#: are integers, and the structured `permutation` axis is a tuple of integers.
AxisValue = str | int | tuple[int, ...]

DEFAULT_COUNT = 5
DEFAULT_HORIZON = 14
DEFAULT_MAX_NOTES = 96

#: How far one exercise may make the fretting hand travel, lowest fretted note
#: to highest (§9's validity gate; issue #57).
#:
#: **One octave of neck.** Shifting is legitimate — `chromatic` with
#: `shift = fret_per_cycle` is *supposed* to climb, and §10's example pool tops
#: it out at nine frets — so this bound is deliberately looser than a position.
#: What it refuses is an exercise that covers more of the neck than the neck's
#: own repeating unit: every shape recurs an octave higher, so a span past
#: twelve frets contains a repetition of itself, and on a 34-inch scale that is
#: most of the reachable board in a fourteen-note exercise. The sheet that
#: raised issue #57 held spans of 15 and 17 frets, which nothing had decided
#: were acceptable.
DEFAULT_MAX_FRET_SPAN = 12

#: `[pool.rhythm]` is a section of `[pool]` but not a family: rhythm is a
#: cross-cutting modifier (§8, decision #3), so it carries axes but no tempo.
RHYTHM = "rhythm"

#: The shorthand that expands an axis to every value it accepts.
ALL = "all"

_FINGERS = (1, 2, 3, 4)
_TEMPO_BOUNDS = 2
_PITCH_CLASSES = 12
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
class SessionConfig:
    """§10's `[session]`: how many exercises, and the bounds around them.

    `shape` is the declared mix of families (§9). Left unset it is `None`
    rather than an empty mapping, because "no shape" means *weight the
    families instead* and an empty mapping would read as "no exercises".

    `max_notes` and `max_fret_span` are the two bounds §9's gate applies beyond
    the instrument profile — how long an exercise is, and how far it makes the
    hand travel. Both are here rather than in `[pool.*]` because they bound the
    *session*, and both are checked through the one gate, because a cycle that
    is too long and a reach no hand has are the same kind of failure.
    """

    count: int
    horizon: int
    max_notes: int
    max_fret_span: int
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
    `"all"` expands to and what an unknown value is reported against.
    """

    key: str
    name: str
    element: Callable[[InstrumentProfile, str, object], AxisValue]
    universe: Callable[[InstrumentProfile], tuple[AxisValue, ...]]


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
# name the same axis.
_ROOT = _numeric("roots", "root", lambda _profile: range(_PITCH_CLASSES))
_INTERVAL = _numeric(
    "intervals",
    "interval",
    lambda _profile: range(_SMALLEST_INTERVAL, _LARGEST_INTERVAL + 1),
)
_START_STRING = _numeric("start_strings", "start_string", lambda p: range(len(p.tuning)))
_SPAN = _numeric("spans", "span", lambda p: range(1, len(p.tuning) + 1))
_START_FRET = _numeric("start_frets", "start_fret", lambda p: range(p.fret_count + 1))

_PERMUTATION = _Axis("permutations", "permutation", _permutation, _all_permutations)

_SCALE_TYPE = _registry("scale_types", "scale_type")
_QUALITY = _registry("qualities", "quality")
_INVERSION = _registry("inversions", "inversion")
_TRAVERSAL = _registry("traversals", "traversal")
_PATTERN = _registry("patterns", "pattern")
_STRING_TRAVERSAL = _registry("string_traversals", "string_traversal")
_SHIFT = _registry("shifts", "shift")
_CONTEXT = _registry("contexts", "context")
_STRING_SKIP = _registry("string_skips", "string_skip")

_ACCENT_PATTERN = _registry("accent_patterns", "accent_pattern")
_NOTE_VALUE_PATTERN = _registry("note_value_patterns", "note_value_pattern")

#: §7's parameter table, family by family. The keys are the families
#: `vocabulary` enumerates — a test asserts that, so a family added to the
#: registry without a pool here fails loudly rather than silently losing its
#: tuning surface.
#:
#: The axes of each entry are the axes its family reads, and a second test
#: asserts *that* against `families.REGISTRY[...].axes` rather than against a
#: list of its own. What lives here and cannot live in the family is the
#: configuration surface of an axis — its plural TOML key, how a written value
#: is read, and what set it is accepted against — so this table is a mapping
#: from the family's axes onto that surface, never a second opinion about which
#: axes the family has. It was a second opinion once: `intervals` was missing
#: `root` and `scale_type` here, which made every specification drawn from this
#: pool one the family would reject.
_AXES_BY_FAMILY: dict[str, tuple[_Axis, ...]] = {
    "chromatic": (
        _PERMUTATION,
        _START_STRING,
        _START_FRET,
        _STRING_TRAVERSAL,
        _SHIFT,
        _SPAN,
    ),
    "scales": (_ROOT, _SCALE_TYPE, _TRAVERSAL, _PATTERN),
    "arpeggios": (
        _ROOT,
        _QUALITY,
        _INVERSION,
        _PATTERN,
    ),
    # `root` is read in both of §7's contexts and `scale_type` only in the
    # diatonic one, which is what "diatonic within root + scale" means: the
    # column names two axes rather than one value.
    "intervals": (
        _INTERVAL,
        _CONTEXT,
        _ROOT,
        _SCALE_TYPE,
        _STRING_SKIP,
        _PATTERN,
    ),
}

#: §8's sampled rhythm axes. Rhythm is one modifier over every family, so it has
#: one pool rather than one per family. The `subdivision` and `time_signature`
#: axes were retired (#119) once the layout fitter took over deriving the meter
#: and subdivision (#118); `_reject_unknown` now refuses those keys under
#: `[pool.rhythm]` like any other unknown one.
_RHYTHM_AXES: tuple[_Axis, ...] = (
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
    universe = axis.universe(profile)

    if raw == ALL:
        return universe

    entries = _list(key, raw)
    if not entries:
        _fail(key, "is empty; an axis with no candidate values cannot be sampled")

    values: list[AxisValue] = []
    for index, entry in enumerate(entries):
        element_key = f"{key}[{index}]"
        value = axis.element(profile, element_key, entry)
        if value not in universe:
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
    """The active profile, with §10's hand-span override applied (issue #57).

    `position_span` sits beside `profile` rather than inside it so that it
    reaches a built-in and an explicit tuning by the same route: a player whose
    hand disagrees with `DEFAULT_POSITION_SPAN` should not have to write out a
    whole tuning to say so.
    """
    section = _table("instrument", raw)
    _reject_unknown("instrument", section, ("profile", "position_span"))
    profile = _profile(section.get("profile", DEFAULT_PROFILE))
    if "position_span" not in section:
        return profile
    return replace(
        profile,
        position_span=_positive("instrument.position_span", section["position_span"]),
    )


def _profile(profile: object) -> InstrumentProfile:
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


def _shape(raw: object) -> dict[str, int]:
    table = _table("session.shape", raw)
    _reject_unknown("session.shape", table, vocabulary.accepted("family"))
    if not table:
        _fail("session.shape", "declares no families; omit it to weight families instead (§9)")
    return {family: _positive(f"session.shape.{family}", count) for family, count in table.items()}


def _session(raw: object) -> SessionConfig:
    section = _table("session", raw)
    _reject_unknown("session", section, ("count", "horizon", "max_notes", "max_fret_span", "shape"))

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
        max_fret_span=_positive(
            "session.max_fret_span",
            section.get("max_fret_span", DEFAULT_MAX_FRET_SPAN),
        ),
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
            _tempo(f"{where}.tempo", table["tempo"])
            if "tempo" in table
            else REGISTRY[family].default_tempo_range
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

    _reject_unknown("config", raw, ("instrument", "session", "pool"))

    profile = _instrument(raw.get("instrument", {}))
    pools, rhythm = _pool(raw.get("pool", {}), profile)
    return Config(
        instrument=profile,
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
