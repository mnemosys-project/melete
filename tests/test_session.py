"""Tests for the session log and replay (spec §12, §13, §14, decision #14).

The file is ordered the way decision #14's argument is. Round-tripping comes
first, because the whole value of the log is that what comes back out is what
went in — and the one value that does *not* survive JSON on its own is the
tuple, which `axis_key` labels differently from the list JSON hands back. Then
the two §13 rows this module owns: a corrupt entry is a hard error naming the
file, and an existing session directory is refused. The replay test closes the
file, because it is the proof the rest of the module exists for.
"""

from __future__ import annotations

import json
from datetime import date
from random import Random
from typing import TYPE_CHECKING

import pytest

from melete import session
from melete.config import load_string
from melete.selection import ExerciseSpec, WeightInputs, axis_key, select

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from melete.config import Config

HORIZON = 14

#: A pool broad enough that no draw is over-constrained, and narrow enough that
#: the recency weighting has something to spread across. `scales` carries
#: `string_set` and `chromatic` carries `permutation`, which are the two axes
#: whose values are tuples — the values this file exists to watch.
CONFIG_TOML = """
[instrument]
profile = "bass6"

[session]
shape = { scales = 2, chromatic = 1 }
horizon = 14

[pool.scales]
roots = "all"
scale_types = ["ionian", "dorian", "phrygian", "lydian", "mixolydian", "aeolian"]
traversals = ["positional"]
string_sets = [[0, 1, 2, 3], [1, 2, 3, 4], [2, 3, 4, 5]]
patterns = ["straight", "thirds"]
octaves = [1, 2]
directions = ["up", "down", "up_down"]

[pool.chromatic]
permutations = [[1, 2, 3, 4], [1, 3, 2, 4], [2, 1, 4, 3], [4, 3, 2, 1]]
start_strings = [0, 1, 2]
start_frets = [1, 3, 5, 7]
directions = ["up", "down", "up_down"]
string_traversals = ["adjacent"]
shifts = ["none", "fret_per_cycle"]
spans = [3, 4]

[pool.rhythm]
subdivisions = ["eighth", "triplet_eighth", "sixteenth"]
time_signatures = ["4_4", "3_4"]
accent_patterns = ["none", "every_3"]
note_value_patterns = ["straight", "long_short"]
"""


def config() -> Config:
    return load_string(CONFIG_TOML)


def seeded(seed: int) -> Random:
    """A generator seeded from a number, which is the whole of §9's determinism."""
    return Random(seed)  # noqa: S311 - reproducibility is the requirement (§9)


def generate(root: Path, on: date, *, force: bool = False) -> session.Session:
    """One day's run, exactly as §4's pipeline drives this module.

    Read the log, derive the seed from the date and the configuration hash
    (§9), draw, record, write. The log is read *before* the draw, so a session
    never sees itself; generating in date order is therefore the same log a
    real sequence of days would build.
    """
    active = config()
    digest = session.config_hash(active)
    seed = session.seed_for(on, digest)
    picks = select(active, session.history(root, HORIZON), seeded(seed))
    record = session.record(on, active, picks, seed)
    session.write(root, record, force=force)
    return record


def spec_with_a_string_set() -> ExerciseSpec:
    """One realizable `scales` specification, carrying both a tuple and an int."""
    return ExerciseSpec(
        family="scales",
        params={
            "root": 33,
            "scale_type": "dorian",
            "traversal": "positional",
            "string_set": (0, 1, 2, 3),
            "pattern": "straight",
            "range_octaves": 2,
            "direction": "up",
            "subdivision": "eighth",
            "time_signature": "4_4",
            "accent_pattern": "none",
            "note_value_pattern": "straight",
        },
    )


def written(root: Path, on: date, specs: Sequence[ExerciseSpec]) -> Path:
    """A session on disk made of exactly `specs`, for the tests about the file."""
    inputs = [WeightInputs(distances={"family": {"scales": None}}) for _ in specs]
    record = session.Session(
        date=on,
        instrument="bass6",
        seed=7,
        config_hash="0" * 64,
        exercises=tuple(specs),
        weight_inputs=tuple(inputs),
    )
    return session.write(root, record)


