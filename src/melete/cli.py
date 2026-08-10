"""The command line: argument parsing, and the wiring of spec §4's pipeline.

This module decides nothing about music. It loads the configuration, applies
§11's two overrides, draws a session, realizes each specification through its
family and §8's rhythm modifier, engraves the day as one book, renders it, and
writes the log. Every stage above is a module that can be tested without this
one, which is why this file is short and why its tests are about *composition*
rather than about any single stage.

## The working directory is the project

`generate` takes seven flags (§11) and none of them is a path. The
configuration is `config.toml` beside the sessions directory, both resolved
against the process's working directory, so a project is a directory rather
than a set of paths that have to agree with each other.

## Why `session.json` is written last

`session.write` creates the day's directory and writes the log. Called before
the render, a failed render would leave a directory that the next run refuses
without `--force` *and* — the worse half — a `session.json` that
`session.history` counts as a real session, so a day that produced no sheet at
all would push down every value it drew for the next fourteen days, invisibly.

Written last, the file's presence means exactly one thing: this session
completed. §13 still requires the generated `.ly` to survive a failed render,
so the directory does persist — it just does not become a session. The two
consequences are deliberate:

* The refusal §13 asks for is made **here**, before anything is written, rather
  than by `session.write` at the end (which is passed `force=True`, because by
  then the directory exists precisely because this run made it).
* A run whose render failed leaves a directory with sources and no log. The
  next run for that date refuses it by name, and `--force` replaces it. A
  *later* date reads it as a corrupt history entry and stops naming the file
  (§13's row) rather than quietly generating against a history with a hole in
  it — loud, and repaired by deleting the directory the message names.

## What `--force` does

It replaces the directory rather than writing into it: a `--split` run followed
by a forced run without `--split` would otherwise leave yesterday's per-exercise
PDFs sitting beside today's sheet, presented as part of it. The removal happens
after the draw succeeds, so a configuration that no longer selects cannot
destroy the record of the day it was going to replace.
"""

from __future__ import annotations

import argparse
import datetime
import shutil
import sys
from dataclasses import replace
from functools import partial
from pathlib import Path
from random import Random
from typing import TYPE_CHECKING

from melete import config, rhythm, session, vocabulary
from melete.families import REGISTRY
from melete.lilypond import emit, render
from melete.selection import SelectionError, select

if TYPE_CHECKING:
    from collections.abc import Sequence

    from melete.config import AxisValue, Config
    from melete.score import Score
    from melete.selection import ExerciseSpec, WeightInputs

#: §10's configuration, looked up in the working directory.
CONFIG_NAME = "config.toml"

#: §12's directory of generated LilyPond source: one file per exercise, and one
#: for the book.
SOURCES = "src"

#: The stem the combined document is generated under. Its PDF is moved up to
#: `practice.pdf`, which is the name §12 prints.
BOOK = "book"

EXIT_OK = 0
EXIT_FAILED = 1


class CliError(RuntimeError):
    """A refusal this module owns, rather than one a stage below it raises.

    There are two: a session directory that already exists (§13), and a
    `--count` that contradicts the declared shape.
    """


