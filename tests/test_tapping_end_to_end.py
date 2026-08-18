"""End-to-end proof that a tapped-triad config renders to a tapped `.gp` (epic #67, Task D2).

This is the spec's success criterion (spec §1, §10, "End to end" row), checked as
a **black box**: an `arpeggios` pool listing a triad `quality` is driven through
the *whole* pipeline — selection derives `hands == 2`, the family walks the
two-hand tapped journey, the emitter stamps the tap effects, and the vendored
`melete-render` renders real alphaTex to a real Guitar Pro `.gp` — and then the
produced `.gp` is unzipped and its `Content/score.gpif` is asserted to carry the
`Tapped` property. That is exactly how the R&D survey detected tapping: `.gp` is
a ZIP, and a tapped note round-trips to a `<Property name="Tapped">` in the score
model file.

Nothing below reaches into the pipeline's stages; it runs `melete generate` the
way a user would and inspects only the artifact on disk. It fakes nothing — the
unit tests below it (`tests/alphatab/test_emit_tapping.py` for the tokens,
`tests/families/test_arpeggios_tapping.py` for the journey) prove each stage, and
this test proves the stages compose all the way to a tapped `.gp` against the
real alphaTab. It therefore needs the Node toolchain the dev container carries
and skips on a bare host, the same discipline `tests/alphatab/test_render.py` and
`tests/test_cli_generate.py` use for their real-render integration tests.

## Why every draw taps

`qualities = ["min"]` lists a single **triad**. A triad is inherently a tapped
candidate (spec §7, decision 8): the family derives `hands == 2` and routes it
through the two-hand tapped journey where every note is `TAPPED`. So the whole
session is tapped — there is no draw that could leave a note plucked and let the
`Tapped` assertion pass on the wrong evidence. `roots = "all"` gives the tiled
box twelve pitch classes to find an on-neck placement among, so the validity gate
resamples any root whose box runs off the neck rather than over-constraining the
draw.
"""

from __future__ import annotations

import tempfile
import zipfile
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from melete import cli, session
from melete.alphatab import render as render_module

if TYPE_CHECKING:
    from collections.abc import Callable

TODAY = date.today()

#: A `bass6` session drawn entirely from `min` triads, so every exercise is a
#: two-hand tapped journey. `shape` pins the whole session to `arpeggios` — no
#: other family can be drawn — and `qualities = ["min"]` makes every arpeggios
#: draw a triad. The remaining axes are the ordinary arpeggios pool, trimmed to
#: the root inversion the tap box supports (a triad's inversion is derived to
#: `root` regardless, spec §7).
TAPPED_CONFIG = """\
[instrument]
profile = "bass6"

[session]
shape = { arpeggios = 4 }

[pool.arpeggios]
roots = "all"
qualities = ["min"]
inversions = ["root"]
patterns = ["straight"]

[pool.rhythm]
accent_patterns = ["none"]
note_value_patterns = ["straight"]
"""

#: The score-model file inside a Guitar Pro `.gp` (a ZIP). alphaTab writes the
#: full musical model here, and the note effects survive the export as XML
#: `<Property>` elements — this is the file the R&D survey unzipped.
GPIF_ENTRY = "Content/score.gpif"

#: A trivial, renderer-indifferent alphaTex whose only job is to answer "is the
#: whole toolchain here?" — Node, the `melete-render` script, and
#: `@coderline/alphatab` on `NODE_PATH` must all be present, and only a real
#: render exercises all three (mirrors `tests/test_cli_generate.py`).
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
    "The alphaTab toolchain is not reachable. This is the epic #67 end-to-end success "
    "criterion (spec §1, §10): it drives a tapped-triad config through the whole pipeline "
    "to a real Guitar Pro .gp and asserts the .gp carries the Tapped property. melete "
    "renders through melete-render, a Node tool driving alphaTab: Node must be on PATH, the "
    "render.js script must sit at the repo root, and @coderline/alphatab must be importable "
    "(the container bakes it globally on NODE_PATH, melete#85). Inside `vrg-container-run` "
    "all three hold and this test runs; a bare host without alphaTab installed skips it."
)


@pytest.fixture
def tapped_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project root holding the all-tapped `config.toml`, with the process in it.

    The CLI resolves both the configuration and `sessions/` against the working
    directory, so the directory the command runs from *is* the project.
    """
    root = tmp_path / "project"
    root.mkdir()
    (root / "config.toml").write_text(TAPPED_CONFIG, encoding="utf-8")
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Callable[[list[str]], int]:
    """Invoke `main` in-process, surfacing the CLI's own stderr on failure."""

    def invoke(argv: list[str]) -> int:
        code = cli.main(argv)
        if code != 0:
            captured = capsys.readouterr()
            pytest.fail(f"`melete {' '.join(argv)}` exited {code}\n{captured.err}")
        return code

    return invoke


@pytest.mark.integration
@pytest.mark.skipif(not ALPHATAB_ON_PATH, reason=NO_TOOLCHAIN)
def test_a_tapped_triad_session_renders_a_gp_carrying_the_tapped_property(
    tapped_project: Path, run: Callable[[list[str]], int]
) -> None:
    """The success criterion: a tapped-triad sheet reaches the `.gp` as `Tapped`.

    A right-hand tapped note (`tt`) round-trips to a `<Property name="Tapped">` in
    `Content/score.gpif`; a left-hand tapped note (`lht`) to `LeftHandTapped`. The
    universal tap box uses both hands (root+third left, fifth+octave-root right —
    spec §5), so a correctly wired chain produces both, and the right-hand
    fingering (`rf`) reaches the `.gp` as a `RightFingering`. `Tapped` is the
    spec's success criterion; the other two are asserted as corroboration that the
    whole tap payload — not merely one token — survives the export.
    """
    run(["generate"])

    practice_gp = session.directory(tapped_project, TODAY) / "practice.gp"
    assert practice_gp.exists()

    # A `.gp` is a ZIP; its local-file-header magic is exactly `PK\x03\x04`.
    assert practice_gp.read_bytes().startswith(b"PK\x03\x04")

    with zipfile.ZipFile(practice_gp) as archive:
        gpif = archive.read(GPIF_ENTRY).decode("utf-8")

    # The spec's success criterion, checked the way the R&D survey detected
    # tapping: the tapped note is a `<Property name="Tapped">` in the score model.
    assert 'name="Tapped"' in gpif
    # Corroboration that the full two-hand tap payload survived the export, not
    # only the right-hand tap: the box's left-hand tones and the right-hand
    # fingering reach the `.gp` too.
    assert 'name="LeftHandTapped"' in gpif
    assert "RightFingering" in gpif