def document(directory: Path) -> dict[str, object]:
    text = (directory / session.FILENAME).read_text(encoding="utf-8")
    return json.loads(text)  # type: ignore[no-any-return]


# --------------------------------------------------------------------------
# What §12 requires the file to hold
# --------------------------------------------------------------------------


def test_session_json_records_seed_config_hash_params_and_weight_inputs(tmp_path: Path) -> None:
    """§12: the seed, the configuration hash, every parameter, the weight inputs."""
    generate(tmp_path, date(2026, 8, 9))

    data = document(session.directory(tmp_path, date(2026, 8, 9)))

    assert set(data) >= {"seed", "config_hash", "exercises", "weight_inputs"}


def test_every_exercise_records_its_full_parameter_dictionary(tmp_path: Path) -> None:
    written(tmp_path, date(2026, 8, 9), [spec_with_a_string_set()])

    data = document(session.directory(tmp_path, date(2026, 8, 9)))
    exercises = data["exercises"]
    assert isinstance(exercises, list)

    assert exercises[0]["family"] == "scales"
    assert set(exercises[0]["params"]) == set(spec_with_a_string_set().params)


def test_the_weight_inputs_are_one_record_per_exercise(tmp_path: Path) -> None:
    """Each slot was drawn against different distances, so each has its own."""
    record = generate(tmp_path, date(2026, 8, 9))

    data = document(session.directory(tmp_path, date(2026, 8, 9)))
    inputs = data["weight_inputs"]
    assert isinstance(inputs, list)

    assert len(inputs) == len(record.exercises)


def test_the_instrument_profile_is_named_in_the_log(tmp_path: Path) -> None:
    """§10: an explicit profile is named so the session log can identify it."""
    record = generate(tmp_path, date(2026, 8, 9))

    assert record.instrument == "bass6"
    assert document(session.directory(tmp_path, date(2026, 8, 9)))["instrument"] == "bass6"


def test_the_file_is_human_readable_and_git_committable(tmp_path: Path) -> None:
    """§12: indented, key-sorted and newline-terminated, so a diff is readable."""
    generate(tmp_path, date(2026, 8, 9))

    text = (session.directory(tmp_path, date(2026, 8, 9)) / session.FILENAME).read_text(
        encoding="utf-8"
    )

    assert text.startswith("{\n  ")
    assert text.endswith("\n")
    keys = list(json.loads(text))
    assert keys == sorted(keys)


# --------------------------------------------------------------------------
# The serialization trap: JSON has no tuples
# --------------------------------------------------------------------------


def test_a_string_set_is_restored_as_a_tuple_and_labels_identically(tmp_path: Path) -> None:
    """The trap decision #14 turns on.

    JSON round-trips a tuple as a list, and `axis_key` labels a list
    differently from the tuple it came from. A history carrying lists would
    silently stop counting its string sets as uses of the pool values they were
    drawn from, and the recency weighting would degrade invisibly — no error,
    just less varied sheets over time.
    """
    original = spec_with_a_string_set()
    directory = written(tmp_path, date(2026, 8, 9), [original])

    restored = session.read(directory).exercises[0].params["string_set"]

    assert isinstance(restored, tuple)
    assert restored == (0, 1, 2, 3)
    assert axis_key(restored) == axis_key(original.params["string_set"]) == "0-1-2-3"


def test_a_permutation_is_restored_as_a_tuple(tmp_path: Path) -> None:
    """`chromatic`'s tuple axis, which is the other half of the same trap."""
    spec = ExerciseSpec(family="chromatic", params={"permutation": (1, 3, 2, 4)})
    directory = written(tmp_path, date(2026, 8, 9), [spec])

    restored = session.read(directory).exercises[0].params["permutation"]

    assert restored == (1, 3, 2, 4)
    assert axis_key(restored) == "1-3-2-4"


def test_a_written_session_reads_back_equal(tmp_path: Path) -> None:
    """Every field, not only the tuples: the file is the record or it is nothing."""
    record = generate(tmp_path, date(2026, 8, 9))

    assert session.read(session.directory(tmp_path, date(2026, 8, 9))) == record


