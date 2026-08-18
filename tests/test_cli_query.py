"""Tests for the read-only commands — `replay`, `show`, `families`, `vocabulary`.

These four share one property that shapes every test here: **none of them
draws**. `generate` is the only command that calls the selector, so nothing in
this module asserts anything about which exercises were chosen. What it asserts
is that a recorded day comes back the way it was recorded, and that the two
listing commands read their content out of the registries rather than restating
it.

**On replay's semantics.** `replay` is a read-back, not a re-execution: it
re-engraves the exercises `session.json` already holds. The test that matters
is therefore `test_replay_reproduces_the_source_it_replayed` — the generated
alphaTex, byte for byte, after two later sessions have moved the history on.
A test that asserted the *draw* would be testing a feature this command does
not have; see `cli._replay`'s docstring.

**On the fake binary.** The same device `tests/test_cli_generate.py`
established: a real executable named `node` on `PATH`, so `shutil.which` and
`subprocess.run` both do the real thing and only the engraving is faked. The
end-to-end test at the bottom uses the real alphaTab toolchain.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from melete import cli, rhythm, session, vocabulary
from melete.alphatab import render as render_module
from melete.families import REGISTRY

if TYPE_CHECKING:
    from collections.abc import Callable

#: The day every test records and then reads back. A fixed past date rather
#: than today's, because `replay` and `show` are about a session that is over.
RECORDED = date(2026, 8, 9)

#: Two days generated after `RECORDED`, so the log has moved on before anything
#: is replayed. Without them a read-back and a re-derivation would agree, and
#: the test would pass for either implementation.
LATER = (date(2026, 8, 10), date(2026, 8, 11))

# --------------------------------------------------------------------------
# A working configuration (spec §10)
# --------------------------------------------------------------------------

TEMPLATE = """\
[instrument]
profile = "{profile}"

[session]
count = 3
horizon = 14

[pool.scales]
roots = "all"
scale_types = ["ionian", "dorian", "phrygian", "lydian", "mixolydian", "aeolian"]
traversals = ["positional"]
patterns = ["straight", "thirds"]
tempo = [{slowest}, {fastest}]

[pool.chromatic]
permutations = [[1, 2, 3, 4], [1, 3, 2, 4], [2, 1, 4, 3], [4, 3, 2, 1]]
start_strings = [0, 1, 2]
start_frets = [1, 3, 5, 7]
string_traversals = ["adjacent"]
shifts = ["none", "fret_per_cycle"]
spans = [3, 4]

[pool.rhythm]
accent_patterns = ["none", "every_3"]
note_value_patterns = ["straight", "long_short"]
"""


def write_config(
    project: Path, *, profile: str = "bass6", slowest: int = 80, fastest: int = 100
) -> None:
    """Install a configuration at the project root, varying what replay reads.

    The three parameters are exactly the settings `replay` takes from the
    configuration rather than from the record: the instrument it engraves for,
    and the tempo range it prints.
    """
    text = TEMPLATE.format(profile=profile, slowest=slowest, fastest=fastest)
    (project / "config.toml").write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project root holding a working configuration, with the process inside it."""
    root = tmp_path / "project"
    root.mkdir()
    write_config(root)
    monkeypatch.chdir(root)
    return root


#: A fake `node` body that writes the local-file-header magic of a `.gp` (a ZIP)
#: to stdout, which is where `melete-render` writes the rendered bytes.
WRITES_A_GP = r"printf 'PK\003\004'"


