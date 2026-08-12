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

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from melete.alphatab import render as render_module
from melete.alphatab.render import RenderError, render

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

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
