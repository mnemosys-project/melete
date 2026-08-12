"""Adapter over the melete-render Node tool — half the blast door (spec §4).

This module isolates the *binary* (Node) and the *tool* it runs
(`melete-render`); `emit` isolates the *syntax* (alphaTex). A change of Node
distribution, or of how the renderer is invoked, lands here and nowhere else —
the same isolation decision #23 first bought for the original LilyPond adapter.
A change of *renderer* is both modules and their golden files (spec §4, *The
renderer boundary*, and melete#71).

This is the only module in melete's alphaTab package that knows a Node binary
and a renderer script exist. It takes alphaTex text and a directory, and returns
the path to a rendered Guitar Pro `.gp`. It holds no musical knowledge
whatsoever: it never inspects the source it is given, so a change of exporter, of
invocation, or of where Node comes from lands in this file and nowhere else.

Three behaviours are contractual, and all three exist because the alternative is
a silent failure:

* **A failed render keeps the generated `.atex` on disk** and surfaces the
  tool's own stderr verbatim. Nothing is cleaned up on failure — the file and
  the message together are what let the failure be reproduced by hand.
* **A missing Node is an explicit error naming the resolution**, never a stack
  trace. `melete-render` drives alphaTab under Node, an environment prerequisite
  rather than a Python dependency, so this message is the primary user-facing
  contract for the dependency until something fails.
* **A missing renderer script is a hard error**, never a silent fallback. The
  script is the tool; without it there is nothing to run.

Where this adapter diverged from the original LilyPond one is the stream
contract. The
`.gp` is a binary ZIP, so the renderer writes it to **stdout as bytes** and this
module captures those bytes without ever decoding them — `capture_output=True`
with no `text=`/`encoding=`, which a text-mode capture would corrupt. Only
**stderr** is text (the tool's diagnostics), and only stderr is decoded, and
only for the error message.
"""

import shlex
import shutil
import subprocess
from pathlib import Path

#: The executable this module shells out to. Resolved on `PATH`, never bundled.
NODE = "node"

#: The renderer script, which lives at the *repo root* rather than inside the
#: installed package (it is a Node tool, not Python). Resolved relative to this
#: file: alphatab → melete → src → repo root, then `melete-render/render.js`.
RENDER_JS = Path(__file__).parents[3] / "melete-render" / "render.js"

#: Base name for everything written into the output directory. §12 prints one
#: combined document per day, so the day's directory holds one of each.
STEM = "practice"

ATEX_NAME = f"{STEM}.atex"
GP_NAME = f"{STEM}.gp"

MISSING_NODE = f"""\
Node.js is not installed, or the {NODE!r} binary is not on PATH.

melete renders Guitar Pro files through melete-render, a small Node tool that
drives alphaTab. Node is an environment prerequisite rather than a Python
dependency: alphaTab is a JavaScript library, so the renderer runs under Node.

To resolve, install it for this platform:

    Debian / Ubuntu   apt-get install nodejs
    macOS             brew install node
                      (or the upstream build from nodejs.org)

Then confirm with: {NODE} --version
"""


class RenderError(RuntimeError):
    """A render did not produce a Guitar Pro `.gp`.

    Carries the tool's own stderr verbatim where there was any, and the location
    of the alphaTex that was kept for inspection.
    """


def render(alphatex: str, out_dir: Path, *, stem: str = STEM) -> Path:
    """Render `alphatex` into `out_dir` and return the path to the `.gp`.

    Raises `RenderError` if Node is missing, if the renderer script is missing,
    if the tool fails, or if it reports success without writing any bytes. The
    `.atex` is kept in every one of those cases except the first two, where
    nothing was written at all.

    `stem` names the pair of files one render produces — `<stem>.atex` and
    `<stem>.gp`. It is a parameter rather than the constant it started as
    because §12 keeps the source *per exercise and for the book* in one `src/`
    directory: a fixed name would have `--split` overwrite each source with the
    next, and the kept-on-failure `.atex` would name whichever render happened
    to fail last rather than the one being inspected.
    """
    node = _resolve_node()
    render_js = _resolve_render_js()

    out_dir.mkdir(parents=True, exist_ok=True)
    atex_path = out_dir / f"{stem}.atex"
    atex_path.write_text(alphatex, encoding="utf-8")

    command = [node, str(render_js)]
    # S603: `node` is an absolute path resolved by shutil.which and `render_js`
    # is a path this module derives from its own location. No shell is involved
    # and no string is interpolated into a command line, so there is nothing for
    # a shell to reinterpret. stdout is captured as *bytes* — no `text=` — because
    # the `.gp` is a binary ZIP that a text-mode decode would corrupt.
    completed = subprocess.run(  # noqa: S603
        command,
        input=alphatex.encode("utf-8"),
        capture_output=True,
        check=False,
    )

    if completed.returncode != 0:
        raise RenderError(_failed(command, atex_path, completed))

    gp_path = out_dir / f"{stem}.gp"
    if not completed.stdout:
        raise RenderError(_no_output(gp_path, atex_path, completed))
    gp_path.write_bytes(completed.stdout)
    return gp_path


def _resolve_node() -> str:
    """The absolute path to Node, or an error naming how to install it."""
    found = shutil.which(NODE)
    if found is None:
        raise RenderError(MISSING_NODE)
    return found


def _resolve_render_js() -> Path:
    """The renderer script, or an error naming the path that is missing."""
    if not RENDER_JS.exists():
        raise RenderError(_missing_render_js())
    return RENDER_JS


def _missing_render_js() -> str:
    return (
        f"The melete-render script is missing at {RENDER_JS}.\n\n"
        f"It is the Node tool this adapter runs, and it lives at the repository\n"
        f"root (melete-render/render.js), not inside the installed package. If\n"
        f"melete was installed as a wheel without the repo checkout beside it,\n"
        f"the renderer is unavailable and there is nothing to run."
    )


def _failed(
    command: list[str],
    atex_path: Path,
    completed: subprocess.CompletedProcess[bytes],
) -> str:
    return (
        f"melete-render failed with exit status {completed.returncode}.\n\n"
        f"The alphaTex was kept at {atex_path} — nothing is cleaned up on a\n"
        f"failed render. To reproduce it by hand:\n\n"
        f"    {shlex.join(command)} < {atex_path}\n"
        f"{_stderr(completed)}"
    )


def _no_output(
    gp_path: Path,
    atex_path: Path,
    completed: subprocess.CompletedProcess[bytes],
) -> str:
    return (
        f"melete-render exited 0 but wrote no bytes to stdout, so there is no\n"
        f"{gp_path.name} to write into {gp_path.parent}.\n\n"
        f"The alphaTex was kept at {atex_path}. A tool that reports success while\n"
        f"producing nothing is exactly the silent failure this guards against.\n"
        f"{_stderr(completed)}"
    )


def _stderr(completed: subprocess.CompletedProcess[bytes]) -> str:
    """The tool's stderr, verbatim. Only stderr is decoded: stdout is the binary
    `.gp` (or empty on failure), and decoding it would render garbage."""
    return f"\n--- melete-render stderr ---\n{completed.stderr.decode('utf-8', errors='replace')}"
