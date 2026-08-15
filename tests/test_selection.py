"""Tests for coverage-aware selection (spec §9, §14).

The suite is ordered the way §9's argument is. The weighting function comes
first, because decision #15 *is* the weighting function: one expression, the
floor applied last, and never zero. The pathological pool comes second, because
it is the case the superseded three-rule formulation would have divided by zero
on. Sampling, the validity gate and the within-session pushdown follow, and the
200-session simulation closes the file — that is §14's proof that the clumping
problem §9 exists to solve is actually solved.
"""

from __future__ import annotations

from collections import Counter
from random import Random
from typing import TYPE_CHECKING

import pytest

from melete import pipeline, rhythm
from melete.config import RHYTHM, load_string
from melete.families import REGISTRY, Family
from melete.instrument import PROFILES, hand_span
from melete.score import Tuplet
from melete.selection import (
    FAMILY,
    FLOOR,
    MAX_ATTEMPTS,
    ExerciseSpec,
    SelectionError,
    WeightInputs,
    _realized,
    axis_key,
    select,
    weight,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from melete.config import AxisValue, Config
    from melete.families import Params
    from melete.instrument import InstrumentProfile
    from melete.layout import LayoutHints
    from melete.score import Note, Score

HORIZON = 14


def seeded(seed: int) -> Random:
    """A generator seeded from a number, which is the whole of §9's determinism.

    Written once so the reason is written once: `random` is the right module
    here precisely because it is reproducible, and nothing in a practice sheet
    is a secret.
    """
    return Random(seed)  # noqa: S311 - reproducibility is the requirement (§9)


# --------------------------------------------------------------------------
# Configurations, written as the TOML a user would write (spec §10)
# --------------------------------------------------------------------------

INSTRUMENT = '[instrument]\nprofile = "bass6"\n'

#: One axis per line, as TOML values. Each pool function below applies the
#: overrides its test needs, so a test names only the axis it is about.
SCALES_AXES: dict[str, str] = {
    "roots": '"all"',
    "scale_types": '["ionian", "dorian", "phrygian", "lydian", "mixolydian", "aeolian"]',
    "traversals": '["positional"]',
    "patterns": '["straight", "thirds", "groups_of_3"]',
}

CHROMATIC_AXES: dict[str, str] = {
    "permutations": "[[1, 2, 3, 4], [1, 3, 2, 4], [2, 1, 4, 3], [4, 3, 2, 1]]",
    "start_strings": "[0, 1, 2]",
    "start_frets": "[1, 3, 5, 7]",
    "string_traversals": '["adjacent"]',
    "shifts": '["none", "fret_per_cycle"]',
    "spans": "[3, 4]",
}

ARPEGGIOS_AXES: dict[str, str] = {
    "roots": '"all"',
    "qualities": '["maj", "min", "maj7", "min7", "dom7"]',
    "inversions": '["root", "first", "second"]',
    "patterns": '["straight", "broken"]',
}

INTERVALS_AXES: dict[str, str] = {
    "intervals": "[3, 4, 5, 6]",
    "contexts": '["chromatic", "diatonic"]',
    "roots": '"all"',
    "scale_types": '["ionian", "dorian", "aeolian"]',
    "string_skips": '["0", "1"]',
    "patterns": '["ascending_pairs", "descending_pairs", "alternating"]',
}

RHYTHM_AXES: dict[str, str] = {
    "accent_patterns": '["none", "every_3"]',
    "note_value_patterns": '["straight", "long_short"]',
}


def section(name: str, axes: Mapping[str, str], **overrides: str) -> str:
    """One `[pool.<name>]` section, with the named axes replaced or removed.

    An override of `""` drops the axis, which is how the unconfigured-axis
    tests express a pool that leaves something out.
    """
    values = {**axes, **overrides}
    lines = [f"{key} = {value}" for key, value in values.items() if value]
    return f"[pool.{name}]\n" + "\n".join(lines) + "\n"


def make_config(*sections: str, session: str = "", rhythm_pool: str | None = None) -> Config:
    """A `Config` from the sections a test cares about, loaded as real TOML."""
    pool = rhythm_pool if rhythm_pool is not None else section(RHYTHM, RHYTHM_AXES)
    return load_string("\n".join([INSTRUMENT, session, *sections, pool]))


def scales_config(*, session: str = "", **overrides: str) -> Config:
    """The `scales`-only configuration most of these tests draw from."""
    return make_config(section("scales", SCALES_AXES, **overrides), session=session)


def shape(**counts: int) -> str:
    """A `[session]` section declaring §9's family mix."""
    declared = ", ".join(f"{family} = {count}" for family, count in counts.items())
    return f"[session]\nshape = {{ {declared} }}\n"


def every_family(session: str) -> Config:
    """A configuration whose four pools are all declared, under `session`."""
    return make_config(
        section("chromatic", CHROMATIC_AXES),
        section("scales", SCALES_AXES),
        section("arpeggios", ARPEGGIOS_AXES),
        section("intervals", INTERVALS_AXES),
        session=session,
    )


def specs_of(picks: Sequence[tuple[ExerciseSpec, WeightInputs]]) -> list[ExerciseSpec]:
    return [spec for spec, _inputs in picks]


def printed_voice(config: Config, spec: ExerciseSpec) -> list[Note]:
    """Every note the exercise engraves, realized as §4's pipeline does."""
    score, _plan = pipeline.realize(config.instrument, spec.family, spec.params)
    notes: list[Note] = []
    for item in score.voice:
        notes.extend(item.notes if isinstance(item, Tuplet) else [item])
    return notes


def printed_notes(config: Config, spec: ExerciseSpec) -> int:
    """How many notes the exercise engraves."""
    return len(printed_voice(config, spec))


def printed_span(config: Config, spec: ExerciseSpec) -> int:
    """How far the fretting hand travels across the engraved exercise."""
    return hand_span(note.fret for note in printed_voice(config, spec))


#: One realizable `scales` specification, for the tests that need a history
#: entry rather than a draw. A positional A Dorian journey.
SPEC_PARAMS: dict[str, AxisValue] = {
    "root": 33,
    "scale_type": "dorian",
    "traversal": "positional",
    "pattern": "straight",
    "accent_pattern": "none",
    "note_value_pattern": "straight",
}


# --------------------------------------------------------------------------
# Decision #15: one expression, the floor applied last, never zero
# --------------------------------------------------------------------------


def test_never_used_weighs_one() -> None:
    assert weight(None, HORIZON) == 1.0


def test_used_today_is_the_floor_not_zero() -> None:
    """Distance 0 is what the within-session pushdown produces (spec §9)."""
    assert weight(0, HORIZON) == FLOOR


def test_no_weight_is_ever_zero() -> None:
    assert all(weight(distance, HORIZON) >= FLOOR for distance in range(100))


def test_the_ratio_wins_above_the_floor() -> None:
    """The floor is a floor, not a ceiling: at distance 1 the ratio is larger."""
    assert weight(1, HORIZON) == pytest.approx(1 / HORIZON)
    assert weight(1, HORIZON) > FLOOR


def test_weight_is_monotonic_non_decreasing() -> None:
    weights = [weight(distance, HORIZON) for distance in range(30)]
    assert weights == sorted(weights)


def test_saturates_at_the_horizon() -> None:
    assert weight(HORIZON, HORIZON) == 1.0
    assert weight(99, HORIZON) == 1.0


def test_the_horizon_defaults_to_the_configured_one() -> None:
    assert weight(7) == weight(7, HORIZON)


def test_a_short_horizon_still_floors_at_distance_zero() -> None:
    assert weight(0, 1) == FLOOR
    assert weight(1, 1) == 1.0


def test_axis_key_labels_every_kind_of_candidate_value() -> None:
    """`WeightInputs` is written to `session.json`, so a value must be a string."""
    assert axis_key("dorian") == "dorian"
    assert axis_key(9) == "9"
    assert axis_key((0, 1, 2, 3)) == "0-1-2-3"


# --------------------------------------------------------------------------
# The pathological pool: the draw the superseded formulation divided by zero on
# --------------------------------------------------------------------------


def test_the_exhausted_pool_still_selects() -> None:
    """`shape = { scales = 3 }` over a two-element pool (spec §9, §14).

    By the third slot both scale types have been used in this session, so both
    sit at distance 0. Under the three-rule formulation both weighed 0.0 and the
    draw was undefined; under decision #15 both weigh the floor and the draw
    remains a draw.
    """
    config = scales_config(session=shape(scales=3), scale_types='["ionian", "dorian"]')

    picks = select(config, [], seeded(0))

    assert len(picks) == 3
    assert {str(spec.params["scale_type"]) for spec in specs_of(picks)} <= {"ionian", "dorian"}


def test_the_third_slot_of_an_exhausted_pool_weighs_every_candidate_at_the_floor() -> None:
    config = scales_config(session=shape(scales=3), scale_types='["ionian", "dorian"]')

    _spec, inputs = select(config, [], seeded(0))[2]

    assert inputs.distances["scale_type"] == {"ionian": 0, "dorian": 0}
    assert all(weight(distance) == FLOOR for distance in inputs.distances["scale_type"].values())


# --------------------------------------------------------------------------
# Sampling: independent axes, valid specifications, a declared shape
# --------------------------------------------------------------------------


def test_selects_the_configured_count() -> None:
    assert len(select(scales_config(session="[session]\ncount = 5\n"), [], seeded(1))) == 5


def test_a_declared_shape_fills_the_slots_in_the_order_it_declares_them() -> None:
    """Spec §9: the mix of families is configuration, not chance."""
    config = every_family(shape(chromatic=1, scales=2, arpeggios=1, intervals=1))

    families = [spec.family for spec in specs_of(select(config, [], seeded(2)))]

    assert families == ["chromatic", "scales", "scales", "arpeggios", "intervals"]


def test_an_unset_shape_weights_the_families_instead() -> None:
    """Spec §9: leaving the shape unset makes `family` an axis like any other."""
    # Eight slots rather than four: the recency weighting makes a family drawn
    # this slot unlikely in the next one, never impossible (§9's floor), so
    # "every family appears" is a property of a session long enough to show it
    # and not of one exactly as long as the registry.
    config = every_family("[session]\ncount = 8\n")

    picks = select(config, [], seeded(3))

    assert {spec.family for spec in specs_of(picks)} == set(REGISTRY)
    assert all(FAMILY in inputs.distances for _spec, inputs in picks)


def test_a_declared_shape_does_not_draw_the_family_axis() -> None:
    _spec, inputs = select(scales_config(session=shape(scales=1)), [], seeded(4))[0]

    assert FAMILY not in inputs.distances


def test_every_specification_carries_the_axes_its_family_reads_and_the_rhythm_axes() -> None:
    config = every_family(shape(chromatic=1, scales=1, arpeggios=1, intervals=1))

    for spec in specs_of(select(config, [], seeded(5))):
        expected = set(REGISTRY[spec.family].axes) | set(rhythm.AXES)
        # `intervals` in a chromatic context reads no `scale_type`; see below.
        assert set(spec.params) <= expected
        assert expected - set(spec.params) <= {"scale_type"}


def test_every_specification_is_realizable_as_the_pipeline_realizes_it() -> None:
    """The gate's promise: what §4's pipeline is handed always engraves."""
    config = every_family(shape(chromatic=2, scales=2, arpeggios=2, intervals=2))

    for spec in specs_of(select(config, [], seeded(6))):
        assert 0 < printed_notes(config, spec) <= config.session.max_notes


def test_root_anchors_on_the_lowest_instrument_string() -> None:
    """§5, §8: the root pins to the lowest *instrument* string, not the set's."""
    bass6 = PROFILES["bass6"]  # lowest string open = B0 = 23
    # pitch class of Bb (10) -> the lowest fret on the low B string sounding it,
    # which is fret 11 -> Bb1 = 34 (23 + (10 - 23) % 12).
    out = _realized({"root": 10}, bass6)
    assert out["root"] == 34
    assert out["root"] - bass6.tuning[0] == 11  # fret 11 on the low string
    assert (out["root"] - bass6.tuning[0]) % 12 == (10 - bass6.tuning[0]) % 12


def test_a_root_is_realized_onto_the_lowest_instrument_string() -> None:
    """§5, §8: a family needs an absolute pitch, anchored on the low string."""
    config = scales_config(session=shape(scales=8))
    open_pitch = config.instrument.tuning[0]

    for spec in specs_of(select(config, [], seeded(7))):
        root = spec.params["root"]
        assert isinstance(root, int)
        assert open_pitch <= root < open_pitch + 12


def test_a_root_is_counted_as_its_pitch_class() -> None:
    """Coverage accounting stays on §7's axis: A1 and A2 are one value."""
    config = scales_config(session=shape(scales=2))

    picks = select(config, [], seeded(8))
    drawn, next_slot = picks[0][0], picks[1][1]

    assert set(next_slot.distances["root"]) == {str(pitch_class) for pitch_class in range(12)}
    root = drawn.params["root"]
    assert isinstance(root, int)
    assert next_slot.distances["root"][str(root % 12)] == 0


# --------------------------------------------------------------------------
# Determinism (spec §9, decision #14)
# --------------------------------------------------------------------------


def test_the_same_seed_draws_the_same_session() -> None:
    config = scales_config(session="[session]\ncount = 5\n")

    assert specs_of(select(config, [], seeded(99))) == specs_of(select(config, [], seeded(99)))


def test_a_different_seed_draws_a_different_session() -> None:
    config = scales_config(session="[session]\ncount = 5\n")

    assert specs_of(select(config, [], seeded(1))) != specs_of(select(config, [], seeded(2)))


def test_the_history_changes_the_draw_under_the_same_seed() -> None:
    """Decision #14: a seed alone cannot reproduce a day, and this is why."""
    config = scales_config(session="[session]\ncount = 3\n")
    first = specs_of(select(config, [], seeded(42)))

    assert specs_of(select(config, [first], seeded(42))) != first


# --------------------------------------------------------------------------
# Within-session diversity and the session log (spec §9)
# --------------------------------------------------------------------------


def test_a_selection_is_pushed_onto_the_history_at_distance_zero() -> None:
    """Spec §9: the next slot in the same session actively avoids it."""
    config = scales_config(session=shape(scales=2))

    picks = select(config, [], seeded(10))
    drawn, next_slot = picks[0][0], picks[1][1]

    for axis in ("scale_type", "traversal", "pattern", "accent_pattern"):
        assert next_slot.distances[axis][axis_key(drawn.params[axis])] == 0


def test_the_first_slot_of_a_fresh_log_has_used_nothing() -> None:
    _spec, inputs = select(scales_config(session=shape(scales=1)), [], seeded(11))[0]

    assert all(distance is None for distance in inputs.distances["scale_type"].values())


def test_the_previous_session_is_at_distance_one() -> None:
    config = scales_config(session=shape(scales=1))
    yesterday = specs_of(select(config, [], seeded(12)))

    _spec, inputs = select(config, [yesterday], seeded(13))[0]

    assert inputs.distances["scale_type"][axis_key(yesterday[0].params["scale_type"])] == 1


def test_only_the_horizon_is_read_back() -> None:
    """§9 reads the last N sessions; beyond it the ratio saturates anyway."""
    config = scales_config(session="[session]\nhorizon = 2\ncount = 1\n")
    old = ExerciseSpec(family="scales", params={**SPEC_PARAMS, "scale_type": "lydian"})
    recent = ExerciseSpec(family="scales", params={**SPEC_PARAMS, "scale_type": "dorian"})
    history = [[old], [recent], [recent]]

    _spec, inputs = select(config, history, seeded(14))[0]

    assert inputs.distances["scale_type"]["lydian"] is None
    assert inputs.distances["scale_type"]["dorian"] == 1


def test_an_axis_the_family_does_not_read_is_not_a_use_of_it() -> None:
    """A chromatic exercise says nothing about `scale_type` (spec §9).

    `accent_pattern` is §8's rhythm axis, which every family reads, so a
    chromatic exercise that used one *is* recorded against the scales draw; a
    scale-only axis like `scale_type`, which chromatic never reads, is not. That
    contrast is the point — a coverage system that credited an axis the past
    family did not read would avoid variety it never actually consumed.
    """
    config = scales_config(session=shape(scales=1))
    chromatic = ExerciseSpec(family="chromatic", params={"accent_pattern": "none"})

    _spec, inputs = select(config, [[chromatic]], seeded(15))[0]

    assert all(distance is None for distance in inputs.distances["scale_type"].values())
    assert inputs.distances["accent_pattern"]["none"] == 1


def test_the_weight_inputs_record_every_axis_the_draw_consulted() -> None:
    """Decision #14: `session.json` has to be sufficient for exact replay."""
    config = scales_config(session=shape(scales=1))

    _spec, inputs = select(config, [], seeded(16))[0]

    assert set(inputs.distances) == set(REGISTRY["scales"].axes) | set(rhythm.AXES)
    assert inputs.distances["scale_type"].keys() == set(config.pool["scales"].values["scale_type"])


# --------------------------------------------------------------------------
# `scale_type` is not coverage-relevant to a chromatic-context intervals draw
# --------------------------------------------------------------------------


def test_a_chromatic_context_draw_samples_no_scale_type() -> None:
    """The family reads it only in the diatonic branch (spec §7, B8).

    Two chromatic specifications differing only in `scale_type` engrave the
    same sheet, so sampling one would credit §9's accounting with variety that
    does not exist — and would push a scale type down the pool for the next
    slot without a note of it being played.
    """
    config = make_config(
        section("intervals", INTERVALS_AXES, contexts='["chromatic"]', scale_types=""),
        session=shape(intervals=4),
    )

    for spec in specs_of(select(config, [], seeded(20))):
        assert spec.params["context"] == "chromatic"
        assert "scale_type" not in spec.params


def test_a_diatonic_context_draw_does_sample_one() -> None:
    config = make_config(
        section("intervals", INTERVALS_AXES, contexts='["diatonic"]'),
        session=shape(intervals=4),
    )

    for spec in specs_of(select(config, [], seeded(21))):
        assert spec.params["scale_type"] in ("ionian", "dorian", "aeolian")


def test_a_chromatic_context_exercise_does_not_push_a_scale_type_down() -> None:
    config = make_config(
        section("intervals", INTERVALS_AXES),
        section("scales", SCALES_AXES),
        session=shape(scales=1),
    )
    chromatic = ExerciseSpec(
        family="intervals",
        params={"interval": 3, "context": "chromatic", "root": 33, "string_skip": "0"},
    )

    _spec, inputs = select(config, [[chromatic]], seeded(22))[0]

    assert all(distance is None for distance in inputs.distances["scale_type"].values())


# --------------------------------------------------------------------------
# Validity is a hard gate, and exhausting it is loud (spec §9, §13)
# --------------------------------------------------------------------------


def test_an_over_constrained_pool_names_what_could_not_be_satisfied() -> None:
    """A chromatic second skipping two strings can never place its partner.

    The interval journey (epic #72) puts the partner exactly `string_skip + 1`
    strings above the lower note, which is a jump of three strings here; two
    semitones cannot span that, so the partner runs below the nut on every draw
    and §9 exhausts the pool loudly rather than settling for a nearer string.
    """
    config = make_config(
        section(
            "intervals",
            INTERVALS_AXES,
            contexts='["chromatic"]',
            intervals="[2]",
            string_skips='["2"]',
        ),
        session=shape(intervals=1),
    )

    with pytest.raises(SelectionError) as raised:
        select(config, [], seeded(23))

    message = str(raised.value)
    assert "string_skip" in message
    assert "partner" in message
    assert str(MAX_ATTEMPTS) in message


def test_an_exercise_over_max_notes_is_resampled_and_then_reported() -> None:
    """Spec §7, decision #17: a cycle is bounded, never truncated.

    A positional journey fits one hand, so its span passes the gate and the
    *reported* failure is the length one — the outer-to-outer scale is far longer
    than four notes — and the message quotes the most common reason.
    """
    config = scales_config(session=f"{shape(scales=1)}max_notes = 4\n")

    with pytest.raises(SelectionError) as raised:
        select(config, [], seeded(24))

    message = str(raised.value)
    assert "max_notes" in message
    assert "emergent extent and the pattern" in message
    # The retired axes (epic #72) must not resurface in the prose.
    assert "range_octaves" not in message
    assert "direction" not in message


def test_an_exercise_over_max_fret_span_is_resampled_and_then_reported() -> None:
    """Issue #57: nothing bounded how far the fretting hand had to travel.

    The interval journey (epic #72) boxes its lower voice across the strings and
    lifts the partner above it, so even the most compact draw travels several
    frets. A two-fret bound is therefore a pool nothing in that family can
    satisfy, and §9 reports it by name rather than engraving a reach no hand has.
    """
    config = make_config(
        section("intervals", INTERVALS_AXES),
        session=f"{shape(intervals=1)}max_fret_span = 2\n",
    )

    with pytest.raises(SelectionError) as raised:
        select(config, [], seeded(29))

    message = str(raised.value)
    assert "max_fret_span" in message
    assert "travel" in message
    assert str(MAX_ATTEMPTS) in message


def test_max_fret_span_is_a_gate_over_every_traversal() -> None:
    # Not only `positional`: an exercise that is *labelled* as shifting still
    # has a bound on how far it shifts, and every family passes through it.
    config = every_family(
        f"{shape(chromatic=1, scales=1, arpeggios=1, intervals=1)}max_fret_span = 12\n"
    )

    for spec in specs_of(select(config, [], seeded(30))):
        assert printed_span(config, spec) <= 12


def test_a_shifting_exercise_is_still_allowed_to_shift() -> None:
    """The bound is loose enough for the traversals that are meant to move.

    `chromatic` with `shift = fret_per_cycle` climbs the neck by design (§7),
    and a bound that stopped it drawing would have bounded the wrong thing.
    """
    config = make_config(
        section("chromatic", CHROMATIC_AXES, shifts='["fret_per_cycle"]'),
        session=f"{shape(chromatic=3)}max_fret_span = 12\n",
    )

    picks = specs_of(select(config, [], seeded(31)))

    assert len(picks) == 3
    assert all(printed_span(config, spec) <= 12 for spec in picks)


def test_max_notes_is_a_gate_rather_than_a_truncation() -> None:
    # The outer-to-outer journey makes even a `straight` cycle ~32 notes and a
    # grouping pattern far more, so a 40-note ceiling admits the plain journey
    # and gates the longer patterns — resampling them away rather than truncating
    # a cycle to fit (spec §7, decision #17).
    config = scales_config(session=f"{shape(scales=4)}max_notes = 40\n")

    for spec in specs_of(select(config, [], seeded(25))):
        assert printed_notes(config, spec) <= 40


def test_an_unconfigured_axis_is_a_loud_error_naming_it() -> None:
    """§13: never fall back to a default for something the file does not say."""
    config = scales_config(session=shape(scales=1), patterns="")

    with pytest.raises(SelectionError) as raised:
        select(config, [], seeded(26))

    assert "'pattern'" in str(raised.value)
    assert "[pool.scales]" in str(raised.value)


def test_an_unconfigured_rhythm_axis_is_reported_against_its_own_section() -> None:
    config = make_config(
        section("scales", SCALES_AXES),
        session=shape(scales=1),
        rhythm_pool=section(RHYTHM, RHYTHM_AXES, accent_patterns=""),
    )

    with pytest.raises(SelectionError) as raised:
        select(config, [], seeded(27))

    assert "'accent_pattern'" in str(raised.value)
    assert "[pool.rhythm]" in str(raised.value)


def test_a_configuration_with_no_pool_at_all_cannot_weight_the_families() -> None:
    config = make_config(session="[session]\ncount = 1\n")

    with pytest.raises(SelectionError) as raised:
        select(config, [], seeded(28))

    assert "no [pool.<family>] section" in str(raised.value)


def test_a_bug_inside_a_family_is_never_resampled_around(monkeypatch: pytest.MonkeyPatch) -> None:
    """§13: a family raising anything but a ValueError is a bug, not a draw."""

    def broken(_profile: InstrumentProfile, _params: Params) -> tuple[Score, LayoutHints]:
        msg = "not a validity failure"
        raise TypeError(msg)

    monkeypatch.setitem(
        REGISTRY,
        "scales",
        Family(broken, REGISTRY["scales"].axes, REGISTRY["scales"].default_tempo_range),
    )

    with pytest.raises(TypeError, match="not a validity failure"):
        select(scales_config(session=shape(scales=1)), [], seeded(29))


# --------------------------------------------------------------------------
# The test that proves the point (spec §14)
# --------------------------------------------------------------------------

#: §14's simulation length, and the shape it is run under.
SESSIONS = 200
PER_SESSION = 2

#: Axes whose pool is large enough relative to `PER_SESSION` for a recurrence
#: rate to mean anything. With two draws per session over a two-value axis,
#: every session uses both values and "recurred at distance 1" is arithmetic
#: rather than clumping — so recurrence is asserted where there is room to
#: avoid a value, and uniformity is asserted everywhere.
ROOMY_AXES = ("root", "scale_type")

#: Every axis the `scales` pool above varies, §7's and §8's alike.
MEASURED_AXES = (
    "root",
    "scale_type",
    "pattern",
    "accent_pattern",
    "note_value_pattern",
)


def simulate(seed: int) -> dict[str, list[list[str]]]:
    """200 sessions under one seed: the values each axis used, session by session."""
    config = scales_config(session=shape(scales=PER_SESSION))
    rng = seeded(seed)
    history: list[list[ExerciseSpec]] = []
    used: dict[str, list[list[str]]] = {axis: [] for axis in MEASURED_AXES}
    for _ in range(SESSIONS):
        specs = specs_of(select(config, history, rng))
        history.append(specs)
        for axis in MEASURED_AXES:
            used[axis].append([axis_key(coverage_value(axis, spec)) for spec in specs])
    return used


def coverage_value(axis: str, spec: ExerciseSpec) -> AxisValue:
    value = spec.params[axis]
    if axis == "root":
        assert isinstance(value, int)
        return value % 12
    return value


def short_gap_rate(sessions: list[list[str]]) -> float:
    """How often a value used in one session is used again in the next."""
    last: dict[str, int] = {}
    recurrences = 0
    gaps = 0
    for index, values in enumerate(sessions):
        for value in set(values):
            if value in last:
                gaps += 1
                recurrences += index - last[value] == 1
            last[value] = index
    return recurrences / gaps


def worst_window(sessions: list[list[str]], horizon: int) -> int:
    """The most uses any one value got inside a horizon-length window."""
    windows = (sessions[start : start + horizon] for start in range(len(sessions) - horizon + 1))
    return max(
        max(Counter(value for values in window for value in values).values()) for window in windows
    )


def test_two_hundred_sessions_distribute_near_uniformly() -> None:
    """Spec §14: the test that proves the clumping problem is solved.

    Measured over 400 exercises: the worst-spread axis is `root` at 29 to 41
    uses of each of its twelve values, a ratio of 1.41 where a perfectly even
    split would be 33.3 each. Four seeds put the worst ratio anywhere in the
    file at 1.46. The bound below is 1.5 because uniform independent draws
    would routinely exceed it — 400 draws over twelve values has a standard
    deviation of 5.5, so a uniform run's extremes sit near 25 and 42, a ratio
    of about 1.7. The assertion therefore separates coverage-aware sampling
    from uniform sampling rather than merely asserting that both terminate.
    """
    used = simulate(12345)

    for axis, sessions in used.items():
        counts = Counter(value for values in sessions for value in values)
        low, high = min(counts.values()), max(counts.values())
        assert high / low < 1.5, f"{axis} clumped: {counts}"


def test_no_value_recurs_within_the_horizon_more_often_than_the_weighting_permits() -> None:
    """Spec §14's second half, measured two ways.

    *Recurrence at distance 1.* Under uniform independent draws, a value used
    in one session reappears in the next with probability `1 - (1 - 1/n)^k` for
    a pool of `n` values and `k` draws per session: 0.160 for the twelve roots
    and 0.306 for the six scale types. Measured here: 0.057 and 0.144 — the
    roots by a factor of three, the scale types by a factor of two, which is
    what a six-value pool has room for against two draws a session.

    *Concentration inside one horizon.* Fourteen sessions are twenty-eight
    draws, so an even spread gives each of the twelve roots 2.3 uses. The worst
    window of this run gives one root 6; a uniform control drawn at the same
    seed gives 7.
    """
    used = simulate(12345)

    for axis in ROOMY_AXES:
        pool = len({value for values in used[axis] for value in values})
        uniform = 1 - (1 - 1 / pool) ** PER_SESSION
        assert short_gap_rate(used[axis]) < uniform * 0.75, axis

    roots = used["root"]
    assert short_gap_rate(roots) < (1 - (1 - 1 / 12) ** PER_SESSION) / 2
    assert worst_window(roots, HORIZON) <= 6