# --------------------------------------------------------------------------
# §13: a corrupt entry is a hard error naming the file
# --------------------------------------------------------------------------


def test_corrupt_history_entry_is_a_hard_error_naming_the_file(tmp_path: Path) -> None:
    directory = tmp_path / "sessions" / "2026-08-09"
    directory.mkdir(parents=True)
    (directory / session.FILENAME).write_text("{ not json", encoding="utf-8")

    with pytest.raises(session.SessionError) as exc:
        session.read(directory)

    assert session.FILENAME in str(exc.value)


def test_a_missing_session_names_the_file(tmp_path: Path) -> None:
    with pytest.raises(session.SessionError) as exc:
        session.read(tmp_path / "sessions" / "1999-01-01")

    assert "1999-01-01" in str(exc.value)


@pytest.mark.parametrize(
    ("document_text", "expected"),
    [
        ("[]", "expected an object"),
        ('{"seed": 1}', "missing"),
        pytest.param(
            json.dumps(
                {
                    "date": "not-a-date",
                    "instrument": "bass6",
                    "seed": 1,
                    "config_hash": "x",
                    "exercises": [],
                    "weight_inputs": [],
                }
            ),
            "date",
            id="unparseable-date",
        ),
    ],
)
def test_a_malformed_document_is_a_hard_error(
    tmp_path: Path, document_text: str, expected: str
) -> None:
    directory = tmp_path / "sessions" / "2026-08-09"
    directory.mkdir(parents=True)
    (directory / session.FILENAME).write_text(document_text, encoding="utf-8")

    with pytest.raises(session.SessionError) as exc:
        session.read(directory)

    assert expected in str(exc.value)
    assert session.FILENAME in str(exc.value)


def corrupt(tmp_path: Path, **changes: object) -> Path:
    """A written session whose document is then damaged in one named way."""
    directory = written(tmp_path, date(2026, 8, 9), [spec_with_a_string_set()])
    data = document(directory)
    data.update(changes)
    (directory / session.FILENAME).write_text(json.dumps(data), encoding="utf-8")
    return directory


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"instrument": 6}, "instrument"),
        ({"seed": "seven"}, "seed"),
        ({"seed": True}, "seed"),
        ({"seed": -1}, "non-negative"),
        ({"exercises": {}}, "exercises"),
        ({"exercises": [[]]}, "exercises[0]"),
        ({"exercises": [{"params": {}}]}, "family"),
        ({"exercises": [{"family": 1, "params": {}}]}, "family"),
        ({"exercises": [{"family": "scales", "params": []}]}, "params"),
        ({"exercises": [{"family": "scales", "params": {"root": 1.5}}]}, "params.root"),
        ({"exercises": [{"family": "scales", "params": {"root": True}}]}, "params.root"),
        ({"exercises": [{"family": "scales", "params": {"string_set": [[0]]}}]}, "string_set[0]"),
        ({"weight_inputs": [{"root": {"0": "near"}}]}, "root.0"),
        ({"weight_inputs": [{"root": []}]}, "root"),
        ({"weight_inputs": [1]}, "weight_inputs[0]"),
        ({"weight_inputs": []}, "one set of weight inputs per exercise"),
    ],
)
def test_a_corrupt_value_is_a_hard_error_naming_where_it_is(
    tmp_path: Path, changes: dict[str, object], expected: str
) -> None:
    """Never a skipped entry: §13's row, and the same failure class as the tuple."""
    directory = corrupt(tmp_path, **changes)

    with pytest.raises(session.SessionError) as exc:
        session.read(directory)

    assert expected in str(exc.value)
    assert session.FILENAME in str(exc.value)


def test_a_distance_of_none_is_a_value_not_a_corruption(tmp_path: Path) -> None:
    """`null` is how "never used inside the horizon" is spelled (§9)."""
    directory = corrupt(tmp_path, weight_inputs=[{"root": {"0": None, "1": 3}}])

    assert session.read(directory).weight_inputs[0].distances == {"root": {"0": None, "1": 3}}


# --------------------------------------------------------------------------
# §13: an existing session directory is refused
# --------------------------------------------------------------------------


