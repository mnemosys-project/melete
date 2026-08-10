"""Tests for `melete generate` — the command that produces a practice sheet.

This is the first module that runs spec §4's pipeline end to end, so the tests
here are about *composition* rather than about any one stage: the flags of §11,
the directory layout of §12 — which is a contract, not a suggestion — and the
three rows of §13 the CLI owns (an existing session directory, a failed render,
a missing binary).

**On the fake binary.** LilyPond is not installed in the dev container and is
not a Python dependency (spec §15, decision #23), so the render path is covered
here the way `tests/lilypond/test_render.py` established: a small real
executable named `lilypond` is written into a directory and `PATH` is replaced
with it. Nothing is patched out — `shutil.which` does the real lookup and
`subprocess.run` really forks — so what is faked is the engraving and nothing
else. The fake here differs from the render module's in one respect: it reads
`-o` out of its own argv, because a session renders the book and then one
document per exercise into the same directory and each has to land on its own
name.

`test_end_to_end_produces_a_practice_pdf` is the real thing, and it is the test
spec §14 assigns to this module. It runs the moment LilyPond is on PATH.
"""

from __future__ import annotations

import json
import re
import shutil
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from melete import cli, session

if TYPE_CHECKING:
    from collections.abc import Callable

REPO_ROOT = Path(__file__).resolve().parent.parent

TODAY = date.today()

# --------------------------------------------------------------------------
# A working configuration (spec §10), as a template the odd test varies
# --------------------------------------------------------------------------

#: Two families, both carrying a tuple axis — `string_set` and `permutation` —
#: because those are the values that travel furthest through the pipeline. No
#: `shape`, so `--count` is free to override the count (see the shape test).
SESSION = """\
count = 2
horizon = 14
"""

SCALES = """\
roots = "all"
scale_types = ["ionian", "dorian", "phrygian", "lydian", "mixolydian", "aeolian"]
traversals = ["positional"]
string_sets = [[0, 1, 2, 3], [1, 2, 3, 4], [2, 3, 4, 5]]
patterns = ["straight", "thirds"]
octaves = [1, 2]
directions = ["up", "down", "up_down"]
"""

TEMPLATE = """\
[instrument]
profile = "bass6"

[output]
staves = "both"
key_signatures = true

[session]
{session}

[pool.scales]
{scales}

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


def write_config(project: Path, *, session: str = SESSION, scales: str = SCALES) -> None:
    """Install a configuration at the project root, varying at most two sections."""
    text = TEMPLATE.format(session=session, scales=scales)
    (project / "config.toml").write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------
# Fixtures: a project directory, a fake binary, and a way to run the CLI
# --------------------------------------------------------------------------


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project root holding a working `config.toml`, and the process inside it.

    The CLI resolves both the configuration and `sessions/` against the working
    directory: §11 gives `generate` seven flags and none of them is a path, so
    the directory the command is run from *is* the project.
    """
    root = tmp_path / "project"
    root.mkdir()
    write_config(root)
    monkeypatch.chdir(root)
    return root


#: Writes an empty file at whatever `-o` names, which is what LilyPond does
#: with `--pdf`. Reading argv rather than hard-coding a name is what lets one
#: fake serve the book render and every `--split` render in the same directory.
WRITES_A_PDF = """\
previous=""
for argument in "$@"; do
  if [ "$previous" = "-o" ]; then : > "$argument.pdf"; fi
  previous="$argument"
done
"""


