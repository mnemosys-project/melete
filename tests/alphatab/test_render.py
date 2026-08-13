"""Tests for the melete-render adapter — half the blast door (spec §4).

The adapter isolates the *binary* (Node) and the *tool* (`melete-render`);
`emit` isolates the *syntax* (alphaTex). Both are renderer-specific and both
would be rewritten by a change of renderer.

The behaviours that matter here are the failure paths, because they are the
contract: a failed render keeps its `.atex` on disk and surfaces the tool's
stderr verbatim, a missing Node produces an explicit resolution rather than a
stack trace, and a missing renderer script is a hard error rather than a silent
fallback. Those are tested first and hardest.

**On the fake binary.** Node drives `melete-render`, which drives alphaTab; none
of that is a Python dependency, so the success path is not covered by running
the real toolchain. It is covered instead by putting a small executable named
`node` on `PATH` and letting the adapter find and run it for real. Nothing in
the adapter is patched out: `shutil.which` does the real lookup,
`subprocess.run` really forks, and the exit status, stderr and stdout bytes are
whatever the fake wrote. What is faked is the rendering — the one thing this
module is specified not to know anything about. A mock of `subprocess` would
instead assert that the adapter calls the API we already decided it calls, which
would keep passing after the contract broke.

The fake also proves the binary contract that distinguishes this adapter from
the LilyPond one: the `.gp` is a binary ZIP, so stdout is captured as bytes and
written back byte-for-byte, while only stderr is decoded for the error message.
`test_a_successful_render_writes_the_gp_bytes_verbatim` writes bytes that are
not valid UTF-8, which a text-mode capture would corrupt.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from melete.alphatab import render as render_module
from melete.alphatab.emit import emit_score
from melete.alphatab.render import RenderError, render
from melete.instrument import resolve_profile
from melete.score import Note, Score, Voice

if TYPE_CHECKING:
    from collections.abc import Callable

# Deliberately not real alphaTex: this module must be indifferent to its
# contents, and a test that reads as music invites musical assertions here.
SOURCE = r"\title 'x' . 3.3.4"


# --------------------------------------------------------------------------
# The fake binary
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class FakeNode:
    """A stand-in `node` executable installed on `PATH`."""

    path: Path
    argv_file: Path
    stdin_file: Path

    def argv(self) -> list[str]:
        """The arguments the adapter actually invoked `node` with."""
        return self.argv_file.read_text(encoding="utf-8").splitlines()

    def stdin(self) -> str:
        """The bytes the adapter piped to `node`, decoded as UTF-8 text."""
        return self.stdin_file.read_text(encoding="utf-8")


@pytest.fixture
def fake_node(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[[str], FakeNode]:
    """Install a `node` on `PATH` whose body is the given shell script.

    The fake directory is *prepended* to `PATH`, so `shutil.which("node")`
    resolves this fake first and shadows any real Node the container happens to
    bake in — determinism holds because the fake always wins the lookup. Prepend
    rather than replace (the choice the LilyPond fixture makes) because the fake
    script itself relies on coreutils being reachable: it captures its stdin with
    `cat`, which a bare fake-only `PATH` would hide. The fake records its argv and
    captures its stdin before running the body, so the body is free to write to
    stdout/stderr and exit with any status.
    """
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    argv_file = tmp_path / "argv.txt"
    stdin_file = tmp_path / "stdin.txt"

    def install(body: str) -> FakeNode:
        executable = bin_dir / "node"
        executable.write_text(
            f'#!/bin/sh\nprintf "%s\\n" "$@" > "{argv_file}"\ncat > "{stdin_file}"\n{body}\n',
            encoding="utf-8",
        )
        executable.chmod(0o755)
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
        return FakeNode(path=executable, argv_file=argv_file, stdin_file=stdin_file)

    return install


# --------------------------------------------------------------------------
# Node missing
# --------------------------------------------------------------------------


def test_a_missing_node_states_the_resolution_rather_than_a_stack_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "nothing-here"))

    with pytest.raises(RenderError) as exc:
        render(SOURCE, tmp_path)

    message = str(exc.value)
    assert "node" in message.lower()
    assert "PATH" in message
    # Every platform this project runs on gets a named resolution.
    assert "apt-get install nodejs" in message
    assert "brew install node" in message


def test_a_missing_node_is_detected_before_anything_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "nothing-here"))

    with pytest.raises(RenderError):
        render(SOURCE, tmp_path)

    assert list(tmp_path.iterdir()) == []


# --------------------------------------------------------------------------
# Renderer script missing
# --------------------------------------------------------------------------


def test_a_missing_render_script_is_a_hard_error_not_a_silent_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_node: Callable[[str], FakeNode],
) -> None:
    fake_node(":")  # Node resolves; the script does not.
    monkeypatch.setattr(render_module, "RENDER_JS", tmp_path / "no" / "render.js")

    with pytest.raises(RenderError) as exc:
        render(SOURCE, tmp_path / "out")

    message = str(exc.value)
    assert "render.js" in message
    # Detected before anything is written — the .atex is not created.
    assert not (tmp_path / "out").exists()


# --------------------------------------------------------------------------
# Render fails
# --------------------------------------------------------------------------


def test_a_failed_render_keeps_the_atex_on_disk(
    tmp_path: Path, fake_node: Callable[[str], FakeNode]
) -> None:
    fake_node("exit 1")
    out_dir = tmp_path / "session"

    with pytest.raises(RenderError):
        render(SOURCE, out_dir)

    kept = out_dir / "practice.atex"
    assert kept.exists()
    assert kept.read_text(encoding="utf-8") == SOURCE


def test_a_failed_render_surfaces_the_tool_stderr_verbatim(
    tmp_path: Path, fake_node: Callable[[str], FakeNode]
) -> None:
    complaint = "parser AlphaTexError: unexpected token (line 1, col 3)"
    fake_node(f'printf "%s\\n" "{complaint}" >&2\nexit 1')

    with pytest.raises(RenderError) as exc:
        render(SOURCE, tmp_path)

    message = str(exc.value)
    assert complaint in message
    assert "error" in message.lower()


def test_a_failed_render_reports_the_exit_status_and_the_kept_atex_path(
    tmp_path: Path, fake_node: Callable[[str], FakeNode]
) -> None:
    fake_node("exit 3")

    with pytest.raises(RenderError) as exc:
        render(SOURCE, tmp_path)

    message = str(exc.value)
    assert "exit status 3" in message
    # The kept .atex is only useful if the user is told where it is and how to
    # re-run it by hand.
    assert str(tmp_path / "practice.atex") in message


def test_exiting_zero_without_output_is_a_hard_error_not_a_silent_success(
    tmp_path: Path, fake_node: Callable[[str], FakeNode]
) -> None:
    fake_node('printf "%s\\n" "wrote nothing" >&2\nexit 0')

    with pytest.raises(RenderError) as exc:
        render(SOURCE, tmp_path)

    message = str(exc.value)
    assert "practice.gp" in message
    assert "wrote nothing" in message
    assert (tmp_path / "practice.atex").exists()
    # No empty .gp is left behind masquerading as a rendered file.
    assert not (tmp_path / "practice.gp").exists()


# --------------------------------------------------------------------------
# The success path
# --------------------------------------------------------------------------

# Bytes that are not valid UTF-8: a text-mode capture would corrupt them. The
# real `.gp` is a ZIP whose local-file-header magic is exactly `PK\x03\x04`.
GP_BYTES = b"PK\x03\x04\xff\xfe"


def test_a_successful_render_writes_the_gp_bytes_verbatim(
    tmp_path: Path, fake_node: Callable[[str], FakeNode]
) -> None:
    out_dir = tmp_path / "session"
    fake_node(r"printf 'PK\003\004\377\376'")

    gp = render(SOURCE, out_dir)

    assert gp == out_dir / "practice.gp"
    assert gp.read_bytes() == GP_BYTES


def test_the_output_directory_is_created_if_it_does_not_exist(
    tmp_path: Path, fake_node: Callable[[str], FakeNode]
) -> None:
    out_dir = tmp_path / "sessions" / "2026-08-12"
    fake_node(r"printf 'PK\003\004'")

    render(SOURCE, out_dir)

    assert (out_dir / "practice.atex").exists()
    assert (out_dir / "practice.gp").exists()


def test_the_alphatex_is_piped_to_the_renderer_on_stdin(
    tmp_path: Path, fake_node: Callable[[str], FakeNode]
) -> None:
    fake = fake_node(r"printf 'PK\003\004'")

    render(SOURCE, tmp_path)

    # The tool reads alphaTex from stdin, and the renderer script is its sole
    # argument.
    assert fake.stdin() == SOURCE
    assert fake.argv()[-1].endswith("render.js")


def test_a_custom_stem_names_both_files(
    tmp_path: Path, fake_node: Callable[[str], FakeNode]
) -> None:
    fake_node(r"printf 'PK\003\004'")

    gp = render(SOURCE, tmp_path, stem="etude-1")

    assert gp == tmp_path / "etude-1.gp"
    assert (tmp_path / "etude-1.atex").exists()


# --------------------------------------------------------------------------
# The black-box integration test (epic #46, Task 9)
# --------------------------------------------------------------------------
#
# Everything above fakes the binary: the point there is the *adapter* contract,
# and a fake `node` proves it without a toolchain. This one test fakes nothing.
# It drives a real `Score` through the real emitter and the real `melete-render`
# renderer to a real Guitar Pro `.gp`, then re-imports that `.gp` through
# alphaTab a second time and asserts its structure. It is the end-to-end proof
# that the whole pipeline — Score to alphaTex to a valid, round-trippable `.gp` —
# actually works against the real alphaTab, not merely that each stage passes its
# own unit tests.
#
# It is deliberately structural, not content-correctness. Whether the *right*
# notes landed is the Task 6 alphaTex goldens' job (`test_alphatex_emit.py`); a
# `.gp` is a binary export whose internals shift with the alphaTab version, so
# pinning them here would be a brittle second golden with none of the first's
# clarity. Track count and bar count are the version-stable structural facts that
# a round trip either preserves or does not — and they are exactly what the Task 1
# spike checked when it re-imported its probe `.gp`. String indices are *not*
# asserted: alphaTab renumbers `Note.string` on GP re-import, so a raw-index
# assertion would fail on a `.gp` that is perfectly correct.

#: `node` on PATH, resolved once. `None` skips the test — the same gate the
#: LilyPond render integration test puts on its binary. The renderer needs the
#: Node toolchain the dev container carries; a bare host has no way to run it.
NODE_ON_PATH = shutil.which(render_module.NODE)

NO_NODE = (
    "Node is not on PATH. This black-box integration test drives real alphaTex "
    "through the real melete-render renderer and re-imports the resulting .gp, so it "
    "needs the Node toolchain the dev container carries (vergil.toml [container] bakes "
    "alphaTab onto NODE_PATH). It is marked @pytest.mark.integration, runs for real "
    "under vrg-container-run where Node is present, and skips on a bare host — the same "
    "discipline the LilyPond render integration test uses. CI runs it inside the "
    "ordinary pytest job; integration-tests stays false in vergil.toml (melete#23), "
    "which governs the dedicated integration *job*, not whether this test executes."
)

#: A second, independent trip through alphaTab: read the `.gp` bytes back with
#: `ScoreLoader.loadScoreFromBytes` — the loader that sniffs the format — and
#: print the two structural counts as JSON on stdout. This is the re-import the
#: spike did by hand, reduced to the two numbers this test asserts. It runs under
#: the container's Node, whose NODE_PATH resolves `@coderline/alphatab` exactly as
#: `melete-render` itself relies on (CommonJS `require`).
_REIMPORT_JS = (
    "const fs = require('fs');\n"
    "const alphaTab = require('@coderline/alphatab');\n"
    "const buf = fs.readFileSync(process.argv[2]);\n"
    "const bytes = new Uint8Array(buf.buffer, buf.byteOffset, buf.byteLength);\n"
    "const score = alphaTab.importer.ScoreLoader.loadScoreFromBytes(bytes);\n"
    "process.stdout.write(JSON.stringify({\n"
    "  tracks: score.tracks.length,\n"
    "  bars: score.masterBars.length,\n"
    "  masterBars: score.masterBars.map("
    "(b) => ({isRepeatStart: b.isRepeatStart, repeatCount: b.repeatCount})),\n"
    "}));\n"
)


def _known_score() -> Score:
    """A Score whose structure is known by construction: one track, three bars.

    Twelve quarter notes in 4/4 fill exactly three bars, and one exercise is one
    alphaTab track. Both counts are chosen to be unambiguous — three is not the
    default a mis-parse would leave — and both survive the GP round trip that the
    per-note fields do not. The notes sit on the lowest string at real frets so
    the emitter and renderer see a genuine exercise, but nothing here asserts
    against them: that is the goldens' job.
    """
    profile = resolve_profile("bass6")
    quarter = Fraction(1, 4)
    voice: Voice = [
        Note(
            pitch=profile.tuning[0] + fret,
            string=0,
            fret=fret,
            duration=quarter,
            finger=None,
            accent=False,
        )
        for fret in [0, 2, 3, 5] * 3
    ]
    return Score(
        title="integration",
        instruction="",
        instrument=profile,
        time_signature=(4, 4),
        tempo_range=(80, 80),
        voice=voice,
        key=None,
    )


def _reimport_structure(gp: Path, tmp_path: Path) -> dict[str, Any]:
    """Re-import `gp` through alphaTab and return its structural facts.

    The track and bar counts, plus each master bar's repeat flags
    (`isRepeatStart`, `repeatCount`) — the version-stable facts a round trip
    preserves. A failed re-import is surfaced loudly — its stderr becomes the
    assertion message — rather than swallowed: a silent failure here would let a
    corrupt `.gp` pass as a valid one, the exact thing this test exists to catch.
    """
    node = NODE_ON_PATH
    assert node is not None  # guaranteed by the skipif; narrows the type
    script = tmp_path / "reimport.js"
    script.write_text(_REIMPORT_JS, encoding="utf-8")

    completed = subprocess.run(  # noqa: S603
        [node, str(script), str(gp)],
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    return json.loads(completed.stdout)


@pytest.mark.integration
@pytest.mark.skipif(NODE_ON_PATH is None, reason=NO_NODE)
def test_a_known_score_renders_to_a_valid_gp_and_round_trips(tmp_path: Path) -> None:
    alphatex = emit_score(_known_score())

    gp = render(alphatex, tmp_path)

    assert gp.exists()
    # The proof of validity is that alphaTab reads the bytes back at all: a
    # corrupt or empty `.gp` raises in the loader rather than returning a score.
    structure = _reimport_structure(gp, tmp_path)
    assert structure["tracks"] == 1
    assert structure["bars"] == 3


# --------------------------------------------------------------------------
# The exercise-level repeat, end to end (spec §5; melete#112)
# --------------------------------------------------------------------------
#
# The emit goldens (`test_alphatex_emit.py`) pin the repeat *tokens* in the text;
# this proves the whole pipeline honours them — the frozen `repeat.atex` renders
# to a valid `.gp` whose master bars carry the repeat alphaTab reconstructs. The
# spike found that a *trailing* `\rc` opens a spurious empty master bar, so the
# bar count here is load-bearing: two content bars must stay two, and the repeat
# must land on the second, not on a phantom third.

REPEAT_GOLDEN = Path(__file__).parent / "golden" / "repeat.atex"


def _repeating_score() -> Score:
    """A two-bar exercise wrapped in a repeat: one track, two bars, two passes.

    Eight quarter notes in 4/4 fill exactly two bars, and `repeat=True` brackets
    them. The counts are chosen unambiguous — two content bars stay two only if
    the close leads the last bar rather than trailing it into a phantom third
    (spike finding, melete#112). This is the Score the frozen `repeat.atex`
    golden is emitted from, so the freeze and the render share one source.
    """
    profile = resolve_profile("bass6")
    quarter = Fraction(1, 4)
    voice: Voice = [
        Note(
            pitch=profile.tuning[0] + fret,
            string=0,
            fret=fret,
            duration=quarter,
            finger=None,
            accent=False,
        )
        for fret in [0, 2, 3, 5] * 2
    ]
    return Score(
        title="repeat",
        instruction="",
        instrument=profile,
        time_signature=(4, 4),
        tempo_range=(80, 80),
        voice=voice,
        key=None,
        repeat=True,
    )


def test_the_repeat_golden_is_frozen() -> None:
    """The emitter's text for the repeating score is pinned byte for byte.

    Not an integration test — it renders nothing — so it runs everywhere and
    guards the exact `.atex` the render test below feeds the real renderer.
    """
    assert emit_score(_repeating_score()) == REPEAT_GOLDEN.read_text(encoding="utf-8")


@pytest.mark.integration
@pytest.mark.skipif(NODE_ON_PATH is None, reason=NO_NODE)
def test_the_repeat_golden_renders_to_a_valid_gp_with_the_repeat(tmp_path: Path) -> None:
    alphatex = REPEAT_GOLDEN.read_text(encoding="utf-8")

    gp = render(alphatex, tmp_path)

    assert gp.exists()
    structure = _reimport_structure(gp, tmp_path)
    assert structure["tracks"] == 1
    # Two content bars stay two — a trailing `\rc` would have made a phantom third.
    assert structure["bars"] == 2
    master_bars = structure["masterBars"]
    assert master_bars[0]["isRepeatStart"] is True
    assert master_bars[-1]["repeatCount"] == 2
