"""The session log and replay — `sessions/YYYY-MM-DD/session.json` (spec §12).

One file per day, holding the seed, the configuration hash, the full parameter
dictionary of every exercise, and the resolved weight inputs that produced the
draw. It is two things at once: the history §9's selector reads back, and the
record decision #14 makes **sufficient for exact replay on its own**.

## Why the file is self-sufficient (decision #14)

A seed alone cannot reproduce a day. Selection weights every candidate by how
many sessions have passed since it was last used, and that history is not a
function of the seed: replaying a seed against today's log computes different
weights than the original run did, so the sheet would come back different, with
nothing to say it had diverged. §9 splits the two operations for exactly that
reason — `--seed` fixes the draw against whatever history exists *now*, and
`replay` reproduces a past day.

So `replay` re-derives nothing. The day's exercises were recorded in full when
they were drawn, and reading them back is the reproduction; the recorded seed
and weight inputs sit beside them as the account of *why* that draw happened,
which is what makes a past sheet auditable rather than merely regenerable. Any
scheme that re-ran the draw would need the configuration and the log as they
were, and would silently produce a different sheet the day either one changed —
which is the failure this whole module exists to rule out.

## The serialization trap

JSON has no tuples. `selection.axis_key` labels a `string_set` of `(0, 1, 2, 3)`
as `"0-1-2-3"`, but the list JSON hands back labels as `"[0, 1, 2, 3]"` — a
different key for the same value. A history restored as lists would therefore
stop counting its string sets and permutations as uses of the pool values they
were drawn from, every distance would read as "never used", and the recency
weighting would quietly degrade into the uniform draw §9 exists to replace. It
would not raise. The sheets would just get less varied.

`_axis_value` is the fix and it is deliberately structural rather than a list of
known tuple axes: *every* JSON array comes back as a tuple of integers, so an
axis added later cannot miss the restoration. It is also the only value that
does not survive the round trip — strings and integers return as themselves, and
a `float`, a `bool` or a nested array is a corrupt record rather than a value to
be coerced (a `26.0` labels as `"26.0"`, which is the same silent mislabelling
in a different disguise).

## §13's two rows

**A corrupt entry is a hard error naming the file.** Never a skipped one:
skipping degrades variety invisibly, which is precisely the tuple failure again.
Every message carries the path and the position inside the document, because the
file is hand-editable and the point of the error is to say what to fix.

**An existing session directory is refused** unless `force` is asked for, so a
second run of a day cannot overwrite the record of the first without being told
to.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NoReturn, cast

from melete.selection import ExerciseSpec, WeightInputs

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from melete.config import AxisValue, Config

#: The directory every dated session lives under, relative to the project root.
SESSIONS = "sessions"

#: §12's session log, one per dated directory.
FILENAME = "session.json"

#: The keys a document must carry. Absent any one of them the record is not a
#: session, and guessing a default for the missing half would be §13's "never
#: fall back to a default" applied to the wrong file.
_REQUIRED = ("config_hash", "date", "exercises", "instrument", "seed", "weight_inputs")

_EXERCISE_KEYS = ("family", "params")

#: How many bytes of the seed material become the seed. Eight is a 64-bit
#: integer: wide enough that two days never collide in practice, narrow enough
#: that the number in the file is one a person can read back and retype.
_SEED_BYTES = 8


class SessionError(ValueError):
    """A session record that cannot be read.

    A `ValueError`, because a corrupt document is an invalid value; a distinct
    type, because §13 has the CLI print these to a user rather than as a
    traceback, and because it is what a caller catches around a whole log.
    """


@dataclass(frozen=True)
class Session:
    """One day's record: §12's `session.json`, as data.

    `weight_inputs` is one entry per exercise, parallel to `exercises`, because
    the within-session pushdown means the second slot of a day was drawn against
    different distances than the first (§9). `instrument` is the profile's name
    rather than the profile, which is what §10 already promises the log
    identifies it by.
    """

    date: datetime.date
    instrument: str
    seed: int
    config_hash: str
    exercises: tuple[ExerciseSpec, ...]
    weight_inputs: tuple[WeightInputs, ...]


# --------------------------------------------------------------------------
# The seed, and the configuration it is derived from (§9)
# --------------------------------------------------------------------------


def _jsonable(value: AxisValue) -> str | int | list[int]:
    """One axis value as JSON holds it: a tuple becomes a list, and back again."""
    if isinstance(value, tuple):
        return list(value)
    return value


def _fingerprint(config: Config) -> dict[str, Any]:
    """Everything about the configuration that decides *which* exercises are drawn.

    `[output]` is deliberately absent. It selects how a drawn exercise is
    engraved — the staves, the key signatures — and folding it in would fold it
    into the seed, so changing the staff mode would hand back a different set of
    exercises with no indication that it had. Everything else is in, because
    everything else moves the draw: the instrument decides which specifications
    are valid, `[session]` decides how many and of what, and `[pool]` is the
    candidate set itself.

    Candidate lists keep the order they were written in. That order is not
    cosmetic — a weighted draw walks the candidates in sequence — so two pools
    holding the same values in a different order are two different
    configurations and hash differently.
    """
    return {
        "instrument": {
            "name": config.instrument.name,
            "tuning": list(config.instrument.tuning),
            "fret_count": config.instrument.fret_count,
        },
        "session": {
            "count": config.session.count,
            "horizon": config.session.horizon,
            "max_notes": config.session.max_notes,
            "shape": None if config.session.shape is None else dict(config.session.shape),
        },
        "pool": {
            family: {
                "tempo": list(pool.tempo),
                "values": {
                    axis: [_jsonable(value) for value in values]
                    for axis, values in pool.values.items()
                },
            }
            for family, pool in config.pool.items()
        },
        "rhythm": {
            axis: [_jsonable(value) for value in values]
            for axis, values in config.rhythm.values.items()
        },
    }


def config_hash(config: Config) -> str:
    """A stable digest of the configuration that produced a draw (§9, §12).

    SHA-256 of the canonical JSON form, rather than Python's `hash`, because it
    has to be the same number tomorrow and on another machine: `hash` is salted
    per process and would make the seed — and therefore the day's exercises —
    depend on which interpreter happened to run.
    """
    canonical = json.dumps(_fingerprint(config), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def seed_for(session_date: datetime.date, digest: str) -> int:
    """§9's seed: the date plus a hash of the configuration.

    The date makes each day its own draw; the configuration hash makes a day
    re-generated after the pool was edited a different draw rather than the same
    one against a pool that no longer means the same thing.
    """
    material = f"{session_date.isoformat()}:{digest}".encode()
    return int.from_bytes(hashlib.sha256(material).digest()[:_SEED_BYTES], "big")


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


def directory(root: Path, session_date: datetime.date) -> Path:
    """Where one day's output lives: `<root>/sessions/YYYY-MM-DD` (§12)."""
    return root / SESSIONS / session_date.isoformat()


