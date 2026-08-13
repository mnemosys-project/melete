r"""Acceptance goldens: the five 2026-08-13 exercises, frozen (epic #57, Task 11).

This is the epic's acceptance proof, not a unit test of any single stage. It
freezes one real day — the five exercises drawn for 2026-08-13 from
`examples/config.toml` — and asserts three things the completed pipeline now
guarantees for *every* exercise it engraves:

* **Reproducibility.** Regenerating the day in-process draws the byte-identical
  alphaTex the frozen goldens hold. The draw is deterministic from the date and
  the configuration (§9), so a change anywhere in the family → fitter → rhythm →
  emit path that would have altered the sheet fails here, naming the exercise.
* **Every exercise repeats** (§5): the `\ro` … `\rc 2` bracket is present in the
  text, and the in-memory Score carries `repeat=True`.
* **No partial measure.** The fitter derives a whole-bar meter (#118), so every
  `|`-separated bar carries exactly its `\ts`'s worth of sounding time. This is
  checked structurally on the in-memory Score through the same `bar()` /
  `sounding_duration` the emitter uses, rather than by re-parsing the text.

The meter is also asserted *simple* — a `/4`, or `/8` for a compound feel, never
a `/16`. A day that regenerated with a partial bar or a `/16` meter would mean
the pipeline is not clean and this frozen day is a bad golden; the assertions
below are written to fail loudly in that case rather than freeze the defect.

Reproduction runs the real `cli._score` over the real selector and emitter, so
it needs no renderer and runs in the ordinary pytest job. The one integration
test renders the frozen book to a `.gp` to confirm the day loads through the
real alphaTab toolchain; it is `@pytest.mark.integration` and skips on a bare
host, exactly as the render integration tests do. The dedicated Guitar Pro
visual check is a separate task (melete#122).
"""

from __future__ import annotations

import datetime
import re
import shutil
import zipfile
from fractions import Fraction
from pathlib import Path
from random import Random
from typing import TYPE_CHECKING

import pytest

from melete import config, session
from melete.alphatab import emit
from melete.alphatab import render as render_module
from melete.alphatab.render import render
from melete.cli import _score
from melete.score import bar, sounding_duration
from melete.selection import select

if TYPE_CHECKING:
    from melete.score import Score

#: The frozen day and the configuration it was drawn from. The config path is
#: resolved from this test file so the test is independent of the working
#: directory the suite is launched in.
GOLDEN = Path(__file__).parent / "golden" / "practice-2026-08-13"
CONFIG = Path(__file__).parents[2] / "examples" / "config.toml"

#: The date the frozen day was generated for, and the number of exercises the
#: session shape declares. `range(1, COUNT + 1)` names the per-exercise goldens.
ON = datetime.date(2026, 8, 13)
COUNT = 5

#: The exercise numbers, for `pytest.mark.parametrize` and the golden filenames.
NUMBERS = tuple(range(1, COUNT + 1))


def _draw() -> list[Score]:
    """Redraw the frozen day in-process, exactly as `cli._generate` does.

    Empty history is the frozen day's own condition — it was generated against a
    clean project — and the seed is derived from the date and the configuration
    hash (§9), so this is deterministic and needs no session directory on disk.
    `cli._score` is the real per-exercise pipeline (family, fitter, rhythm, and
    the tempo override), so the alphaTex it feeds the emitter is the alphaTex the
    generator froze.
    """
    active = config.load(CONFIG)
    seed = session.seed_for(ON, session.config_hash(active))
    picks = select(active, [], Random(seed))  # noqa: S311 - reproducibility is the requirement (§9)
    return [_score(active, spec) for spec, _inputs in picks]


@pytest.fixture(scope="module")
def scores() -> list[Score]:
    """The redrawn day, drawn once and shared across the module's assertions."""
    drawn = _draw()
    assert len(drawn) == COUNT
    return drawn


def _golden(number: int) -> str:
    """The frozen alphaTex for one exercise."""
    return (GOLDEN / f"exercise-{number:02d}.atex").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Reproducibility
# --------------------------------------------------------------------------


@pytest.mark.parametrize("number", NUMBERS)
def test_each_exercise_reproduces_byte_for_byte(scores: list[Score], number: int) -> None:
    """Re-emitting the redrawn exercise is byte-identical to its frozen golden."""
    assert emit.emit_score(scores[number - 1]) == _golden(number)


def test_the_book_reproduces_byte_for_byte(scores: list[Score]) -> None:
    """The combined book the day prints from is frozen alongside its exercises."""
    active = config.load(CONFIG)
    cover = emit.Cover(date=ON.isoformat(), instrument=active.instrument.name)
    book = emit.emit_book(scores, cover)
    assert book == (GOLDEN / "book.atex").read_text(encoding="utf-8")


