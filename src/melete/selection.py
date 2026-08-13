"""Coverage-aware selection — which exercises a session is made of (spec §9).

Drawing uniformly at random treats every specification as a single draw, so
nothing stops three D-rooted exercises landing on one page or a week of nothing
but Dorian. Clumping is what uniform randomness does, and §1 asks for variety
that *feels* varied. This module is the answer: **every parameter is an axis,
and each axis is sampled independently, weighted by recency**.

Independence is the whole mechanism. Roots spread across the chromatic scale on
their own schedule while modes spread on theirs, which is what produces "a mix
of keys and a mix of modes" rather than one lucky draw.

## The weighting (decision #15)

    w(value) = 1.0                                    # never used
    w(value) = max(FLOOR, min(1.0, distance / horizon))

**One expression, with the floor applied last, and never zero.** An earlier
three-rule formulation carried a "used today or yesterday" special case
alongside the ratio and the two disagreed: at distance 0 the ratio yields 0.0
while the special case says 0.05, and at distance 1 the ratio yields ≈0.071, so
0.05 was acting as a ceiling rather than the floor it was described as. Read
with the ratio winning, anything used today weighs 0.0 — impossible, the
opposite of the intent — and because the within-session rule below pushes each
selection onto the history at distance 0, a small pool reaches a state where
every candidate weighs 0.0. A weighted draw over an all-zero vector has no
defined result: `shape = { scales = 3 }` over a two-element `scale_types` pool
hits it on the third slot, on a configuration that is otherwise perfectly legal.

The floor of 0.05 rather than 0.0 is deliberate: a recently used value becomes
unlikely, never impossible. `weight` is the one entry point §9's tunability
requirement names — swapping linear decay for exponential is a change to that
function and to nothing else.

## Within-session diversity

As each exercise is selected its values are pushed onto the history at distance
zero, so the next slot in the same session actively avoids them. D Dorian and D
Phrygian will not appear on the same page.

## Validity is a gate, not a weight

Each sampled specification is realized against the active instrument profile and
checked against `max_notes` (§7, decision #17) and `max_fret_span` (§10, issue
#57). The two session bounds are one gate on purpose: a cycle too long to print
and a reach no hand has are the same kind of failure — a specification that is
legal and useless — and neither is quietly adjusted into something renderable.
The fretboard is checked twice over, because the family checks that a note is
*on* the neck and only this bound checks that a player can get to it. An
unrealizable draw is
resampled up to `MAX_ATTEMPTS` times; exhausting the budget is a loud error that
quotes the family's own account of what could not be satisfied. It is never a
silent fallback and never a clamp: a clamped exercise is a plausible-looking
sheet that is not the one that was drawn, which is the §13 failure mode this
project exists to avoid.

## Determinism and replay (decision #14)

Randomness arrives as an injected `random.Random`; nothing here touches
module-level randomness. The caller seeds it from the date and the configuration
hash. But a seed alone cannot reproduce a day, because the weights are computed
from a session log that keeps growing — so every pick carries the `WeightInputs`
that fed it, and §12's `session.json` records them. Replay reads those recorded
distances rather than recomputing against a log that has moved on.

## Three things §9 left to this module

**A root is a pitch class in the pool and an absolute pitch in the parameters.**
§7 gives the `root` axis twelve pitch classes and the families take an absolute
pitch: `scales.generate` with `root = 9` would ask for A0, three semitones below
the lowest string of a six-string bass, and every draw would be unrealizable.
The pitch class is therefore *realized* at the lowest octave at or above the open
pitch of the string set's lowest string — deterministic, and inside the sampled
string set rather than beside it. Coverage accounting stays on the pitch class,
because that is the axis §7 names: `_coverage_value` reduces a recorded root
modulo an octave before it counts as a use.

**`scale_type` is not coverage-relevant to a chromatic-context `intervals`
draw.** That family reads `scale_type` only in its diatonic branch, so two
chromatic specifications differing only in `scale_type` engrave the same sheet.
Sampling one anyway would credit §9's accounting with variety that does not
exist and would push a scale type down the pool for the next slot without a
single note of it being played. So the axis is not sampled at all in that
branch, does not enter `params`, and is not pushed onto the history —
`_CONDITIONAL_AXES` states the rule and the sampling order guarantees `context`
is drawn first. The recorded `WeightInputs` still carries the axis, because that
is a record of what fed the *draw* including the attempts that were rejected,
and a replay that skipped them would consume the generator differently.

**An axis the family reads and the pool does not configure is a loud error.**
`config` deliberately does not default an unconfigured axis — "the pool is what
the configuration says, and nothing else" — which leaves the choice here, and
defaulting it to the axis's full universe would be this module inventing a
tuning surface that `config` refused to invent. §13 forbids falling back to a
default for a key the user did not write, so the draw stops and names the axis
and the family instead.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from melete import rhythm
from melete.config import DEFAULT_HORIZON, RHYTHM
from melete.families import REGISTRY
from melete.instrument import hand_span
from melete.score import notes

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from random import Random

    from melete.config import AxisValue, Config
    from melete.instrument import InstrumentProfile

#: The lowest weight any candidate can carry (§9). A recently used value becomes
#: unlikely, never impossible: at 0.05 a value drawn today still has one chance
#: in twenty of the weight of one never used, which is what keeps a weighted
#: draw over an exhausted pool defined.
FLOOR = 0.05

#: The axis the family is drawn on when `[session] shape` is unset (§9: "leaving
#: the shape unset weights families instead"). Named because it is the one axis
#: that is not a member of any family's parameter list.
FAMILY = "family"

#: How many times one slot may be resampled before the draw is declared
#: over-constrained (§9, §7's `max_notes`).
#:
#: Measured rather than guessed, by sampling each family independently from a
#: broad pool on `bass6` and realizing every draw (20,000 draws per family):
#:
#: | pool                                        | valid |
#: |---------------------------------------------|-------|
#: | `scales`, broad                             | 0.278 |
#: | `chromatic`, broad                          | 0.347 |
#: | `arpeggios`, broad                          | 0.579 |
#: | `intervals`, broad                          | 0.713 |
#: | `scales`, `three_note_per_string` only      | 0.112 |
#: | `chromatic`, `single_string` only           | 0.168 |
#:
#: The two narrow rows are the constraint that matters: a traversal is only
#: realizable against string sets of one particular size, so a legitimate pool
#: that fixes one can leave nine draws in ten unrealizable. `intervals` is the
#: other known offender — roughly one draw in five is unrealizable over a broad
#: sweep, and a `string_skip` of 2 against three-string sets is unrealizable
#: outright, which is exactly the over-constrained pool this budget exists to
#: report rather than to grind against.
#:
#: 500 attempts puts a pool half as good as the worst measured legitimate one —
#: one valid draw in twenty — at a 7e-12 chance of a spurious failure, while a
#: genuinely impossible pool costs 500 × 35µs ≈ 18ms before it says so.
#:
#: **Re-measured against §10's example pool once the playability bounds were in
#: place** (issue #57), because a bound that rejects more draws is a bound that
#: could have invalidated the sizing above. 20,000 draws per family on `bass6`:
#:
#: | pool                  | before | after |
#: |-----------------------|--------|-------|
#: | `chromatic`           | 0.437  | 0.437 |
#: | `scales`              | 0.485  | 0.299 |
#: | `arpeggios`           | 0.960  | 0.560 |
#: | `intervals`           | 0.819  | 0.152 |
#:
#: `intervals` is the family the span bound costs most, and for a structural
#: reason: its cycle is an octave of lower notes walked along one string, so it
#: covers twelve frets before the upper note of a single pair is placed, and
#: only the draws whose two strings sit close together survive. At 0.152 the
#: budget is unchanged: 500 attempts leave a 1.6e-36 chance of a spurious
#: failure, and the 1-in-20 pool the number was sized against is still three
#: times worse than the worst family measured here. 500 stands.
MAX_ATTEMPTS = 500

_SEMITONES_PER_OCTAVE = 12

#: §7's `root` axis, which is twelve pitch classes in the pool and an absolute
#: pitch in `params` — see the module docstring.
ROOT = "root"

#: The axis a realized `root` is placed against: the exercise starts at or above
#: the open pitch of the lowest string it is played on. Every family that reads
#: `root` also reads `string_set`, so this is a lookup rather than a fallback; a
#: family that read one without the other would fail here by name.
STRING_SET = "string_set"

#: Axes whose value is only *read* by a family under some other axis's value,
#: keyed by `(family, axis)` and mapping to the value that switches them on.
#: Sampling one when its condition does not hold would record a use of a value
#: that changes nothing an exercise can hear (see the module docstring).
_CONDITIONAL_AXES: dict[tuple[str, str], tuple[str, str]] = {
    ("intervals", "scale_type"): ("context", "diatonic"),
}


class SelectionError(ValueError):
    """A draw that cannot be satisfied by the configured pool.

    A `ValueError`, because an over-constrained pool is an invalid combination
    of values; a distinct type, because §13 has the CLI print these to a user
    rather than as a traceback.
    """


@dataclass(frozen=True)
class ExerciseSpec:
    """One exercise: which family realizes it, and with which parameters.

    `params` is handed to `REGISTRY[spec.family].generate(profile, spec.params)`
    verbatim. It lives here rather than in `score` so that a family's contract
    stays `params -> Score` and no family ever imports the selector (§4,
    decision #21).
    """

    #: A key of `families.REGISTRY`, and of `vocabulary.AXES["family"]`.
    family: str
    #: Every axis the family reads, plus §8's four rhythm axes, which travel in
    #: the same dictionary and are read by `rhythm.apply` further down §4's
    #: pipeline.
    params: dict[str, AxisValue]


@dataclass(frozen=True)
class WeightInputs:
    """The recency distances that fed one draw (§9, decision #14).

    `distances` maps an axis to each of its candidate values — labelled by
    `axis_key`, so the structure is JSON as it stands — and each value to the
    number of sessions since it was last used. `0` is a value used earlier in
    *this* session, `1` a value used in the session before it, and `None` a
    value not used inside the horizon at all.

    Recorded into `session.json` because a seed alone cannot reproduce a day:
    the weights are computed from a log that grows, so replaying a seed against
    today's log computes different weights than the original run did and would
    produce a different sheet silently. Every axis the slot's sampler *could*
    consult is recorded, not only the axes the accepted specification kept — the
    rejected attempts consumed the generator too, and a replay that skipped them
    would diverge.
    """

    distances: dict[str, dict[str, int | None]]


def weight(sessions_since: int | None, horizon: int = DEFAULT_HORIZON) -> float:
    """How heavily a candidate value is drawn, given how long since it was used.

    Spec §9 and decision #15: **one expression, with the floor applied last**,
    rather than a ladder of special cases. Monotonic in `sessions_since`, never
    above 1.0, and never zero — the last of those is what keeps a weighted draw
    over a pool whose every value was used today defined rather than a division
    by zero.

    `None` means never used within the horizon and weighs 1.0, which is the same
    weight the ratio saturates at, so a longer window would change nothing.

    This is the one entry point §9's tunability requirement names: replacing
    linear decay with exponential decay is a change to this function alone.
    """
    if sessions_since is None:
        return 1.0
    return max(FLOOR, min(1.0, sessions_since / horizon))


def axis_key(value: AxisValue) -> str:
    """The label one candidate value is recorded and counted under.

    `WeightInputs` is written to `session.json` (§12), so a value has to be a
    string before it can be a key. Structured axes — `string_set` and
    `permutation` — are joined with hyphens rather than repr'd, so the label is
    the same short thing in the file as it is here.

    The structured axes are the one thing a reader of the log has to restore:
    JSON gives a list back where the pool holds a tuple, and `ExerciseSpec`
    types `params` as `AxisValue` for exactly that reason. A history entry
    carrying lists would label its string sets differently from the pool they
    were drawn from and quietly stop counting as uses of them.
    """
    if isinstance(value, tuple):
        return "-".join(str(item) for item in value)
    return str(value)


# --------------------------------------------------------------------------
# What counts as a use of an axis value
# --------------------------------------------------------------------------


def _coverage_value(axis: str, spec: ExerciseSpec) -> AxisValue | None:
    """The value of `axis` this specification used, or None if it used none.

    `None` is the honest answer for an axis the family does not read: a
    `chromatic` exercise says nothing about `scale_type`, and neither does an
    `intervals` exercise in a chromatic context, which is why that draw omits
    the axis from `params` rather than sampling a value it will not read.

    `root` is reduced to its pitch class, because §7's axis is twelve pitch
    classes and `params` carries the octave the selector realized it at. A
    recorded A1 and a recorded A2 are one use of the same axis value.
    """
    if axis == FAMILY:
        return spec.family
    value = spec.params.get(axis)
    if axis == ROOT and value is not None:
        return cast("int", value) % _SEMITONES_PER_OCTAVE
    return value


def _uses(spec: ExerciseSpec) -> dict[str, str]:
    """Every axis this specification used, labelled as `WeightInputs` labels it."""
    axes = [FAMILY, *spec.params]
    return {axis: axis_key(cast("AxisValue", _coverage_value(axis, spec))) for axis in axes}


def _distances(
    axis: str,
    candidates: Sequence[AxisValue],
    history: Sequence[Sequence[ExerciseSpec]],
    pending: Mapping[str, set[str]],
    horizon: int,
) -> dict[str, int | None]:
    """Sessions since each candidate value of `axis` was last used (§9).

    `pending` holds the values already drawn in *this* session, at distance
    zero, which is what makes the next slot avoid them (§9's within-session
    diversity). The log is then read nearest first, so the first session
    carrying a value is the smallest distance and later ones cannot overwrite
    it.

    Only the last `horizon` sessions are read, exactly as §9 describes. Nothing
    is lost by stopping there: `weight` saturates at the horizon, so a value
    last used beyond it and a value never used at all weigh the same 1.0, and
    the distinction would only make `session.json` larger.
    """
    used: dict[str, int] = dict.fromkeys(pending.get(axis, ()), 0)
    for distance, session in enumerate(reversed(history[-horizon:]), start=1):
        for spec in session:
            value = _coverage_value(axis, spec)
            if value is not None:
                used.setdefault(axis_key(value), distance)
    return {axis_key(candidate): used.get(axis_key(candidate)) for candidate in candidates}


# --------------------------------------------------------------------------
# One slot of the session
# --------------------------------------------------------------------------


@dataclass
class _Slot:
    """The draws for one exercise, and the distances that fed them.

    One instance per slot rather than per attempt: a rejected specification does
    not change the history, so every attempt for a slot weighs its candidates
    identically and the distances are computed once, on first use of each axis.
    `distances` is therefore both the cache and the record `WeightInputs`
    carries — every axis the sampler consulted across every attempt, which is
    what a replay has to reproduce.
    """

    history: Sequence[Sequence[ExerciseSpec]]
    pending: Mapping[str, set[str]]
    horizon: int
    rng: Random
    distances: dict[str, dict[str, int | None]] = field(default_factory=dict)

    def draw(self, axis: str, candidates: Sequence[AxisValue]) -> AxisValue:
        """One value of one axis, drawn proportional to its recency weight."""
        recorded = self.distances.get(axis)
        if recorded is None:
            recorded = _distances(axis, candidates, self.history, self.pending, self.horizon)
            self.distances[axis] = recorded
        weights = [weight(recorded[axis_key(candidate)], self.horizon) for candidate in candidates]
        return self.rng.choices(list(candidates), weights)[0]


def _candidates(
    section: str, axis: str, pool: Mapping[str, tuple[AxisValue, ...]]
) -> tuple[AxisValue, ...]:
    """The configured candidate values of one axis, or a loud error (§13).

    `config` leaves an axis the user did not configure absent rather than
    defaulting it, so an unconfigured axis arrives here as a missing key. It is
    not defaulted here either: inventing a candidate set would be this module
    deciding a tuning surface `config` deliberately declined to decide, and §13
    forbids falling back to a default for something the configuration does not
    say.
    """
    values = pool.get(axis)
    if values is None:
        msg = (
            f"[pool.{section}] configures no candidate values for the {axis!r} axis. §9 samples "
            f"every axis its family reads, and an axis with no candidates cannot be sampled; "
            f"declare it under [pool.{section}] — an axis is never defaulted for you (§13)"
        )
        raise SelectionError(msg)
    return values


def _sample(family: str, config: Config, slot: _Slot) -> dict[str, AxisValue]:
    """One candidate specification: every axis of `family`, drawn independently.

    §8's rhythm axes are drawn alongside them and travel in the same dictionary,
    because §4's pipeline hands one `params` to the family and then to
    `rhythm.apply`, and §9 counts `subdivision` and `accent_pattern` as axes
    like any other.
    """
    params: dict[str, AxisValue] = {}
    pool = config.pool[family].values
    for axis in REGISTRY[family].axes:
        switch = _CONDITIONAL_AXES.get((family, axis))
        if switch is not None and params[switch[0]] != switch[1]:
            continue
        params[axis] = slot.draw(axis, _candidates(family, axis, pool))
    for axis in rhythm.AXES:
        params[axis] = slot.draw(axis, _candidates(RHYTHM, axis, config.rhythm.values))
    return _realized(params, config.instrument)


def _realized(params: dict[str, AxisValue], profile: InstrumentProfile) -> dict[str, AxisValue]:
    """`root` as an absolute pitch: §7's pitch class, placed on the instrument.

    The lowest octave at or above the open pitch of the string set's lowest
    string. Deterministic, and inside the strings the exercise is played on
    rather than beside them — a pitch class handed to a family unchanged would
    ask for A0 on an instrument whose lowest string is B0, and every draw would
    be unrealizable.
    """
    if ROOT not in params:
        return params
    strings = cast("tuple[int, ...]", params[STRING_SET])
    open_pitch = profile.tuning[strings[0]]
    pitch_class = cast("int", params[ROOT])
    return {**params, ROOT: open_pitch + (pitch_class - open_pitch) % _SEMITONES_PER_OCTAVE}


# --------------------------------------------------------------------------
# The validity gate (§9, §7's `max_notes`)
# --------------------------------------------------------------------------


def _rejected(family: str, params: Mapping[str, AxisValue], config: Config) -> str | None:
    """Why this specification cannot be used, or `None` if it can.

    The exercise is realized exactly as §4's pipeline realizes it — the family,
    then §8's rhythm modifier — because both halves can reject a draw and
    because `max_notes` bounds the notes that get *printed*. A family raises
    `ValueError` naming what could not be satisfied when a specification runs
    off the neck or asks a traversal for a string count it does not have; that
    is the gate, and the message is kept because §13 makes the eventual failure
    report the whole value of the loud error.

    Only `ValueError` is caught. Anything else from a family is a bug in the
    family (§13) and resampling around it would hide it.
    """
    try:
        generated, _hints = REGISTRY[family].generate(config.instrument, params)
        score = rhythm.apply(generated, params)
    except ValueError as error:
        return str(error)

    printed = list(notes(score.voice))
    if len(printed) > config.session.max_notes:
        return (
            f"{family}: the cycle is {len(printed)} notes, over the max_notes bound of "
            f"{config.session.max_notes}. range_octaves, pattern and direction multiply, so a "
            f"cycle is bounded rather than truncated (§7, decision #17)"
        )

    span = hand_span(note.fret for note in printed)
    if span > config.session.max_fret_span:
        return (
            f"{family}: the exercise makes the hand travel {span} frets, over the "
            f"max_fret_span bound of {config.session.max_fret_span}. A traversal, a string_set "
            f"and a shift that spread an exercise further than that are a specification "
            f"nothing can play in one sitting, so it is resampled rather than engraved "
            f"(§9, issue #57)"
        )
    return None


def _over_constrained(family: str, reasons: Counter[str], slot: _Slot) -> SelectionError:
    """The loud failure §9 requires when the retry budget runs out.

    It names the family, quotes the family's own account of what could not be
    satisfied — the modal one, since the axes vary from draw to draw — and lists
    the candidate values every axis was drawn from, so the over-constrained
    combination is readable from the message rather than reconstructed from the
    configuration file.
    """
    modal, count = reasons.most_common(1)[0]
    pool = {axis: sorted(values) for axis, values in slot.distances.items()}
    msg = (
        f"{family}: no valid specification in {MAX_ATTEMPTS} draws from this pool. The most "
        f"common failure ({count} of {MAX_ATTEMPTS} draws) was: {modal}. Widen one of the axes "
        f"that message names, or drop {family} from [session] shape — §9 resamples an "
        f"unrealizable draw and never quietly adjusts one into something renderable. The "
        f"candidates drawn from were: {pool}"
    )
    return SelectionError(msg)


# --------------------------------------------------------------------------
# The entry point
# --------------------------------------------------------------------------


def _fill(family: str, config: Config, slot: _Slot) -> ExerciseSpec:
    """One valid specification for `family`, resampling until the budget runs out."""
    reasons: Counter[str] = Counter()
    for _ in range(MAX_ATTEMPTS):
        params = _sample(family, config, slot)
        reason = _rejected(family, params, config)
        if reason is None:
            return ExerciseSpec(family=family, params=params)
        reasons[reason] += 1
    raise _over_constrained(family, reasons, slot)


def _families(config: Config) -> tuple[str, ...] | None:
    """The declared shape as one family per slot, or `None` to weight families.

    §9: the mix of families is configuration, not chance. `config` has already
    checked that the shape and the count agree, so the slots are the declared
    counts in the order they were written.
    """
    shape = config.session.shape
    if shape is None:
        return None
    return tuple(family for family, count in shape.items() for _ in range(count))


def _configured(config: Config) -> tuple[AxisValue, ...]:
    """The families the `family` axis is drawn from when no shape is declared.

    A `[pool.<family>]` section that configures no axis at all is a family this
    configuration does not practise, so it is not a candidate: declaring the
    section *is* how a family is opted into an unshaped draw. Naming one in
    `[session] shape` is the other way, and that route reaches `_candidates`
    instead — a family whose pool is half-written is an error there rather than
    a family quietly dropped here.
    """
    families = tuple(family for family, pool in config.pool.items() if pool.values)
    if not families:
        msg = (
            "no [pool.<family>] section configures any axis, so there is nothing to draw from. "
            "§9 weights the families when [session] shape is unset, and a family with no "
            "candidate values on any axis cannot be sampled"
        )
        raise SelectionError(msg)
    return families


def select(
    config: Config,
    history: Sequence[Sequence[ExerciseSpec]],
    rng: Random,
) -> list[tuple[ExerciseSpec, WeightInputs]]:
    """Draw one session's exercises, and the weight inputs that produced them.

    `history` is the session log, **oldest session first**, each session being
    the specifications it was made of. The session before this one is therefore
    at distance 1, and a value drawn earlier in this session is at distance 0.
    Only the last `horizon` sessions are read (§9).

    `rng` is injected and never module-level: §9's determinism is a requirement,
    and the caller seeds it from the date and the configuration hash. Each
    returned pick carries its own `WeightInputs`, because the within-session
    pushdown means the second slot of a session was drawn against different
    distances than the first.
    """
    declared = _families(config)
    pending: dict[str, set[str]] = {}
    picks: list[tuple[ExerciseSpec, WeightInputs]] = []

    for index in range(config.session.count):
        slot = _Slot(
            history=history,
            pending=pending,
            horizon=config.session.horizon,
            rng=rng,
        )
        family = (
            declared[index]
            if declared is not None
            else cast("str", slot.draw(FAMILY, _configured(config)))
        )
        spec = _fill(family, config, slot)
        picks.append((spec, WeightInputs(distances=slot.distances)))
        for axis, key in _uses(spec).items():
            pending.setdefault(axis, set()).add(key)

    return picks