#: A `bass6` session drawn entirely from `min7` sevenths, opted into tapping by
#: `tapped_qualities` (G3, `melete#212`). Unlike a triad — inherently tapped — a
#: seventh taps only because the pool names it here, so this config is the proof
#: that the last Track-2 piece (selection → derive `hands == 2` → the seventh tap
#: box → emit) wires end to end. Every draw is a `min7` in the tapped set, so the
#: whole session taps and no plucked draw could pass the `Tapped` assertion on the
#: wrong evidence. `roots = "all"` lets the validity gate resample any root whose
#: seventh grid runs off the neck.
TAPPED_SEVENTH_CONFIG = """\
[instrument]
profile = "bass6"

[session]
shape = { arpeggios = 4 }

[pool.arpeggios]
roots = "all"
qualities = ["min7"]
tapped_qualities = ["min7"]
inversions = ["root"]
patterns = ["straight"]

[pool.rhythm]
accent_patterns = ["none"]
note_value_patterns = ["straight"]
"""


@pytest.fixture
def tapped_seventh_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project root holding the tapped-seventh `config.toml`, with the process in it."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "config.toml").write_text(TAPPED_SEVENTH_CONFIG, encoding="utf-8")
    monkeypatch.chdir(root)
    return root


@pytest.mark.integration
@pytest.mark.skipif(not ALPHATAB_ON_PATH, reason=NO_TOOLCHAIN)
def test_a_tapped_seventh_config_renders_a_gp_carrying_the_tapped_property(
    tapped_seventh_project: Path, run: Callable[[list[str]], int]
) -> None:
    """G3's success criterion: a `tapped_qualities`-configured seventh reaches the
    `.gp` as `Tapped`.

    The same black-box check as the triad case, now for a *configured* seventh: the
    seventh two-string tap grid (R11) taps root+fifth with the left hand and
    third+seventh with the right, so a correctly wired chain produces both a
    `Tapped` and a `LeftHandTapped` property. `Tapped` is the criterion; the
    left-hand tap corroborates the full two-hand payload survived the export.
    """
    run(["generate"])

    practice_gp = session.directory(tapped_seventh_project, TODAY) / "practice.gp"
    assert practice_gp.exists()
    assert practice_gp.read_bytes().startswith(b"PK\x03\x04")

    with zipfile.ZipFile(practice_gp) as archive:
        gpif = archive.read(GPIF_ENTRY).decode("utf-8")

    assert 'name="Tapped"' in gpif
    assert 'name="LeftHandTapped"' in gpif


#: A two-hand tapped 3nps scale (corpus R9/R10, epic #67, #214): A Ionian, three
#: notes per string, on the six-string bass. Reached by `hands == 2` in params —
#: the selection wiring is the follow-up H2, so this renders the realized Score
#: directly rather than through `melete generate`.
TAPPED_SCALE: dict[str, object] = {
    "root": 33,
    "scale_type": "ionian",
    "traversal": "three_note_per_string",
    "pattern": "straight",
    "hands": 2,
}


@pytest.mark.integration
@pytest.mark.skipif(not ALPHATAB_ON_PATH, reason=NO_TOOLCHAIN)
def test_a_tapped_3nps_scale_renders_a_gp_carrying_tapped_and_hopo(tmp_path: Path) -> None:
    """#214's success criterion: a tapped 3nps scale reaches the `.gp` as tap + pull-off.

    The same black-box check as the arpeggio cases, now for the first tapped
    *scale*: a two-hand tapped 3nps scale (R9/R10) taps the top of each string
    with the right hand (`Tapped`) and the two lower notes with the left
    (`LeftHandTapped`), and its ascending hammer-ons and descending pull-offs are
    hammer/pull legato — which round-trip to a `Hopo` property (alphaTab writes
    `HopoOrigin` on the origin note and `HopoDestination` on the slurred note) in
    the score model. The Score is realized through the pipeline and rendered by
    the real alphaTab, then the `.gp` is unzipped and asserted to carry all three.
    """
    from melete import pipeline
    from melete.alphatab.emit import emit_score
    from melete.instrument import PROFILES

    score, _plan = pipeline.realize(PROFILES["bass6"], "scales", TAPPED_SCALE)
    gp_path = render_module.render(emit_score(score), tmp_path)

    assert gp_path.read_bytes().startswith(b"PK\x03\x04")
    with zipfile.ZipFile(gp_path) as archive:
        gpif = archive.read(GPIF_ENTRY).decode("utf-8")

    # The right-hand tap on each string's top, the left-hand taps below it, and
    # the hammer-on/pull-off legato that R9 makes load-bearing for scales
    # (alphaTab spells a hammer/pull as the `HopoOrigin`/`HopoDestination` pair).
    assert 'name="Tapped"' in gpif
    assert 'name="LeftHandTapped"' in gpif
    assert 'name="HopoOrigin"' in gpif