def test_existing_session_directory_is_refused_without_force(tmp_path: Path) -> None:
    generate(tmp_path, date(2026, 8, 9))

    with pytest.raises(FileExistsError) as exc:
        generate(tmp_path, date(2026, 8, 9))

    assert "2026-08-09" in str(exc.value)
    assert "force" in str(exc.value)


def test_force_overwrites_an_existing_session(tmp_path: Path) -> None:
    written(tmp_path, date(2026, 8, 9), [spec_with_a_string_set()])

    record = generate(tmp_path, date(2026, 8, 9), force=True)

    assert session.read(session.directory(tmp_path, date(2026, 8, 9))) == record


# --------------------------------------------------------------------------
# The history the selector reads back
# --------------------------------------------------------------------------


def test_history_is_empty_before_the_first_session(tmp_path: Path) -> None:
    assert session.history(tmp_path, HORIZON) == []


def test_history_returns_the_last_n_sessions_oldest_first(tmp_path: Path) -> None:
    for day in (9, 10, 11, 12):
        generate(tmp_path, date(2026, 8, day))

    recent = session.history(tmp_path, 2)

    assert len(recent) == 2
    assert list(recent[0]) == list(session.replay(tmp_path, date(2026, 8, 11)).exercises)
    assert list(recent[1]) == list(session.replay(tmp_path, date(2026, 8, 12)).exercises)


def test_history_is_what_select_expects(tmp_path: Path) -> None:
    """The shape `select` reads: sessions oldest first, each a list of specs."""
    generate(tmp_path, date(2026, 8, 9))

    picks = select(config(), session.history(tmp_path, HORIZON), seeded(1))

    assert len(picks) == 3


def test_history_rejects_a_corrupt_entry_naming_the_file(tmp_path: Path) -> None:
    generate(tmp_path, date(2026, 8, 9))
    (session.directory(tmp_path, date(2026, 8, 9)) / session.FILENAME).write_text(
        "{ not json", encoding="utf-8"
    )

    with pytest.raises(session.SessionError) as exc:
        session.history(tmp_path, HORIZON)

    assert "2026-08-09" in str(exc.value)


def test_history_rejects_a_session_directory_that_is_not_a_date(tmp_path: Path) -> None:
    """A stray directory would sort as the newest session and silently displace one."""
    (tmp_path / "sessions" / "scratch").mkdir(parents=True)

    with pytest.raises(session.SessionError) as exc:
        session.history(tmp_path, HORIZON)

    assert "scratch" in str(exc.value)


def test_history_rejects_a_record_dated_differently_from_its_directory(tmp_path: Path) -> None:
    """A session.json copied into another day's directory is a corrupt entry."""
    generate(tmp_path, date(2026, 8, 9))
    elsewhere = tmp_path / "sessions" / "2026-08-10"
    elsewhere.mkdir()
    (elsewhere / session.FILENAME).write_text(
        (session.directory(tmp_path, date(2026, 8, 9)) / session.FILENAME).read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )

    with pytest.raises(session.SessionError) as exc:
        session.history(tmp_path, HORIZON)

    assert "2026-08-10" in str(exc.value)


def test_history_ignores_a_stray_file(tmp_path: Path) -> None:
    """A session is a directory (§12); a file beside one is not a half-read session."""
    generate(tmp_path, date(2026, 8, 9))
    (tmp_path / "sessions" / ".DS_Store").write_text("", encoding="utf-8")

    assert len(session.history(tmp_path, HORIZON)) == 1


def test_history_restores_tuples_so_the_weighting_keeps_counting(tmp_path: Path) -> None:
    """The trap, at the boundary that actually matters: what the selector reads."""
    written(tmp_path, date(2026, 8, 9), [spec_with_a_string_set()])

    (recent,) = session.history(tmp_path, HORIZON)

    assert recent[0].params["string_set"] == (0, 1, 2, 3)


# --------------------------------------------------------------------------
# The seed and the configuration hash (§9)
# --------------------------------------------------------------------------


def test_the_configuration_hash_is_stable_for_the_same_configuration() -> None:
    assert session.config_hash(config()) == session.config_hash(config())