@pytest.fixture
def node(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[[], None]:
    """Install a fake `node` on a *prepended* `PATH`.

    Prepended rather than replaced (as `tests/alphatab/test_render.py` does) so
    the fake body's coreutils — `printf` — stay reachable. The fake still wins the
    `shutil.which` lookup, so a real Node baked into the container cannot be
    picked up in its place and the render stays deterministic.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    def install() -> None:
        executable = bin_dir / "node"
        executable.write_text(f"#!/bin/sh\n{WRITES_A_GP}\n", encoding="utf-8")
        executable.chmod(0o755)
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    return install


@dataclass(frozen=True)
class Result:
    """One CLI invocation: its exit status and both of its streams."""

    exit_code: int
    stdout: str
    stderr: str


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Callable[[list[str]], Result]:
    """Invoke `main` in-process, so a failure surfaces as the CLI's own message."""

    def invoke(argv: list[str]) -> Result:
        code = cli.main(argv)
        captured = capsys.readouterr()
        return Result(exit_code=code, stdout=captured.out, stderr=captured.err)

    return invoke


def book_source(project: Path, on: date) -> str:
    return (session.directory(project, on) / cli.SOURCES / "book.atex").read_text(encoding="utf-8")


def log_text(project: Path, on: date) -> str:
    return (session.directory(project, on) / session.FILENAME).read_text(encoding="utf-8")


def generate_a_history(run: Callable[[list[str]], Result], *, days: int = 2) -> None:
    """Record `RECORDED`, then move the log on past it.

    Every later day matters: §9 weights a draw by how many sessions have passed
    since each value was last used, so a re-derivation of `RECORDED` against
    this log computes different weights than the original run did. A read-back
    is unaffected, which is the difference these tests exist to pin.
    """
    assert run(["generate", "--date", RECORDED.isoformat()]).exit_code == 0
    for later in LATER[:days]:
        assert run(["generate", "--date", later.isoformat()]).exit_code == 0


# --------------------------------------------------------------------------
# replay (spec §9 Determinism, §11)
# --------------------------------------------------------------------------


def test_replay_reproduces_the_source_it_replayed(
    project: Path, run: Callable[[list[str]], Result], node: Callable[[], None]
) -> None:
    """The whole guarantee, and the only test that can distinguish the designs.

    Two sessions were generated after this one, so the history a re-derivation
    would weight against has moved. The engraved source has to come back byte
    for byte anyway, because it is derived from the recorded exercises rather
    than from a fresh draw.
    """
    node()
    generate_a_history(run)
    first = book_source(project, RECORDED)

    result = run(["replay", RECORDED.isoformat()])

    assert result.exit_code == 0
    assert book_source(project, RECORDED) == first


def test_replay_leaves_the_record_exactly_as_it_found_it(
    project: Path, run: Callable[[list[str]], Result], node: Callable[[], None]
) -> None:
    """`replay` reads the log; it never writes one.

    A replay that rewrote `session.json` would be a second author of the
    history every later draw is weighted against, which is the one file §12
    makes the record rather than an output.
    """
    node()
    generate_a_history(run)
    before = log_text(project, RECORDED)

    run(["replay", RECORDED.isoformat()])

    assert log_text(project, RECORDED) == before


def test_replay_re_renders_the_sheet(
    project: Path, run: Callable[[list[str]], Result], node: Callable[[], None]
) -> None:
    """The point of the command: a lost `.gp` comes back."""
    node()
    generate_a_history(run, days=1)
    (session.directory(project, RECORDED) / "practice.gp").unlink()

    assert run(["replay", RECORDED.isoformat()]).exit_code == 0

    assert (session.directory(project, RECORDED) / "practice.gp").exists()


def test_replay_replaces_the_sources_rather_than_writing_into_them(
    project: Path, run: Callable[[list[str]], Result], node: Callable[[], None]
) -> None:
    """A source left over from the run being replaced is not part of this one."""
    node()
    generate_a_history(run, days=1)
    stale = session.directory(project, RECORDED) / cli.SOURCES / "exercise-99.atex"
    stale.write_text("// not from this session\n", encoding="utf-8")

    run(["replay", RECORDED.isoformat()])

    assert not stale.exists()


def test_replay_works_when_the_sources_are_gone(
    project: Path, run: Callable[[list[str]], Result], node: Callable[[], None]
) -> None:
    """`src/` is an output, not an input: the record is what replay reads."""
    node()
    generate_a_history(run, days=1)
    shutil.rmtree(session.directory(project, RECORDED) / cli.SOURCES)

    assert run(["replay", RECORDED.isoformat()]).exit_code == 0

    assert (session.directory(project, RECORDED) / cli.SOURCES / "book.atex").exists()


def test_replay_prints_where_it_wrote(
    project: Path, run: Callable[[list[str]], Result], node: Callable[[], None]
) -> None:
    node()
    generate_a_history(run, days=1)

    out = run(["replay", RECORDED.isoformat()]).stdout

    assert str(session.directory(project, RECORDED) / "practice.gp") in out


def test_replay_refuses_to_engrave_a_session_for_another_instrument(
    project: Path, run: Callable[[list[str]], Result], node: Callable[[], None]
) -> None:
    """A fret number is a fact about one instrument (§5).

    The recorded exercises hold string indices and roots; the profile decides
    what those reach. Engraving them against a different bass would produce
    tablature that reads as music and is wrong, which is the failure §5 refuses
    to let a re-sorted tuning cause.
    """
    node()
    generate_a_history(run, days=1)
    write_config(project, profile="bass4")

    result = run(["replay", RECORDED.isoformat()])

    assert result.exit_code != 0
    assert "bass6" in result.stderr
    assert "bass4" in result.stderr


def test_replay_says_so_when_the_configuration_has_moved_on(
    project: Path, run: Callable[[list[str]], Result], node: Callable[[], None]
) -> None:
    """The tempo and the staff mode are read from the configuration as it is now.

    That is not hidden. The exercises are the recorded ones either way, but a
    replayed sheet whose tempo mark differs from the one that was practised has
    to say why rather than let the reader discover it. alphaTab's tempo is a
    single value, so the range's slowest is the one engraved.
    """
    node()
    generate_a_history(run, days=1)
    write_config(project, slowest=61, fastest=62)

    result = run(["replay", RECORDED.isoformat()])

    assert result.exit_code == 0
    assert "configuration has changed" in result.stdout
    assert "\\tempo 61" in book_source(project, RECORDED)


def test_replay_restores_the_order_the_parameters_were_drawn_in(
    project: Path, run: Callable[[list[str]], Result], node: Callable[[], None]
) -> None:
    """The record is key-sorted (§12); the cover page is not.

    §12 generates each cover entry by walking `params`, so a replay that took
    the alphabetical order JSON hands back would print the same exercise's axes
    in a different order than the sheet it reproduces. The order is the
    family's declared axes then §8's rhythm axes, which is how the selector
    builds one.
    """
    node()
    generate_a_history(run, days=1)
    first = session.replay(project, RECORDED).exercises[0]
    assert list(first.params) == sorted(first.params), "the record comes back alphabetical"

    restored = cli.ordered(first)

    declared = [*REGISTRY[first.family].axes, *rhythm.AXES]
    # `scales` (H2) and `arpeggios` (G3) derive `hands`, an axis no family
    # *declares*: the selector adds it after the declared axes, so `ordered` keeps
    # it — and any other undeclared recorded axis — at the end, in read order.
    expected = [axis for axis in declared if axis in first.params]
    expected += [axis for axis in first.params if axis not in declared]
    assert list(restored.params) == expected
    assert restored.params == first.params


def test_replay_keeps_a_recorded_axis_no_family_declares(
    project: Path, run: Callable[[list[str]], Result], node: Callable[[], None]
) -> None:
    """§12 makes the log hand-editable, so an unrecognised axis is data, not litter.

    The family carries an extra `params` key untouched (its `generate` reads the
    axes it declares and ignores the rest), so replay tolerates the record and
    `cli.ordered` keeps the axis rather than dropping it to tidy the ordering —
    losing a recorded parameter would be a silent loss of the thing reproduced.
    """
    node()
    generate_a_history(run, days=1)
    log = session.directory(project, RECORDED) / session.FILENAME
    document = json.loads(log.read_text(encoding="utf-8"))
    document["exercises"][0]["params"]["annotation"] = "kept"
    log.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    assert run(["replay", RECORDED.isoformat()]).exit_code == 0

    replayed = cli.ordered(session.replay(project, RECORDED).exercises[0])
    assert replayed.params["annotation"] == "kept"


def test_replay_names_a_recorded_family_that_does_not_exist(
    project: Path, run: Callable[[list[str]], Result], node: Callable[[], None]
) -> None:
    """A hand-edited log is a value to correct, not a traceback (§12, §13)."""
    node()
    generate_a_history(run, days=1)
    log = session.directory(project, RECORDED) / session.FILENAME
    document = json.loads(log.read_text(encoding="utf-8"))
    document["exercises"][0]["family"] = "banjo"
    log.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = run(["replay", RECORDED.isoformat()])

    assert result.exit_code != 0
    assert "banjo" in result.stderr
    assert str(log) in result.stderr
    assert "Traceback" not in result.stderr


def test_replay_on_a_missing_session_fails_loudly_naming_the_date(
    project: Path, run: Callable[[list[str]], Result]
) -> None:
    result = run(["replay", "1999-01-01"])

    assert result.exit_code != 0
    assert "1999-01-01" in result.stderr
    assert "Traceback" not in result.stderr


def test_a_date_that_is_not_a_date_is_refused_by_the_parser(
    project: Path, run: Callable[[list[str]], Result], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        run(["replay", "2026-13-01"])

    assert exc.value.code == 2
    assert "2026-13-01" in capsys.readouterr().err


# --------------------------------------------------------------------------
# show (spec §11, §12)
# --------------------------------------------------------------------------


def test_show_summarizes_a_past_session(
    project: Path, run: Callable[[list[str]], Result], node: Callable[[], None]
) -> None:
    node()
    generate_a_history(run, days=1)

    out = run(["show", RECORDED.isoformat()]).stdout

    assert RECORDED.isoformat() in out
    assert "bass6" in out
    assert str(session.replay(project, RECORDED).seed) in out


def test_show_prints_one_line_per_recorded_exercise(
    project: Path, run: Callable[[list[str]], Result], node: Callable[[], None]
) -> None:
    node()
    generate_a_history(run, days=1)
    recorded = session.replay(project, RECORDED)

    out = run(["show", RECORDED.isoformat()]).stdout

    numbered = [line for line in out.splitlines() if re.match(r"\s*\d+\. ", line)]
    assert len(numbered) == len(recorded.exercises)
    assert all(spec.family in out for spec in recorded.exercises)


def test_show_reports_the_recorded_instrument_not_the_current_configuration(
    project: Path, run: Callable[[list[str]], Result], node: Callable[[], None]
) -> None:
    """History is what happened, not what the configuration says today.

    A profile edited since the session was generated would otherwise make
    `show` misreport every day before the edit, silently and in the one command
    whose whole job is to report the record.
    """
    node()
    generate_a_history(run, days=1)
    write_config(project, profile="bass4")

    out = run(["show", RECORDED.isoformat()]).stdout

    assert "bass6" in out
    assert "bass4" not in out


def test_show_survives_a_configuration_it_could_not_load(
    project: Path, run: Callable[[list[str]], Result], node: Callable[[], None]
) -> None:
    """`show` reads the record and nothing else, so a broken config cannot stop it."""
    node()
    generate_a_history(run, days=1)
    (project / "config.toml").write_text("[session]\ncount = 0\n", encoding="utf-8")

    assert run(["show", RECORDED.isoformat()]).exit_code == 0


def test_show_names_values_the_way_the_cover_page_does(
    project: Path, run: Callable[[list[str]], Result], node: Callable[[], None]
) -> None:
    """§13's registry is the one source of display names, so the two cannot disagree."""
    node()
    generate_a_history(run, days=1)

    out = run(["show", RECORDED.isoformat()]).stdout

    recorded = session.replay(project, RECORDED)
    expected = {
        vocabulary.display(axis, str(value))
        for spec in recorded.exercises
        for axis, value in spec.params.items()
        if axis in vocabulary.AXES
    }
    assert expected
    assert all(name in out for name in expected)


def test_show_still_reports_a_family_the_registry_does_not_know(
    project: Path, run: Callable[[list[str]], Result], node: Callable[[], None]
) -> None:
    """`show` reports a record; it does not judge whether that record can be engraved.

    `replay` refuses the same file, because it has to hand the exercise to a
    family that is not there. Reporting what the log says is a different job
    and is still answerable.
    """
    node()
    generate_a_history(run, days=1)
    log = session.directory(project, RECORDED) / session.FILENAME
    document = json.loads(log.read_text(encoding="utf-8"))
    document["exercises"][0]["family"] = "banjo"
    log.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = run(["show", RECORDED.isoformat()])

    assert result.exit_code == 0
    assert "banjo" in result.stdout


def test_show_prints_the_axes_in_the_order_they_were_drawn(
    project: Path, run: Callable[[list[str]], Result], node: Callable[[], None]
) -> None:
    """The same order §12's cover page uses, so the two read the same way round."""
    node()
    generate_a_history(run, days=1)
    first = session.replay(project, RECORDED).exercises[0]

    line = run(["show", RECORDED.isoformat()]).stdout.splitlines()[1]

    drawn = cli.ordered(first).params
    positions = [line.index(cli.phrase(axis, value)) for axis, value in drawn.items()]
    assert positions == sorted(positions)


def test_show_on_a_missing_session_fails_loudly_naming_the_date(
    project: Path, run: Callable[[list[str]], Result]
) -> None:
    result = run(["show", "1999-01-01"])

    assert result.exit_code != 0
    assert "1999-01-01" in result.stderr
    assert "Traceback" not in result.stderr


def test_show_on_a_corrupt_log_names_the_file(
    project: Path, run: Callable[[list[str]], Result]
) -> None:
    """§13's row, unsoftened: a corrupt record is a hard error naming the file."""
    directory = session.directory(project, RECORDED)
    directory.mkdir(parents=True)
    (directory / session.FILENAME).write_text("{ not json", encoding="utf-8")

    result = run(["show", RECORDED.isoformat()])

    assert result.exit_code != 0
    assert str(directory / session.FILENAME) in result.stderr


@pytest.mark.parametrize("command", ["show", "replay"])
def test_an_incomplete_session_directory_says_it_can_be_deleted(
    project: Path, run: Callable[[list[str]], Result], command: str
) -> None:
    """The state a failed render leaves behind: sources, and no log (§13).

    `session.read` reports this as "cannot be read", which is true and is not
    an instruction. The directory exists, so the CLI knows something the reader
    does not — that this is a run that did not complete, and that deleting it
    is the repair.
    """
    directory = session.directory(project, RECORDED)
    (directory / cli.SOURCES).mkdir(parents=True)

    result = run([command, RECORDED.isoformat()])

    assert result.exit_code != 0
    assert RECORDED.isoformat() in result.stderr
    assert str(directory) in result.stderr
    assert "delete" in result.stderr


# --------------------------------------------------------------------------
# families (spec §7, §11)
# --------------------------------------------------------------------------


def test_families_lists_every_family_with_its_axes(run: Callable[[list[str]], Result]) -> None:
    """Read out of `REGISTRY`, so a fifth family needs no change here."""
    result = run(["families"])

    assert result.exit_code == 0
    for name, family in REGISTRY.items():
        assert name in result.stdout
        for axis in family.axes:
            assert axis in result.stdout


def test_families_prints_the_tempo_range_each_family_declares(
    run: Callable[[list[str]], Result],
) -> None:
    """§7's tempo is the family's own, not a sampled axis (decision #20)."""
    out = run(["families"]).stdout

    for family in REGISTRY.values():
        slowest, fastest = family.default_tempo_range
        assert f"{slowest}-{fastest}" in out


def test_families_names_the_rhythm_axes_that_cross_all_four(
    run: Callable[[list[str]], Result],
) -> None:
    """§8: rhythm is a modifier over every family, not a fifth family."""
    out = run(["families"]).stdout

    assert "rhythm" in out
    for axis in rhythm.AXES:
        assert axis in out


# --------------------------------------------------------------------------
# vocabulary (spec §11, §13)
# --------------------------------------------------------------------------


def test_vocabulary_lists_every_axis_and_every_accepted_value(
    run: Callable[[list[str]], Result],
) -> None:
    result = run(["vocabulary"])

    assert result.exit_code == 0
    for axis, values in vocabulary.AXES.items():
        assert axis in result.stdout
        for identifier, display in values.items():
            assert identifier in result.stdout
            assert display in result.stdout


def test_vocabulary_names_the_range_axes_it_deliberately_omits(
    run: Callable[[list[str]], Result],
) -> None:
    """A list that looked exhaustive and was not would be read as one.

    `root`, the fret numbers, the interval and the permutation are validated
    against the instrument profile (§5) rather than against an enumerated set, so
    they carry no registry entry — and a reader who could not see that would
    conclude the tool has no such axes. Octave counts and string sets used to
    join them here; epic #72 retired both from every family (extent is now
    emergent and coverage spans the whole instrument), so no family reads them
    and they no longer appear among the omitted range axes.
    """
    omitted = {axis for family in REGISTRY.values() for axis in family.axes}
    omitted.update(rhythm.AXES)
    omitted -= set(vocabulary.AXES)

    out = run(["vocabulary"]).stdout

    assert omitted == {
        "interval",
        "permutation",
        "root",
        "span",
        "start_fret",
        "start_string",
    }
    for axis in omitted:
        assert axis in out
    # The retired axes (epic #72) must not resurface in the range-note prose.
    assert "octave count" not in out
    assert "string set" not in out
    assert "range_octaves" not in out
    assert "string_set" not in out


# --------------------------------------------------------------------------
# The subcommands spec §11 documents
# --------------------------------------------------------------------------


def test_the_command_table_is_exactly_the_documented_subcommands() -> None:
    """One table builds both the parser and the dispatch, so they cannot disagree.

    What the table can still get wrong is its *contents*, which is what this
    pins: §11 documents five subcommands and the tool offers those five.
    """
    assert set(cli.COMMANDS) == {"generate", "replay", "show", "families", "vocabulary"}


# --------------------------------------------------------------------------
# Spec §14: the end-to-end test that needs the real toolchain
# --------------------------------------------------------------------------

#: A trivial, renderer-indifferent alphaTex — a title, the `.` header terminator,
#: and one beat — whose render is the only honest probe for "is the whole
#: toolchain here?": Node, the `melete-render` script, and `@coderline/alphatab`
#: on `NODE_PATH` must all be present, and only a real render exercises all three.
PROBE_ALPHATEX = r'\title "probe" . 3.3.4'


def _alphatab_toolchain_available() -> bool:
    """True when a real alphaTex render actually produces a `.gp`."""
    try:
        with tempfile.TemporaryDirectory() as tmp:
            render_module.render(PROBE_ALPHATEX, Path(tmp))
    except render_module.RenderError:
        return False
    return True


ALPHATAB_ON_PATH = _alphatab_toolchain_available()

NO_TOOLCHAIN = (
    "The alphaTab toolchain is not reachable. Spec §14 requires the binary-dependent "
    "tests to fail loudly rather than skip silently in any environment that claims to run "
    "the full suite. melete renders through melete-render, a Node tool driving alphaTab: "
    "Node must be on PATH, the render.js script must sit at the repo root, and "
    "@coderline/alphatab must be importable (the container bakes it globally on NODE_PATH, "
    "melete#85). Inside `vrg-container-run` all three hold and this test runs; a bare host "
    "without alphaTab installed skips it."
)


@pytest.mark.integration
@pytest.mark.skipif(not ALPHATAB_ON_PATH, reason=NO_TOOLCHAIN)
def test_replay_reproduces_a_real_sheet_end_to_end(
    project: Path, run: Callable[[list[str]], Result]
) -> None:
    """`replay` against the real engraver, with the log moved on past the day.

    Two things are compared, and each answers a different question. The alphaTex
    source is compared **byte for byte**: that is the whole pipeline from the
    record to the engraver's input, and it is the artifact that can be identical.
    The rendered `.gp` is checked only for its ZIP magic — a Guitar Pro file may
    carry render-time metadata, so two renders of one source need not be
    byte-identical — and the record is compared to itself, to pin that replay
    wrote none.
    """
    assert run(["generate", "--date", RECORDED.isoformat()]).exit_code == 0
    first_source = book_source(project, RECORDED)
    first_log = log_text(project, RECORDED)
    directory = session.directory(project, RECORDED)

    for later in LATER:
        assert run(["generate", "--date", later.isoformat()]).exit_code == 0
    shutil.rmtree(directory / cli.SOURCES)
    (directory / "practice.gp").unlink()

    assert run(["replay", RECORDED.isoformat()]).exit_code == 0

    assert book_source(project, RECORDED) == first_source
    assert log_text(project, RECORDED) == first_log
    # A `.gp` is a ZIP; its local-file-header magic is exactly `PK\x03\x04`.
    assert (directory / "practice.gp").read_bytes().startswith(b"PK\x03\x04")