def record(
    session_date: datetime.date,
    config: Config,
    picks: Sequence[tuple[ExerciseSpec, WeightInputs]],
    seed: int,
) -> Session:
    """The `Session` a draw produced, ready to be written.

    `picks` is `selection.select`'s return value unchanged, so nothing between
    the draw and the file can drop the weight inputs from the specification they
    belong to.
    """
    return Session(
        date=session_date,
        instrument=config.instrument.name,
        seed=seed,
        config_hash=config_hash(config),
        exercises=tuple(spec for spec, _inputs in picks),
        weight_inputs=tuple(inputs for _spec, inputs in picks),
    )


def _document(session: Session) -> dict[str, Any]:
    return {
        "date": session.date.isoformat(),
        "instrument": session.instrument,
        "seed": session.seed,
        "config_hash": session.config_hash,
        "exercises": [
            {
                "family": spec.family,
                "params": {axis: _jsonable(value) for axis, value in spec.params.items()},
            }
            for spec in session.exercises
        ],
        "weight_inputs": [inputs.distances for inputs in session.weight_inputs],
    }


def write(root: Path, session: Session, *, force: bool = False) -> Path:
    """Write one day's record, refusing to overwrite an existing session (§13).

    Refusing is the whole point: a second run of a day that silently replaced
    the first would destroy the record of the sheet that was actually practised,
    and the log is the history every later draw is weighted against. `force` is
    the explicit ask.

    Indented, key-sorted and newline-terminated because §12 requires the file to
    be human-readable, git-committable and hand-editable: sorting is what keeps
    a diff to the line that changed rather than to whatever order a dictionary
    happened to be built in.
    """
    target = directory(root, session.date)
    if target.exists() and not force:
        msg = (
            f"{target} already exists. Refusing to overwrite the record of a session that has "
            f"already been generated (§13); pass force to replace it."
        )
        raise FileExistsError(msg)

    target.mkdir(parents=True, exist_ok=True)
    text = json.dumps(_document(session), indent=2, sort_keys=True)
    (target / FILENAME).write_text(f"{text}\n", encoding="utf-8")
    return target