#: Every stage's own error type. Caught in `main` and printed verbatim, because
#: §13 makes each of them a message to a person rather than a traceback.
_HANDLED = (
    CliError,
    config.ConfigError,
    SelectionError,
    session.SessionError,
    render.RenderError,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command and return its exit status.

    Every stage's own error is printed as its own message. Nothing is re-worded
    on the way out: §13 writes those messages to name the key, the axis or the
    file that has to be fixed, and a wrapper saying "generation failed" would
    throw exactly that away. What is *not* caught is a bug — a family emitting
    a note off the fretboard raises, and a traceback is the right output for it.
    """
    args = _parser().parse_args(argv)
    try:
        return _generate(args, Path.cwd())
    except _HANDLED as exc:
        print(f"melete: {exc}", file=sys.stderr)
        return EXIT_FAILED


# --------------------------------------------------------------------------
# Parsing (spec §11)
# --------------------------------------------------------------------------


def _iso_date(text: str) -> datetime.date:
    """`--date`, as a date. The parser names the flag; this names the format."""
    try:
        return datetime.date.fromisoformat(text)
    except ValueError as exc:
        msg = f"{text!r} is not an ISO date like 2026-08-10"
        raise argparse.ArgumentTypeError(msg) from exc


def _at_least(minimum: int, text: str) -> int:
    """An integer flag, bounded where the bound belongs — at the flag.

    A negative `--seed` writes a log `session.read` then refuses (§13), and a
    `--count` of zero asks the emitter for a book with no exercises. Both are
    caught here, where argparse can name the flag that carried them.
    """
    try:
        value = int(text)
    except ValueError as exc:
        msg = f"{text!r} is not an integer"
        raise argparse.ArgumentTypeError(msg) from exc
    if value < minimum:
        msg = f"must be {minimum} or greater, got {value}"
        raise argparse.ArgumentTypeError(msg)
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="melete",
        description="Generate parameterized bass practice exercises.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    generate = subcommands.add_parser(
        "generate",
        help="draw a day's exercises and engrave them as one printable document",
    )
    generate.add_argument(
        "--date",
        type=_iso_date,
        default=None,
        metavar="YYYY-MM-DD",
        help="the session date; defaults to today",
    )
    generate.add_argument(
        "--seed",
        type=partial(_at_least, 0),
        default=None,
        help="fix the draw against the current history, rather than deriving the seed (§9)",
    )
    generate.add_argument(
        "--dry-run",
        action="store_true",
        help="print the selections and render nothing",
    )
    generate.add_argument(
        "--staves",
        choices=config.STAVES,
        default=None,
        help="override [output] staves for this run",
    )
    generate.add_argument(
        "--count",
        type=partial(_at_least, 1),
        default=None,
        help="override [session] count for this run",
    )
    generate.add_argument(
        "--force",
        action="store_true",
        help="replace an existing session directory",
    )
    generate.add_argument(
        "--split",
        action="store_true",
        help="also render one PDF per exercise",
    )
    return parser


# --------------------------------------------------------------------------
# generate (spec §4's pipeline)
# --------------------------------------------------------------------------

_ALREADY_GENERATED = (
    "{target} already exists. That session has been generated; refusing to overwrite the record "
    "of a sheet that may have been practised (§13). Pass --force to replace it."
)

_COUNT_AGAINST_SHAPE = (
    "--count {count} contradicts [session] shape, which declares {declared} exercises, one per "
    "family slot (§9). One of them is wrong and guessing which would silently generate the wrong "
    "session: edit the shape, or omit it to weight the families instead."
)


def _generate(args: argparse.Namespace, root: Path) -> int:
    active = _overridden(config.load(root / CONFIG_NAME), args)
    on: datetime.date = args.date if args.date is not None else datetime.date.today()

    target = session.directory(root, on)
    if target.exists() and not args.force:
        raise CliError(_ALREADY_GENERATED.format(target=target))

    seed: int = (
        args.seed if args.seed is not None else session.seed_for(on, session.config_hash(active))
    )
    picks = select(
        active,
        session.history(root, active.session.horizon, exclude=on),
        Random(seed),  # noqa: S311 - reproducibility is the requirement (§9)
    )

    if args.dry_run:
        _preview(on, active, picks, seed)
        return EXIT_OK

    if target.exists():
        # --force, checked above. Replaced rather than written into, so no
        # artifact of the session being replaced survives inside this one.
        shutil.rmtree(target)

    scores = [_score(active, spec) for spec, _inputs in picks]
    _engrave(target, active, scores, on, split=args.split)
    session.write(root, session.record(on, active, picks, seed), force=True)

    print(f"wrote {target / render.PDF_NAME}")
    return EXIT_OK


def _overridden(active: Config, args: argparse.Namespace) -> Config:
    """§11's two configuration overrides, applied before anything reads them.

    Applied to the `Config` itself rather than carried beside it, so that one
    object describes the run — including the hash the seed is derived from.
    That is why `--count` changes the draw and `--staves` does not:
    `session._fingerprint` excludes `[output]` deliberately, so a staff mode
    cannot hand back a different set of exercises.
    """
    if args.staves is not None:
        active = replace(active, output=replace(active.output, staves=args.staves))

    if args.count is None:
        return active

    shape = active.session.shape
    if shape is not None:
        raise CliError(_COUNT_AGAINST_SHAPE.format(count=args.count, declared=sum(shape.values())))
    return replace(active, session=replace(active.session, count=args.count))


def _score(active: Config, spec: ExerciseSpec) -> Score:
    """One specification realized: §4's family generator, then §8's modifier.

    The tempo range is the family's own until `[pool.<family>] tempo` overrides
    it (§10, decision #20). It is not a sampled axis, so it never travels in
    `params` and never reaches the family — this is the only place the
    documented override can be applied, and without it the setting would be a
    comment in the configuration file.
    """
    score = REGISTRY[spec.family].generate(active.instrument, spec.params)
    return replace(rhythm.apply(score, spec.params), tempo_range=active.pool[spec.family].tempo)


def _stem(number: int) -> str:
    return f"exercise-{number:02d}"


def _engrave(
    target: Path,
    active: Config,
    scores: list[Score],
    on: datetime.date,
    *,
    split: bool,
) -> None:
    """§12's directory: the sources, the combined document, and the split PDFs.

    The order is the contract. Every source is written before anything is
    rendered, so a failed render leaves the whole day on disk to be inspected
    and re-run by hand (§13) rather than however much of it had been engraved.
    The book renders before any `--split` PDF, because the book is the printing
    unit and the split PDFs are an extra.

    Sources are rendered *in* `src/` and the PDFs moved up, because §12 puts the
    generated source in `src/` and the printable documents at the top of the
    session directory, and a render writes its `.ly` beside its `.pdf`.
    """
    sources = target / SOURCES
    sources.mkdir(parents=True)

    staves = active.output.staves
    signatures = active.output.key_signatures
    pages = [emit.emit_score(score, staves, key_signatures=signatures) for score in scores]
    for number, page in enumerate(pages, start=1):
        (sources / f"{_stem(number)}.ly").write_text(page, encoding="utf-8")

    cover = emit.Cover(date=on.isoformat(), instrument=active.instrument.name)
    book = emit.emit_book(scores, cover, staves, key_signatures=signatures)
    render.render(book, sources, stem=BOOK).replace(target / render.PDF_NAME)

    if not split:
        return
    for number, page in enumerate(pages, start=1):
        stem = _stem(number)
        render.render(page, sources, stem=stem).replace(target / f"{stem}.pdf")


# --------------------------------------------------------------------------
# --dry-run
# --------------------------------------------------------------------------

_AXIS_COLUMN = 20


def _named(axis: str, value: AxisValue) -> str:
    """One drawn value in the words §12's cover page would use for it.

    Read out of `vocabulary` rather than printed raw, because §13 makes that
    registry the single source of display names: a preview with a private
    vocabulary is a preview that drifts from the sheet it is previewing. The
    range axes the registry deliberately does not enumerate — frets, octave
    counts, string sets — print as themselves.
    """
    if isinstance(value, tuple):
        return "-".join(str(item) for item in value)
    if axis in vocabulary.AXES:
        return vocabulary.display(axis, str(value))
    return str(value)


def _preview(
    on: datetime.date,
    active: Config,
    picks: list[tuple[ExerciseSpec, WeightInputs]],
    seed: int,
) -> None:
    """§11's `--dry-run`: the selections, and nothing written anywhere.

    Nothing is written *at all* — not even the session directory. A dry run
    that logged its draw would be counted by `session.history` as a day that
    was practised, which is the recency weighting corrupted by a command whose
    entire promise is that it changes nothing.
    """
    print(f"{on.isoformat()}  {active.instrument.name}  seed {seed}")
    for number, (spec, _inputs) in enumerate(picks, start=1):
        print(f"{number:>3}. {spec.family}")
        for axis in sorted(spec.params):
            print(f"     {axis:<{_AXIS_COLUMN}} {_named(axis, spec.params[axis])}")
    print("dry run: nothing was written")
