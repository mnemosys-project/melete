"""Adapter over the LilyPond binary — the blast door (spec §4).

This is the only module in melete that knows a LilyPond binary exists. It takes
LilyPond source text and a directory, and returns the path to a rendered PDF.
It holds no musical knowledge whatsoever: it never inspects the source it is
given, so a change of engraver, of invocation, or of where the binary comes
from lands in this file and nowhere else.

Two behaviours are contractual (spec §13), and both exist because the
alternative is a silent failure:

* **A failed render keeps the generated `.ly` on disk** and surfaces LilyPond's
  own output verbatim. Nothing is cleaned up on failure — the file and the
  message together are what let the failure be reproduced by hand.
* **A missing binary is an explicit error naming the resolution**, never a
  stack trace. LilyPond is an environment prerequisite rather than a Python
  dependency (spec §15, decision #23): the PyPI redistribution publishes x86_64
  wheels only, so it cannot be installed on the arm64 container or on Apple
  Silicon at all. That makes this message the primary user-facing contract for
  the dependency, since the prerequisite is invisible until something fails.
"""

import shlex
import shutil
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

#: The executable this module shells out to. Resolved on `PATH`, never bundled.
BINARY = "lilypond"

#: Base name for everything written into the output directory. §12 prints one
#: combined document per day, so the day's directory holds one of each.
STEM = "practice"

LY_NAME = f"{STEM}.ly"
PDF_NAME = f"{STEM}.pdf"

MISSING_BINARY = f"""\
LilyPond is not installed, or the {BINARY!r} binary is not on PATH.

melete engraves through LilyPond. It is an environment prerequisite rather
than a Python dependency, because the PyPI redistribution of LilyPond ships
x86_64 wheels only and has no aarch64 build at any version.

To resolve, install it for this platform:

    Debian / Ubuntu   apt-get install lilypond
    macOS             brew install lilypond
                      (or the upstream darwin-arm64 tarball from lilypond.org)
    x86_64 only       uv sync --extra bundled-lilypond

Then confirm with: {BINARY} --version
"""


class RenderError(RuntimeError):
    """A render did not produce a PDF.

    Carries LilyPond's own output verbatim where there was any, and the
    location of the source that was kept for inspection.
    """


def render(ly_text: str, out_dir: Path, *, stem: str = STEM) -> Path:
    """Engrave `ly_text` into `out_dir` and return the path to the PDF.

    Raises `RenderError` if the binary is missing, if LilyPond fails, or if it
    reports success without leaving a PDF behind. The `.ly` is kept in every
    one of those cases except the first, where nothing was written at all.

    `stem` names the pair of files one render produces — `<stem>.ly` and
    `<stem>.pdf`. It is a parameter rather than the constant it started as
    because §12 keeps the source *per exercise and for the book* in one `src/`
    directory: a fixed name would have `--split` overwrite each source with the
    next, and the kept-on-failure `.ly` (§13) would name whichever render
    happened to fail last rather than the one being inspected.
    """
    binary = _resolve_binary()

    out_dir.mkdir(parents=True, exist_ok=True)
    ly_path = out_dir / f"{stem}.ly"
    ly_path.write_text(ly_text, encoding="utf-8")

    command = [binary, "--pdf", "-o", str(out_dir / stem), str(ly_path)]
    # S603/S607: `binary` is an absolute path resolved by shutil.which, and the
    # remaining arguments are paths this module derives from the caller's
    # directory. No shell is involved and no string is interpolated into a
    # command line, so there is nothing for a shell to reinterpret.
    completed = subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        text=True,
        check=False,
    )

    if completed.returncode != 0:
        raise RenderError(_failed(command, ly_path, completed))

    pdf_path = out_dir / f"{stem}.pdf"
    if not pdf_path.exists():
        raise RenderError(_no_output(pdf_path, ly_path, completed))
    return pdf_path


def _resolve_binary() -> str:
    """The absolute path to LilyPond, or an error naming how to install it."""
    found = shutil.which(BINARY)
    if found is None:
        raise RenderError(MISSING_BINARY)
    return found


def _failed(command: list[str], ly_path: Path, completed: subprocess.CompletedProcess[str]) -> str:
    return (
        f"LilyPond failed with exit status {completed.returncode}.\n\n"
        f"The source was kept at {ly_path} — nothing is cleaned up on a failed\n"
        f"render. To reproduce it by hand:\n\n"
        f"    {shlex.join(command)}\n"
        f"{_output(completed)}"
    )


def _no_output(pdf_path: Path, ly_path: Path, completed: subprocess.CompletedProcess[str]) -> str:
    return (
        f"LilyPond exited 0 but wrote no {pdf_path.name} into {pdf_path.parent}.\n\n"
        f"The source was kept at {ly_path}. A source that redirects its own\n"
        f"output — \\bookOutputName, for instance — will do this; so will a\n"
        f"LilyPond built without PDF support.\n"
        f"{_output(completed)}"
    )


def _output(completed: subprocess.CompletedProcess[str]) -> str:
    """LilyPond's own streams, verbatim. Both, always: a diagnostic that is
    reported on the stream we chose not to read is a diagnostic lost."""
    return (
        f"\n--- lilypond stderr ---\n{completed.stderr}"
        f"\n--- lilypond stdout ---\n{completed.stdout}"
    )