# --------------------------------------------------------------------------
# Reading: every failure names the file and the position inside it (§13)
# --------------------------------------------------------------------------


def _corrupt(where: str, problem: str) -> NoReturn:
    raise SessionError(f"{where}: {problem}")


def _mapping(where: str, raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        _corrupt(where, f"expected an object, got {raw!r}")
    return cast("dict[str, Any]", raw)


def _sequence(where: str, raw: object) -> list[Any]:
    if not isinstance(raw, list):
        _corrupt(where, f"expected a list, got {raw!r}")
    return raw


def _text(where: str, raw: object) -> str:
    if not isinstance(raw, str):
        _corrupt(where, f"expected a string, got {raw!r}")
    return raw


def _integer(where: str, raw: object) -> int:
    """An integer, and never a `bool` or a `float`.

    `bool` is a subclass of `int` and `26.0` is not `26` to `axis_key`, so both
    are rejected rather than coerced — a coerced value is a value that labels
    differently from the one that was drawn.

    Nothing here judges the *range* of an axis value: which integers an axis
    accepts is `config`'s question, asked against the pool and the instrument
    profile, and a second opinion about it here would be a second source of
    truth that drifts.
    """
    if isinstance(raw, bool) or not isinstance(raw, int):
        _corrupt(where, f"expected an integer, got {raw!r}")
    return raw


def _whole(where: str, raw: object) -> int:
    """A non-negative integer: a seed and a recency distance are both counts."""
    value = _integer(where, raw)
    if value < 0:
        _corrupt(where, f"expected a non-negative integer, got {value}")
    return value


def _axis_value(where: str, raw: object) -> AxisValue:
    """One parameter value, with JSON's arrays restored to tuples.

    The restoration is the trap this module's docstring opens with: a list and
    the tuple it came from label differently under `axis_key`, so a history left
    as lists silently stops counting.
    """
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        return tuple(_integer(f"{where}[{index}]", item) for index, item in enumerate(raw))
    return _integer(where, raw)


def _exercise(where: str, raw: object) -> ExerciseSpec:
    entry = _mapping(where, raw)
    missing = sorted(set(_EXERCISE_KEYS) - set(entry))
    if missing:
        _corrupt(where, f"is missing required key(s) {missing}")
    params = _mapping(f"{where}.params", entry["params"])
    return ExerciseSpec(
        family=_text(f"{where}.family", entry["family"]),
        params={
            axis: _axis_value(f"{where}.params.{axis}", value) for axis, value in params.items()
        },
    )


def _weight_inputs(where: str, raw: object) -> WeightInputs:
    axes = _mapping(where, raw)
    return WeightInputs(
        distances={axis: _distances(f"{where}.{axis}", values) for axis, values in axes.items()}
    )


def _distances(where: str, raw: object) -> dict[str, int | None]:
    values = _mapping(where, raw)
    return {key: _distance(f"{where}.{key}", value) for key, value in values.items()}


def _distance(where: str, raw: object) -> int | None:
    """Sessions since a value was last used, or `null` for "not inside the horizon"."""
    if raw is None:
        return None
    return _whole(where, raw)


def _date(where: str, raw: object) -> datetime.date:
    text = _text(where, raw)
    try:
        return datetime.date.fromisoformat(text)
    except ValueError as exc:
        msg = f"{where}: is not an ISO date: {text!r}"
        raise SessionError(msg) from exc


def read(session_directory: Path) -> Session:
    """The session recorded in `<session_directory>/session.json`.

    Every failure is a `SessionError` naming the file, because §13 forbids
    skipping a bad entry: a log quietly one session shorter weights every later
    draw wrongly and nothing ever says so.
    """
    path = session_directory / FILENAME
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"{path}: cannot be read: {exc}"
        raise SessionError(msg) from exc

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"{path}: is not valid JSON: {exc}"
        raise SessionError(msg) from exc

    return _session(str(path), raw)


def _session(where: str, raw: object) -> Session:
    document = _mapping(where, raw)
    missing = sorted(set(_REQUIRED) - set(document))
    if missing:
        _corrupt(where, f"is missing required key(s) {missing}")

    exercises = tuple(
        _exercise(f"{where}: exercises[{index}]", entry)
        for index, entry in enumerate(_sequence(f"{where}: exercises", document["exercises"]))
    )
    inputs = tuple(
        _weight_inputs(f"{where}: weight_inputs[{index}]", entry)
        for index, entry in enumerate(
            _sequence(f"{where}: weight_inputs", document["weight_inputs"])
        )
    )
    if len(inputs) != len(exercises):
        _corrupt(
            where,
            f"records {len(exercises)} exercises but {len(inputs)} sets of weight inputs. §9 "
            f"draws each slot against its own distances, so there is one set of weight inputs "
            f"per exercise",
        )

    return Session(
        date=_date(f"{where}: date", document["date"]),
        instrument=_text(f"{where}: instrument", document["instrument"]),
        seed=_whole(f"{where}: seed", document["seed"]),
        config_hash=_text(f"{where}: config_hash", document["config_hash"]),
        exercises=exercises,
        weight_inputs=inputs,
    )


# --------------------------------------------------------------------------
# The history, and replay
# --------------------------------------------------------------------------


def _dated(entry: Path) -> datetime.date:
    """The date a session directory is named for, or a hard error (§13).

    A directory under `sessions/` that is not named for a date would sort into
    the log at an arbitrary position — after every real session, if the name
    begins with a letter — and displace a real day from the window §9 reads.
    Non-directories are left alone: a session *is* a directory (§12), so a file
    beside one is not a half-written session, and refusing to run because a file
    manager dropped a `.DS_Store` there would be a failure with no defect
    behind it.
    """
    try:
        return datetime.date.fromisoformat(entry.name)
    except ValueError as exc:
        msg = (
            f"{entry}: is not named for a date. Every directory under {SESSIONS}/ is one dated "
            f"session (§12), and a directory that is not would take a real session's place in "
            f"the history §9 weights against"
        )
        raise SessionError(msg) from exc


def history(
    root: Path, count: int, *, exclude: datetime.date | None = None
) -> list[tuple[ExerciseSpec, ...]]:
    """The last `count` sessions, oldest first — the shape `selection.select` reads.

    Oldest first is the order the weighting is defined against: the session
    before this one is at distance 1. A corrupt entry inside the window stops
    the run naming the file rather than being skipped (§13).

    `exclude` drops one date, and the date it drops is the one being generated.
    A day is never part of its own history: regenerating an already-recorded
    day would otherwise weight the draw against the record it is about to
    replace, so the same date against the same configuration would hand back a
    different sheet on every re-run — §9's determinism lost, silently, to a
    file the run itself wrote. Dropped before the window is taken, so the
    replaced day does not also displace a real session from it.
    """
    sessions = root / SESSIONS
    if not sessions.is_dir():
        return []

    every = [(_dated(entry), entry) for entry in sessions.iterdir() if entry.is_dir()]
    dated = sorted(pair for pair in every if pair[0] != exclude)
    recent: list[tuple[ExerciseSpec, ...]] = []
    for on, entry in dated[-count:]:
        logged = read(entry)
        if logged.date != on:
            msg = (
                f"{entry / FILENAME}: records the date {logged.date.isoformat()} but sits in the "
                f"directory for {on.isoformat()}. One of them is wrong, and reading it as either "
                f"would weight every later draw against a day that did not happen"
            )
            raise SessionError(msg)
        recent.append(logged.exercises)
    return recent


def replay(root: Path, session_date: datetime.date) -> Session:
    """A past day, exactly as it was drawn (§9, §14, decision #14).

    Reads that day's record and nothing else — not the configuration, and not
    the surrounding log. Both have moved on since, and both are what a
    re-derivation would silently diverge on: the weights are computed from a
    history that keeps growing, so the same seed against today's log is a
    different sheet. The recorded seed and weight inputs sitting beside the
    recorded exercises are what makes the day auditable as well as reproducible.
    """
    return read(directory(root, session_date))