def test_the_draw_is_deterministic() -> None:
    """Drawing the day a second time emits the identical alphaTex for every slot.

    Reproducibility against the frozen text proves the day matches *today's*
    pipeline; this proves the draw itself carries no hidden state — the same date
    and configuration hand back the same sheet on every run (§9).
    """
    first = [emit.emit_score(s) for s in _draw()]
    second = [emit.emit_score(s) for s in _draw()]
    assert first == second


# --------------------------------------------------------------------------
# The two acceptance properties: repeats, and no partial measure
# --------------------------------------------------------------------------


@pytest.mark.parametrize("number", NUMBERS)
def test_each_exercise_is_wrapped_in_a_repeat(scores: list[Score], number: int) -> None:
    """Every exercise repeats (§5): the tokens are in the text and the Score agrees."""
    text = _golden(number)
    assert emit.REPEAT_OPEN in text
    assert emit.REPEAT_CLOSE in text
    assert scores[number - 1].repeat is True


@pytest.mark.parametrize("number", NUMBERS)
def test_each_exercise_has_no_partial_measure(scores: list[Score], number: int) -> None:
    """Every bar carries a full `\\ts`'s worth of sounding time (#118).

    Checked structurally through the same `bar()` / `sounding_duration` the
    emitter bars with: a bar of `beats/value` holds `beats * (1/value)` whole
    notes, and the fitter's whole-bar meter means every measure equals that.
    """
    score = scores[number - 1]
    beats, value = score.time_signature
    capacity = beats * Fraction(1, value)
    measures = bar(score.voice, score.time_signature)
    assert measures  # the exercise has at least one bar
    assert all(sounding_duration(measure.voice) == capacity for measure in measures)


@pytest.mark.parametrize("number", NUMBERS)
def test_each_meter_is_simple(scores: list[Score], number: int) -> None:
    """The time signature is a `/4` or a compound `/8`, never a `/16` (§8, plan)."""
    _beats, value = scores[number - 1].time_signature
    assert value in (4, 8)


# --------------------------------------------------------------------------
# The book renders through the real toolchain (optional; melete#122 owns the eye)
# --------------------------------------------------------------------------

#: `node` on PATH, resolved once — the same gate the render integration tests
#: use. `None` skips: the renderer needs the Node/alphaTab toolchain the dev
#: container carries, which a bare host has no way to run.
NODE_ON_PATH = shutil.which(render_module.NODE)

NO_NODE = (
    "Node is not on PATH. Rendering the frozen book to a .gp needs the Node/alphaTab "
    "toolchain the dev container bakes onto NODE_PATH (vergil.toml [container]); it runs "
    "for real under vrg-container-run and skips on a bare host, the same discipline the "
    "render integration tests use. The Guitar Pro visual check is a separate task "
    "(melete#122)."
)


@pytest.mark.integration
@pytest.mark.skipif(NODE_ON_PATH is None, reason=NO_NODE)
def test_the_frozen_book_renders_to_a_valid_gp(tmp_path: Path) -> None:
    """The frozen book loads through the real renderer — the day engraves cleanly.

    Structural, not content-correctness: a returned `.gp` that exists is proof
    the toolchain accepted the day's alphaTex. Whether the *right* notes landed
    is what the byte-for-byte goldens above pin.
    """
    book = (GOLDEN / "book.atex").read_text(encoding="utf-8")
    gp = render(book, tmp_path)
    assert gp.exists()
    assert gp.read_bytes()[:2] == b"PK"  # a .gp is a ZIP; this is its magic


@pytest.mark.integration
@pytest.mark.skipif(NODE_ON_PATH is None, reason=NO_NODE)
def test_the_rendered_book_lays_out_one_system_per_exercise(
    scores: list[Score], tmp_path: Path
) -> None:
    r"""The rendered `.gp` carries the per-exercise bar counts as its track layout.

    This is the melete#138 fix proven end to end: `emit_book`'s `\track`
    systemslayout directive must survive the real alphaTab toolchain and land as
    the master track's `<SystemsLayout>` in the exported `Content/score.gpif`,
    equal to `[bar_count(exercise) for exercise in the day]` — one system per
    exercise, so the `\section` titles no longer overprint. The score-level layout
    is not honored for a single-track book, so the *track-level* element is what
    matters and is what is asserted here.
    """
    expected = " ".join(str(len(bar(score.voice, score.time_signature))) for score in scores)

    book = (GOLDEN / "book.atex").read_text(encoding="utf-8")
    gp = render(book, tmp_path)
    with zipfile.ZipFile(gp) as archive:
        name = next(n for n in archive.namelist() if n.endswith("score.gpif"))
        gpif = archive.read(name).decode("utf-8")

    track_layouts = re.findall(r"<SystemsLayout>([^<]*)</SystemsLayout>", gpif)
    assert track_layouts == [expected]