def test_the_configuration_hash_changes_with_the_pool() -> None:
    narrower = load_string(CONFIG_TOML.replace('"straight", "thirds"', '"straight"'))

    assert session.config_hash(narrower) != session.config_hash(config())


def test_the_configuration_hash_covers_the_playability_bounds() -> None:
    """They decide which specifications are valid, so they move the draw (#57)."""
    bounded = load_string(CONFIG_TOML.replace("horizon = 14", "horizon = 14\nmax_fret_span = 9"))
    narrow_hand = load_string(
        CONFIG_TOML.replace('profile = "bass6"', 'profile = "bass6"\nposition_span = 3')
    )

    assert session.config_hash(bounded) != session.config_hash(config())
    assert session.config_hash(narrow_hand) != session.config_hash(config())


def test_the_configuration_hash_ignores_the_engraving_settings() -> None:
    """`[output]` decides how a drawn exercise is engraved, not which is drawn.

    Folding it into the hash would fold it into the seed, and changing the
    staff mode would silently hand back a different set of exercises.
    """
    tabbed = load_string(CONFIG_TOML + '\n[output]\nstaves = "tab"\n')

    assert session.config_hash(tabbed) == session.config_hash(config())


def test_the_configuration_hash_covers_an_unshaped_session() -> None:
    unshaped = load_string(CONFIG_TOML.replace("shape = { scales = 2, chromatic = 1 }", ""))

    assert session.config_hash(unshaped) != session.config_hash(config())


def test_the_seed_derives_from_the_date_and_the_configuration_hash() -> None:
    digest = session.config_hash(config())

    assert session.seed_for(date(2026, 8, 9), digest) == session.seed_for(date(2026, 8, 9), digest)
    assert session.seed_for(date(2026, 8, 10), digest) != session.seed_for(date(2026, 8, 9), digest)
    assert session.seed_for(date(2026, 8, 9), "0" * 64) != session.seed_for(
        date(2026, 8, 9), digest
    )


# --------------------------------------------------------------------------
# The replay test (spec §14, decision #14)
# --------------------------------------------------------------------------


def test_replay_reproduces_the_original_after_the_log_has_moved_on(tmp_path: Path) -> None:
    """The proof decision #14 exists for.

    Generate a day, let the log grow past it, then replay that day. The result
    must be the first run's, exactly — which is why `session.json` records the
    seed and the resolved weight inputs rather than leaving them to be
    recomputed against a log that has since moved on.
    """
    first = generate(tmp_path, date(2026, 8, 9))
    for day in (10, 11, 12):
        generate(tmp_path, date(2026, 8, day))

    again = session.replay(tmp_path, date(2026, 8, 9))

    assert again.exercises == first.exercises
    assert again.weight_inputs == first.weight_inputs
    assert again.seed == first.seed
    assert again.config_hash == first.config_hash


def test_recomputing_against_the_grown_log_would_not_reproduce_the_day(tmp_path: Path) -> None:
    """The test above is not vacuous: the log genuinely moved on.

    Re-drawing the original seed against today's history computes different
    weights than the original run did, because those three later sessions
    pushed values onto the log the first run had never seen. That divergence is
    the whole reason the inputs are recorded rather than recomputed.
    """
    first = generate(tmp_path, date(2026, 8, 9))
    for day in (10, 11, 12):
        generate(tmp_path, date(2026, 8, day))

    redrawn = select(config(), session.history(tmp_path, HORIZON), seeded(first.seed))

    assert [inputs for _spec, inputs in redrawn] != list(first.weight_inputs)


def test_replay_needs_only_the_recorded_session(tmp_path: Path) -> None:
    """`session.json` is self-sufficient: no configuration, no surrounding log."""
    first = generate(tmp_path, date(2026, 8, 9))
    for day in (10, 11, 12):
        generate(tmp_path, date(2026, 8, day))
    for day in (10, 11, 12):
        (session.directory(tmp_path, date(2026, 8, day)) / session.FILENAME).unlink()

    assert session.replay(tmp_path, date(2026, 8, 9)).exercises == first.exercises
