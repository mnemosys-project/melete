"""Tests for the LilyPond adapter — the blast door (spec §4).

The behaviours that matter here are the failure paths, because they are what
spec §13 actually specifies: a failed render keeps its `.ly` on disk and
surfaces LilyPond's stderr verbatim, and a missing binary produces an explicit
resolution rather than a stack trace. Those are tested first and hardest.

**On the fake binary.** LilyPond is not installed in the dev container and is
not a Python dependency (spec §15, decision #23), so the success path cannot be
covered by running the real thing. It is covered instead by putting a small
executable named `lilypond` on `PATH` and letting the adapter find and run it
for real. Nothing in the adapter is patched out: `shutil.which` does the real
lookup, `subprocess.run` really forks, and the exit status, stderr and output
files are whatever the fake wrote. What is faked is the engraving — the one
thing this module is specified not to know anything about. A mock of
`subprocess` would instead assert that the adapter calls the API we already
decided it calls, which would keep passing after the contract broke.

The real thing is exercised by `test_renders_a_multi_page_pdf` below, which
runs whenever the binary is genuinely present.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from melete.lilypond.render import RenderError, render

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

# Deliberately not real LilyPond: this module must be indifferent to its
# contents, and a test that reads as music invites musical assertions here.
SOURCE = "{ c4 d4 e4 f4 }\n"


# --------------------------------------------------------------------------
# The fake binary
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class FakeLilyPond:
    """A stand-in `lilypond` executable installed on `PATH`."""

    path: Path
    argv_file: Path

    def argv(self) -> list[str]:
        """The arguments the adapter actually invoked the binary with."""
        return self.argv_file.read_text(encoding="utf-8").splitlines()


@pytest.fixture
def fake_lilypond(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[[str], FakeLilyPond]:
    """Install a `lilypond` on `PATH` whose body is the given shell script.

    `PATH` is replaced rather than prepended so that a real LilyPond on the
    host can never be picked up by accident — these tests must behave the same
    on a machine that has the binary and on one that does not.
    """
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    argv_file = tmp_path / "argv.txt"

    def install(body: str) -> FakeLilyPond:
        executable = bin_dir / "lilypond"
        executable.write_text(
            f'#!/bin/sh\nprintf "%s\\n" "$@" > "{argv_file}"\n{body}\n',
            encoding="utf-8",
        )
        executable.chmod(0o755)
        monkeypatch.setenv("PATH", str(bin_dir))
        return FakeLilyPond(path=executable, argv_file=argv_file)

    return install


# --------------------------------------------------------------------------
# Spec §13: LilyPond binary missing
# --------------------------------------------------------------------------


def test_a_missing_binary_states_the_resolution_rather_than_a_stack_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "nothing-here"))

    with pytest.raises(RenderError) as exc:
        render(SOURCE, tmp_path)

    message = str(exc.value)
    assert "lilypond" in message.lower()
    assert "PATH" in message
    # Every platform this project runs on gets a named resolution.
    assert "apt-get install lilypond" in message
    assert "brew install lilypond" in message


def test_a_missing_binary_is_detected_before_anything_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "nothing-here"))

    with pytest.raises(RenderError):
        render(SOURCE, tmp_path)

    assert list(tmp_path.iterdir()) == []


# --------------------------------------------------------------------------
# Spec §13: render fails
# --------------------------------------------------------------------------


def test_a_failed_render_keeps_the_ly_on_disk(
    tmp_path: Path, fake_lilypond: Callable[[str], FakeLilyPond]
) -> None:
    fake_lilypond("exit 1")
    out_dir = tmp_path / "session"

    with pytest.raises(RenderError):
        render(SOURCE, out_dir)

    kept = out_dir / "practice.ly"
    assert kept.exists()
    assert kept.read_text(encoding="utf-8") == SOURCE


def test_a_failed_render_surfaces_lilypond_stderr_verbatim(
    tmp_path: Path, fake_lilypond: Callable[[str], FakeLilyPond]
) -> None:
    complaint = "practice.ly:1:3: error: syntax error, unexpected STRING"
    fake_lilypond(f'printf "%s\\n" "{complaint}" >&2\nexit 1')

    with pytest.raises(RenderError) as exc:
        render(SOURCE, tmp_path)

    message = str(exc.value)
    assert complaint in message
    assert "error" in message.lower()


def test_a_failed_render_reports_the_exit_status_and_a_rerunnable_command(
    tmp_path: Path, fake_lilypond: Callable[[str], FakeLilyPond]
) -> None:
    fake_lilypond("exit 3")

    with pytest.raises(RenderError) as exc:
        render(SOURCE, tmp_path)

    message = str(exc.value)
    assert "exit status 3" in message
    # The kept .ly is only useful if the user is told where it is and how to
    # re-run it by hand (spec §13).
    assert str(tmp_path / "practice.ly") in message
    assert "lilypond --pdf -o" in message


def test_a_failed_render_surfaces_stdout_too(
    tmp_path: Path, fake_lilypond: Callable[[str], FakeLilyPond]
) -> None:
    fake_lilypond('printf "%s\\n" "converting to PDF"\nexit 1')

    with pytest.raises(RenderError) as exc:
        render(SOURCE, tmp_path)

    assert "converting to PDF" in str(exc.value)


def test_exiting_zero_without_a_pdf_is_a_hard_error_not_a_silent_success(
    tmp_path: Path, fake_lilypond: Callable[[str], FakeLilyPond]
) -> None:
    fake_lilypond('printf "%s\\n" "skipping output" >&2\nexit 0')

    with pytest.raises(RenderError) as exc:
        render(SOURCE, tmp_path)

    message = str(exc.value)
    assert "practice.pdf" in message
    assert "skipping output" in message
    assert (tmp_path / "practice.ly").exists()


# --------------------------------------------------------------------------
# The success path
# --------------------------------------------------------------------------


def test_a_successful_render_returns_the_path_to_the_pdf(
    tmp_path: Path, fake_lilypond: Callable[[str], FakeLilyPond]
) -> None:
    out_dir = tmp_path / "session"
    fake_lilypond(f': > "{out_dir}/practice.pdf"')

    pdf = render(SOURCE, out_dir)

    assert pdf == out_dir / "practice.pdf"
    assert pdf.exists()


def test_the_output_directory_is_created_if_it_does_not_exist(
    tmp_path: Path, fake_lilypond: Callable[[str], FakeLilyPond]
) -> None:
    out_dir = tmp_path / "sessions" / "2026-08-10"
    fake_lilypond(f': > "{out_dir}/practice.pdf"')

    render(SOURCE, out_dir)

    assert (out_dir / "practice.ly").exists()


def test_the_binary_is_invoked_with_the_ly_file_and_a_pdf_output_base(
    tmp_path: Path, fake_lilypond: Callable[[str], FakeLilyPond]
) -> None:
    fake = fake_lilypond(f': > "{tmp_path}/practice.pdf"')

    render(SOURCE, tmp_path)

    argv = fake.argv()
    assert argv[-1] == str(tmp_path / "practice.ly")
    assert "--pdf" in argv
    assert str(tmp_path / "practice") in argv


# --------------------------------------------------------------------------
# Spec §14: the one test that needs the binary
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

# Long enough that no paper size can fit it on one page. Written out here
# rather than kept as a golden file because the adapter has no opinion about
# its contents: any valid source of sufficient length proves the same thing.
MULTI_PAGE_SOURCE = """\
\\version "2.24.0"
\\score {
  \\new Staff { \\repeat unfold 200 { c'4 d'4 e'4 f'4 } }
}
"""


@pytest.mark.integration
@pytest.mark.skipif(LILYPOND_ON_PATH is None, reason=NO_BINARY)
def test_renders_a_multi_page_pdf(tmp_path: Path) -> None:
    pdf = render(MULTI_PAGE_SOURCE, tmp_path)

    assert pdf.exists()
    assert pdf.read_bytes().count(b"/Type /Page") >= 2