@pytest.fixture
def lilypond(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Install a `lilypond` on `PATH` whose body is the given shell script.

    `PATH` is replaced rather than prepended so that a real LilyPond on the
    host can never be picked up by accident: these tests must behave the same
    on a machine that has the binary and on one that does not.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    def install(body: str = WRITES_A_PDF) -> None:
        executable = bin_dir / "lilypond"
        executable.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        executable.chmod(0o755)
        monkeypatch.setenv("PATH", str(bin_dir))

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


def session_of(project: Path, on: date) -> session.Session:
    return session.read(session.directory(project, on))


def sources(project: Path, on: date) -> list[Path]:
    return sorted((session.directory(project, on) / cli.SOURCES).glob("*.ly"))


# --------------------------------------------------------------------------
# The flags of spec §11
# --------------------------------------------------------------------------


def test_dry_run_prints_selections_and_renders_nothing(
    project: Path, run: Callable[[list[str]], Result]
) -> None:
    result = run(["generate", "--dry-run"])

    assert result.exit_code == 0
    assert not list(project.glob("**/*.pdf"))
    assert "scales" in result.stdout or "chromatic" in result.stdout


def test_dry_run_writes_nothing_at_all_not_even_the_session_directory(
    project: Path, run: Callable[[list[str]], Result]
) -> None:
    """A dry run that logged a session would poison every later draw's history."""
    assert run(["generate", "--dry-run"]).exit_code == 0

    assert not (project / session.SESSIONS).exists()


def test_dry_run_names_values_the_way_the_cover_page_does(
    project: Path, run: Callable[[list[str]], Result]
) -> None:
    """§13's registry is the one source of display names; the preview reads it."""
    out = run(["generate", "--count", "6", "--dry-run"]).stdout

    assert TODAY.isoformat() in out
    assert "bass6" in out
    assert "seed" in out


def test_date_writes_to_that_dated_directory(
    project: Path, run: Callable[[list[str]], Result], lilypond: Callable[..., None]
) -> None:
    lilypond()

    assert run(["generate", "--date", "2026-08-10"]).exit_code == 0

    assert (project / "sessions" / "2026-08-10").is_dir()
    assert session_of(project, date(2026, 8, 10)).date == date(2026, 8, 10)


def test_a_date_that_is_not_a_date_is_refused_by_the_parser(
    project: Path, run: Callable[[list[str]], Result], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        run(["generate", "--date", "2026-13-01"])

    assert exc.value.code == 2
    assert "2026-13-01" in capsys.readouterr().err


def test_seed_fixes_the_draw_against_the_current_history(
    project: Path, run: Callable[[list[str]], Result], lilypond: Callable[..., None]
) -> None:
    lilypond()

    assert run(["generate", "--seed", "12345"]).exit_code == 0

    assert session_of(project, TODAY).seed == 12345


def test_without_a_seed_the_date_and_the_configuration_derive_one(
    project: Path, run: Callable[[list[str]], Result], lilypond: Callable[..., None]
) -> None:
    """§9: the same day against the same configuration is the same sheet."""
    lilypond()
    run(["generate", "--date", "2026-08-10"])

    logged = session_of(project, date(2026, 8, 10))

    assert logged.seed == session.seed_for(date(2026, 8, 10), logged.config_hash)


def test_count_overrides_the_configured_exercise_count(
    project: Path, run: Callable[[list[str]], Result], lilypond: Callable[..., None]
) -> None:
    lilypond()

    assert run(["generate", "--count", "6"]).exit_code == 0

    assert len(session_of(project, TODAY).exercises) == 6


def test_count_against_a_declared_shape_is_refused_rather_than_guessed(
    project: Path, run: Callable[[list[str]], Result], lilypond: Callable[..., None]
) -> None:
    """The contradiction `config` already refuses in the file, arriving by flag.

    `[session] shape` names one family per slot, so a count that disagrees with
    it is the same wrong-session question `session.count` is refused for — and
    guessing which of the two the user meant is what §13 forbids.
    """
    lilypond()
    write_config(project, session="shape = { scales = 1 }")

    result = run(["generate", "--count", "3"])

    assert result.exit_code != 0
    assert "shape" in result.stderr
    assert "--count" in result.stderr
    assert not (project / session.SESSIONS).exists()


@pytest.mark.parametrize(
    ("flag", "value", "complaint"),
    [
        # A count of zero asks the emitter for a book with no exercises, and a
        # negative seed writes a log `session.read` then refuses (§13). Both
        # are bounded at the flag, where the message can name it.
        ("--count", "0", "1 or greater"),
        ("--seed", "-1", "0 or greater"),
        ("--count", "several", "not an integer"),
    ],
)
def test_a_numeric_flag_is_bounded_where_it_is_named(
    project: Path,
    run: Callable[[list[str]], Result],
    capsys: pytest.CaptureFixture[str],
    flag: str,
    value: str,
    complaint: str,
) -> None:
    with pytest.raises(SystemExit) as exc:
        run(["generate", flag, value])

    assert exc.value.code == 2
    error = capsys.readouterr().err
    assert flag in error
    assert complaint in error


def test_staves_override_reaches_the_emitter(
    project: Path, run: Callable[[list[str]], Result], lilypond: Callable[..., None]
) -> None:
    lilypond()

    assert run(["generate", "--staves", "tab"]).exit_code == 0

    book = (session.directory(project, TODAY) / cli.SOURCES / "book.ly").read_text(encoding="utf-8")
    assert "\\tabFullNotation" in book


def test_an_unknown_staff_mode_is_refused_with_its_accepted_values(
    project: Path, run: Callable[[list[str]], Result], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        run(["generate", "--staves", "treble"])

    assert exc.value.code == 2
    assert "tab" in capsys.readouterr().err


def test_split_emits_one_pdf_per_exercise_plus_the_book(
    project: Path, run: Callable[[list[str]], Result], lilypond: Callable[..., None]
) -> None:
    lilypond()

    assert run(["generate", "--count", "3", "--split"]).exit_code == 0

    directory = session.directory(project, TODAY)
    assert (directory / "practice.pdf").exists()
    assert len(list(directory.glob("exercise-*.pdf"))) == 3


def test_without_split_only_the_combined_pdf_is_written(
    project: Path, run: Callable[[list[str]], Result], lilypond: Callable[..., None]
) -> None:
    lilypond()

    assert run(["generate", "--count", "3"]).exit_code == 0

    directory = session.directory(project, TODAY)
    assert (directory / "practice.pdf").exists()
    assert not list(directory.glob("exercise-*.pdf"))


# --------------------------------------------------------------------------
# Spec §12: the directory layout is a contract
# --------------------------------------------------------------------------


def test_the_session_directory_holds_exactly_what_the_spec_lists(
    project: Path, run: Callable[[list[str]], Result], lilypond: Callable[..., None]
) -> None:
    lilypond()

    run(["generate", "--count", "3"])

    directory = session.directory(project, TODAY)
    assert sorted(entry.name for entry in directory.iterdir()) == [
        "practice.pdf",
        "session.json",
        "src",
    ]


def test_source_is_kept_per_exercise_and_for_the_book(
    project: Path, run: Callable[[list[str]], Result], lilypond: Callable[..., None]
) -> None:
    """§12 keeps the generated source *per exercise and for the book*.

    Counted rather than checked for existence: an `is_dir()` assertion cannot
    fail when the per-exercise sources are the output that went missing.
    """
    lilypond()

    run(["generate", "--count", "3"])

    logged = session_of(project, TODAY)
    names = [path.name for path in sources(project, TODAY)]
    assert len(names) == len(logged.exercises) + 1
    assert names == ["book.ly", "exercise-01.ly", "exercise-02.ly", "exercise-03.ly"]


def test_the_book_carries_the_cover_page_and_every_exercise(
    project: Path, run: Callable[[list[str]], Result], lilypond: Callable[..., None]
) -> None:
    lilypond()

    run(["generate", "--count", "3"])

    book = (session.directory(project, TODAY) / cli.SOURCES / "book.ly").read_text(encoding="utf-8")
    assert "Practice session" in book
    assert f"{TODAY.isoformat()} — bass6" in book
    assert book.count("\\score") == 3


def test_the_pool_tempo_override_reaches_the_engraved_page(
    project: Path, run: Callable[[list[str]], Result], lilypond: Callable[..., None]
) -> None:
    """§10's `[pool.<family>] tempo` overrides the family default (decision #20).

    Nothing between the pool and the page applies it — a family states its own
    default and `rhythm` carries it through untouched — so this is the wiring
    that makes the documented override anything other than a comment.
    """
    lilypond()
    write_config(
        project,
        session="shape = { scales = 1 }",
        scales=SCALES + "tempo = [61, 62]\n",
    )

    run(["generate"])

    book = (session.directory(project, TODAY) / cli.SOURCES / "book.ly").read_text(encoding="utf-8")
    assert "61-62 bpm" in book


# --------------------------------------------------------------------------
# Spec §13: an existing session directory is refused
# --------------------------------------------------------------------------


def test_generate_refuses_an_existing_session_without_force(
    project: Path, run: Callable[[list[str]], Result], lilypond: Callable[..., None]
) -> None:
    lilypond()
    assert run(["generate"]).exit_code == 0

    refused = run(["generate"])

    assert refused.exit_code != 0
    assert "--force" in refused.stderr
    assert str(session.directory(project, TODAY)) in refused.stderr
    assert run(["generate", "--force"]).exit_code == 0


def test_a_dry_run_of_an_already_generated_day_is_refused_too(
    project: Path, run: Callable[[list[str]], Result], lilypond: Callable[..., None]
) -> None:
    """§13's row has no exception, and the day *is* already generated."""
    lilypond()
    run(["generate"])

    assert run(["generate", "--dry-run"]).exit_code != 0


def test_force_replaces_the_directory_rather_than_merging_into_it(
    project: Path, run: Callable[[list[str]], Result], lilypond: Callable[..., None]
) -> None:
    """Yesterday's `--split` PDFs must not be presented as today's session."""
    lilypond()
    run(["generate", "--count", "3", "--split"])

    run(["generate", "--count", "3", "--force"])

    assert not list(session.directory(project, TODAY).glob("exercise-*.pdf"))


def test_a_forced_regeneration_reproduces_the_session_it_replaced(
    project: Path, run: Callable[[list[str]], Result], lilypond: Callable[..., None]
) -> None:
    """§9's determinism: the same date and configuration draw the same sheet.

    The day being regenerated must not be part of the history it is weighted
    against, or every `--force` would hand back a different sheet than the run
    before it and nothing would say why.
    """
    lilypond()
    run(["generate", "--date", "2026-08-10"])
    first = (session.directory(project, date(2026, 8, 10)) / session.FILENAME).read_text(
        encoding="utf-8"
    )

    run(["generate", "--date", "2026-08-10", "--force"])

    again = (session.directory(project, date(2026, 8, 10)) / session.FILENAME).read_text(
        encoding="utf-8"
    )
    assert again == first


def test_a_session_is_weighted_against_the_days_before_it(
    project: Path, run: Callable[[list[str]], Result], lilypond: Callable[..., None]
) -> None:
    """The log is read before the draw, so a later day sees the earlier one."""
    lilypond()
    run(["generate", "--date", "2026-08-09", "--count", "4"])

    run(["generate", "--date", "2026-08-10", "--count", "4"])

    first = session_of(project, date(2026, 8, 9)).exercises
    second = session_of(project, date(2026, 8, 10)).exercises
    assert first != second


# --------------------------------------------------------------------------
# Spec §13: every stage's failure arrives with its own message
# --------------------------------------------------------------------------


def test_a_missing_configuration_names_the_file_it_looked_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run: Callable[[list[str]], Result]
) -> None:
    monkeypatch.chdir(tmp_path)

    result = run(["generate"])

    assert result.exit_code == 1
    assert "config.toml" in result.stderr
    assert "Traceback" not in result.stderr


def test_an_invalid_configuration_names_the_key(
    project: Path, run: Callable[[list[str]], Result]
) -> None:
    (project / "config.toml").write_text('[output]\nstaves = "treble"\n', encoding="utf-8")

    result = run(["generate"])

    assert result.exit_code == 1
    assert "output.staves" in result.stderr


def test_an_over_constrained_pool_names_the_axis_that_could_not_be_satisfied(
    project: Path, run: Callable[[list[str]], Result]
) -> None:
    write_config(
        project,
        session="shape = { scales = 1 }",
        scales=SCALES.replace('directions = ["up", "down", "up_down"]\n', ""),
    )

    result = run(["generate"])

    assert result.exit_code == 1
    assert "direction" in result.stderr
    assert "pool.scales" in result.stderr


def test_a_corrupt_history_entry_names_the_file(
    project: Path, run: Callable[[list[str]], Result], lilypond: Callable[..., None]
) -> None:
    lilypond()
    stale = session.directory(project, date(2026, 8, 1))
    stale.mkdir(parents=True)
    (stale / session.FILENAME).write_text("{ not json", encoding="utf-8")

    result = run(["generate", "--date", "2026-08-10"])

    assert result.exit_code == 1
    assert str(stale / session.FILENAME) in result.stderr


def test_a_missing_lilypond_binary_states_the_resolution(
    project: Path, run: Callable[[list[str]], Result], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(project / "nothing-here"))

    result = run(["generate"])

    assert result.exit_code == 1
    assert "apt-get install lilypond" in result.stderr
    assert "Traceback" not in result.stderr


def test_a_failed_render_keeps_every_source_and_writes_no_session_log(
    project: Path, run: Callable[[list[str]], Result], lilypond: Callable[..., None]
) -> None:
    """§13 keeps the `.ly` on disk, and a failed run is not a session.

    `session.json` is written last precisely so that its presence means the run
    completed: a log written before the render would count a failure as a real
    session and skew every later draw's recency weighting with nothing to say
    it had.
    """
    lilypond('printf "%s\\n" "practice.ly:9:1: error: syntax error" >&2\nexit 1')

    result = run(["generate", "--count", "3"])

    directory = session.directory(project, TODAY)
    assert result.exit_code == 1
    assert "syntax error" in result.stderr
    assert not (directory / session.FILENAME).exists()
    assert not (directory / "practice.pdf").exists()
    assert [path.name for path in sources(project, TODAY)] == [
        "book.ly",
        "exercise-01.ly",
        "exercise-02.ly",
        "exercise-03.ly",
    ]


def test_a_failed_split_render_still_keeps_the_combined_document(
    project: Path, run: Callable[[list[str]], Result], lilypond: Callable[..., None]
) -> None:
    """The book renders first: the printing unit is the one that must survive."""
    lilypond(WRITES_A_PDF + '\ncase "$*" in *exercise*) exit 4;; esac\n')

    result = run(["generate", "--count", "2", "--split"])

    assert result.exit_code == 1
    assert "exit status 4" in result.stderr
    assert (session.directory(project, TODAY) / "practice.pdf").exists()
    assert not (session.directory(project, TODAY) / session.FILENAME).exists()


def test_a_render_that_writes_no_pdf_is_a_hard_error(
    project: Path, run: Callable[[list[str]], Result], lilypond: Callable[..., None]
) -> None:
    lilypond("exit 0")

    result = run(["generate"])

    assert result.exit_code == 1
    assert "book.pdf" in result.stderr


def test_the_subcommand_is_required(run: Callable[[list[str]], Result]) -> None:
    with pytest.raises(SystemExit) as exc:
        run([])

    assert exc.value.code == 2


# --------------------------------------------------------------------------
# The console entry point (deferred at task A5 until this module existed)
# --------------------------------------------------------------------------


def test_the_console_script_points_at_this_module() -> None:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)

    assert pyproject["project"]["scripts"] == {"melete": "melete.cli:main"}
    assert callable(cli.main)


# --------------------------------------------------------------------------
# Spec §14: the end-to-end test that needs the binary
# --------------------------------------------------------------------------

LILYPOND_ON_PATH = shutil.which("lilypond")

NO_BINARY = (
    "LilyPond is not on PATH. Spec §14 requires the two binary-dependent tests to fail "
    "loudly rather than skip silently in any environment that claims to run the full "
    "suite; no such environment exists yet. The dev container has no way to carry a "
    "repo-specific system package (vergil-tooling#2718), there is no aarch64 wheel to "
    "install instead (melete#21), and CI does not claim to run integration tests at all "
    "(vergil.toml sets integration-tests = false, melete#23). Install LilyPond locally "
    "-- apt-get install lilypond, or brew install lilypond -- and this test runs."
)


@pytest.mark.integration
@pytest.mark.skipif(LILYPOND_ON_PATH is None, reason=NO_BINARY)
def test_end_to_end_produces_a_practice_pdf(
    project: Path, run: Callable[[list[str]], Result]
) -> None:
    """The first run of the whole pipeline against real LilyPond.

    It is also the first check of the seven LilyPond constructs the emitter's
    golden files could only assert the *text* of — `\\tabFullNotation`, the
    string-number and fingering syntax, the tuplet form, the key and tempo
    commands, and the markup bookpart §12's cover page is.
    """
    assert run(["generate", "--count", "5"]).exit_code == 0

    directory = session.directory(project, TODAY)
    assert (directory / "practice.pdf").exists()
    assert (directory / session.FILENAME).exists()

    ly_files = list((directory / cli.SOURCES).glob("*.ly"))
    assert len(ly_files) == len(session_of(project, TODAY).exercises) + 1

    pdf = (directory / "practice.pdf").read_bytes()
    assert pdf.startswith(b"%PDF")
    # Count leaf page objects, not the one page-tree root. LilyPond 2.24 writes
    # each leaf as `/Type/Page` (no space) and the root as `/Type /Pages`, so a
    # literal count of `/Type /Page` sees only the root and reports a single
    # page for a document that has several. Matching either spacing while the
    # `\b` after `Page` excludes `/Pages` counts the leaves the cover page plus
    # five exercises force.
    assert len(re.findall(rb"/Type\s*/Page\b", pdf)) >= 2


@pytest.mark.integration
@pytest.mark.skipif(LILYPOND_ON_PATH is None, reason=NO_BINARY)
def test_end_to_end_split_renders_every_exercise(
    project: Path, run: Callable[[list[str]], Result]
) -> None:
    assert run(["generate", "--count", "3", "--split"]).exit_code == 0

    directory = session.directory(project, TODAY)
    assert len(list(directory.glob("exercise-*.pdf"))) == 3
    assert json.loads((directory / session.FILENAME).read_text(encoding="utf-8"))["date"] == (
        TODAY.isoformat()
    )
