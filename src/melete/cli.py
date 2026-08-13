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
completed. §13 still requires the generated `.atex` to survive a failed render,
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
`.gp`s sitting beside today's sheet, presented as part of it. The removal happens
after the draw succeeds, so a configuration that no longer selects cannot
destroy the record of the day it was going to replace.

## One table, not two

`COMMANDS` builds the parser *and* dispatches it. §11 documents five
subcommands, and a handler with no subparser or a subparser with no handler
would be a `KeyError` reached only at run time — so the two are one structure
rather than two lists that have to be kept in step.

## The four read-only commands

`replay` and `show` read a recorded day; `families` and `vocabulary` read the
registries. None of them draws — `generate` is the only command that calls the
selector — and none of them writes a session log. `replay` is the only one that
writes anything at all, and what it writes is an engraving of a record that
already exists.
"""

from __future__ import annotations

import argparse
import datetime
import shutil
import sys
import textwrap
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path
from random import Random
from typing import TYPE_CHECKING

from melete import config, rhythm, session, vocabulary
from melete.alphatab import emit, render
from melete.families import REGISTRY
from melete.selection import SelectionError, select

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from melete.config import AxisValue, Config
    from melete.score import Score
    from melete.selection import ExerciseSpec, WeightInputs

#: What one subcommand does, once its arguments are parsed. The working
#: directory is passed rather than looked up, so every command resolves the
#: configuration and `sessions/` against the same root.
type Handler = Callable[[argparse.Namespace, Path], int]

#: How one subcommand declares its own arguments onto its own subparser.
type Arguments = Callable[[argparse.ArgumentParser], None]

#: §10's configuration, looked up in the working directory.
CONFIG_NAME = "config.toml"

#: §12's directory of generated alphaTex source: one file per exercise, and one
#: for the book.
SOURCES = "src"

#: The stem the combined document is generated under. Its `.gp` is moved up to
#: `practice.gp`, which is the name §12 prints.
BOOK = "book"

EXIT_OK = 0
EXIT_FAILED = 1


class CliError(RuntimeError):
    """A refusal this module owns, rather than one a stage below it raises.

    There are five, and each one is a fact only this layer holds: a session
    directory that already exists (§13), a `--count` that contradicts the
    declared shape, a date with no recorded session, a session directory whose
    run never completed, and a replay whose recorded instrument is not the one
    the configuration now describes.
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
        return COMMANDS[args.command].run(args, Path.cwd())
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
    """§11's command line, built from the one table that also dispatches it."""
    parser = argparse.ArgumentParser(
        prog="melete",
        description="Generate parameterized bass practice exercises.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name, command in COMMANDS.items():
        command.arguments(subcommands.add_parser(name, help=command.help))
    return parser


def _no_arguments(_subparser: argparse.ArgumentParser) -> None:
    """A subcommand that takes nothing. `families` and `vocabulary` read registries."""


def _a_date(subparser: argparse.ArgumentParser) -> None:
    """The positional §11 gives `replay` and `show`: which recorded day."""
    subparser.add_argument(
        "date",
        type=_iso_date,
        metavar="YYYY-MM-DD",
        help="the date of the recorded session",
    )


def _generate_flags(generate: argparse.ArgumentParser) -> None:
    """§11's six flags. None of them is a path — the working directory is the project."""
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
        help="also render one .gp per exercise",
    )


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

    print(f"wrote {target / render.GP_NAME}")
    return EXIT_OK


def _overridden(active: Config, args: argparse.Namespace) -> Config:
    """§11's `--count` override, applied before anything reads it.

    Applied to the `Config` itself rather than carried beside it, so that one
    object describes the run — including the hash the seed is derived from, which
    `--count` deliberately moves: a different count is a different draw.
    """
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
    score, _hints = REGISTRY[spec.family].generate(active.instrument, spec.params)
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
    """§12's directory: the sources, the combined document, and the split `.gp`s.

    The order is the contract. Every source is written before anything is
    rendered, so a failed render leaves the whole day on disk to be inspected
    and re-run by hand (§13) rather than however much of it had been engraved.
    The book renders before any `--split` `.gp`, because the book is the printing
    unit and the split files are an extra.

    Sources are rendered *in* `src/` and the `.gp`s moved up, because §12 puts the
    generated source in `src/` and the printable documents at the top of the
    session directory, and a render writes its `.atex` beside its `.gp`. The
    per-exercise `.atex` is written for every exercise regardless of `--split`,
    so the sources are complete even when only the book is rendered; `--split`
    adds the per-exercise `.gp`s beside the book's.
    """
    sources = target / SOURCES
    sources.mkdir(parents=True)

    pages = [emit.emit_score(score) for score in scores]
    for number, page in enumerate(pages, start=1):
        (sources / f"{_stem(number)}.atex").write_text(page, encoding="utf-8")

    cover = emit.Cover(date=on.isoformat(), instrument=active.instrument.name)
    book = emit.emit_book(scores, cover)
    render.render(book, sources, stem=BOOK).replace(target / render.GP_NAME)

    if not split:
        return
    for number, page in enumerate(pages, start=1):
        stem = _stem(number)
        render.render(page, sources, stem=stem).replace(target / f"{stem}.gp")


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


# --------------------------------------------------------------------------
# Reading a recorded day (spec §13)
# --------------------------------------------------------------------------

_NO_SESSION = (
    "no session is recorded for {date}. {directory} does not exist, so nothing was generated "
    "for that day: `melete generate --date {date}` draws one."
)

_INCOMPLETE = (
    "{date} has a session directory but no {filename}, so that run never completed. §13 keeps "
    "the generated source on disk after a failed render, which is what is left here; the day is "
    "not a session and no sheet was produced. Inspect {directory} and then delete it, and the "
    "day can be generated again."
)


def _recorded(root: Path, on: datetime.date) -> session.Session:
    """One day's record, or a refusal that says which of the two things went wrong.

    `session.read` reports a missing log as "cannot be read", which is true and
    is not an instruction. This layer knows one thing that module does not —
    whether the *directory* is there — and the two cases have different repairs:

    * No directory at all: the day was never generated. Generate it.
    * A directory with no log: a run created it and then failed before it
      completed (see this module's docstring on why the log is written last).
      The sources §13 keeps are in it; deleting the directory clears the day.

    A log that exists and is corrupt is neither, and is left entirely to
    `session.read`: §13 makes that a hard error naming the file and the
    position inside it, and nothing here improves on that.
    """
    directory = session.directory(root, on)
    if not directory.exists():
        raise CliError(_NO_SESSION.format(date=on.isoformat(), directory=directory))
    if not (directory / session.FILENAME).exists():
        raise CliError(
            _INCOMPLETE.format(date=on.isoformat(), filename=session.FILENAME, directory=directory)
        )
    return session.replay(root, on)


def ordered(spec: ExerciseSpec) -> ExerciseSpec:
    """The recorded parameters back in the order they were drawn in.

    `session.json` is written key-sorted, because §12 requires a file whose
    diff is readable, so a specification read back from it is alphabetical
    rather than in the order `selection._sample` built it. That is not
    cosmetic: §12's cover entry is generated by walking `params`, so without
    this a replayed sheet lists each exercise's axes in a different order than
    the sheet it reproduces — the one visible difference between the two, in
    the one place a reader compares them. `show` reads it for the same reason
    from the other side: a summary that listed the axes in a different order
    than the sheet would be describing the page in an order the page does not
    have.

    The order is reconstructed rather than recorded, from the family's own
    declared axes followed by §8's rhythm axes, which is exactly how the
    selector builds one. An axis in the record that neither declares is kept
    at the end in the order it was read: dropping a recorded parameter to tidy
    an ordering would be a silent loss of the thing being reproduced. A family
    the registry does not know is the same case one level up — every axis is
    unrecognised, so every axis is kept — because this function orders a
    record and is not the place that judges whether it can be engraved.
    """
    family = REGISTRY.get(spec.family)
    declared = [*(() if family is None else family.axes), *rhythm.AXES]
    axes = [axis for axis in declared if axis in spec.params]
    axes += [axis for axis in spec.params if axis not in declared]
    return replace(spec, params={axis: spec.params[axis] for axis in axes})


# --------------------------------------------------------------------------
# replay (spec §9 Determinism, §11)
# --------------------------------------------------------------------------

_REPLAY_INSTRUMENT = (
    "{date} was recorded on {recorded!r}, and [instrument] profile is now {current!r}. Replay "
    "engraves the recorded exercises, and where a note is played is a fact about one instrument "
    "(§5): the recorded string indices and frets would engrave as convincing tablature for the "
    "wrong bass. Restore {recorded!r} to replay this day, or generate a new session."
)

_CONFIG_MOVED = (
    "note: the configuration has changed since {date} was generated. The exercises are the "
    "recorded ones and are unaffected, but the tempo ranges are read from [pool] as they are now."
)

_UNKNOWN_FAMILY = (
    "{path} records the exercise family {unknown!r}, which is not one melete generates. §12 "
    "makes the log hand-editable, so this is a value to correct rather than a bug; the families "
    "are {accepted}."
)


def _replay(args: argparse.Namespace, root: Path) -> int:
    """§11's `replay`: re-engrave a recorded day from its own record.

    ## This is a read-back, not a re-execution

    `session.json` holds every exercise in full (§12), so the reproduction is
    reading them and running them back through the family, §8's rhythm
    modifier, the emitter and the renderer — the same pipeline `generate` uses,
    minus the draw. Nothing is re-derived, because there is nothing left to
    derive: the seed and the weight inputs recorded beside the exercises are
    the *account* of why that draw happened, which is what makes the day
    auditable, and re-running the selector against them would only recompute
    values already on disk.

    **What this therefore does not catch.** Replay is not a regression test on
    the selector. A change to `selection` that would have drawn a different
    session for that seed and those weight inputs is invisible here — the
    recorded exercises come back either way. Re-execution would be a stronger
    guarantee and would catch exactly that, but it is a different feature
    wearing the same name, and it would need an injection point in
    `selection.select` for the recorded weight inputs that does not exist.

    ## What is *not* read from the record

    The record identifies the instrument by name (§12), so the profile itself —
    the tuning, the fret count, the position span — comes from the
    configuration, as do the tempo ranges. The instrument is
    checked by name and a mismatch is refused, because engraving one bass's
    exercises for another is §5's failure exactly. The rest is presentational
    and is reported rather than refused: a configuration hash that no longer
    matches prints a note saying which parts of the sheet came from today's
    settings.
    """
    on: datetime.date = args.date
    recorded = _recorded(root, on)
    unknown = sorted({spec.family for spec in recorded.exercises} - set(REGISTRY))
    if unknown:
        raise CliError(
            _UNKNOWN_FAMILY.format(
                path=session.directory(root, on) / session.FILENAME,
                unknown=unknown[0],
                accepted=sorted(REGISTRY),
            )
        )

    active = config.load(root / CONFIG_NAME)
    if active.instrument.name != recorded.instrument:
        raise CliError(
            _REPLAY_INSTRUMENT.format(
                date=on.isoformat(),
                recorded=recorded.instrument,
                current=active.instrument.name,
            )
        )
    if session.config_hash(active) != recorded.config_hash:
        print(_CONFIG_MOVED.format(date=on.isoformat()))

    target = session.directory(root, on)
    sources = target / SOURCES
    if sources.exists():
        # Replaced rather than written into, for `--force`'s reason: a source
        # left over from the run being replayed is not part of this engraving.
        shutil.rmtree(sources)

    scores = [_score(active, ordered(spec)) for spec in recorded.exercises]
    _engrave(target, active, scores, on, split=False)

    print(f"replayed {on.isoformat()} to {target / render.GP_NAME}")
    return EXIT_OK


# --------------------------------------------------------------------------
# show (spec §11, §12)
# --------------------------------------------------------------------------


def phrase(axis: str, value: AxisValue) -> str:
    """One recorded parameter in the words §12's cover page uses for it.

    The display name comes from `vocabulary` — the same registry the cover page
    reads — so `show` and the sheet it summarizes cannot name the same value
    differently. An axis the registry does not enumerate carries its own name,
    because "straight" alone does not say whether it was the note pattern or
    the note-value pattern.
    """
    named = _named(axis, value)
    if axis in vocabulary.AXES:
        return named
    return f"{axis.replace('_', ' ')} {named}"


def _show(args: argparse.Namespace, root: Path) -> int:
    """§11's `show`: what a past session was, read out of its own record.

    **The instrument is the recorded one, and the configuration is not read at
    all.** A profile edited since the session was generated would otherwise
    make this command misreport every day before the edit — silently, in the
    one command whose whole job is to report history — and a configuration that
    no longer loads would stop it reporting anything.

    The roots and the fret and octave numbers print as themselves. Spelling a
    root as a letter is a function of the exercise's key (§10a), the key is
    decided by the family when it realizes the exercise, and realizing it needs
    the configuration this command deliberately does not read. Printing "F#"
    where the sheet engraved "Gb" is the disagreement §10a exists to rule out,
    so the pitch integer is printed instead of a name that might be the wrong
    one.

    The axes print in the order they were drawn rather than the alphabetical
    order the record comes back in — see `ordered` — which is the order §12's
    cover page lists them in, so a summary and the sheet it summarizes read the
    same way round.
    """
    recorded = _recorded(root, args.date)
    print(f"{recorded.date.isoformat()}  {recorded.instrument}  seed {recorded.seed}")
    for number, spec in enumerate(recorded.exercises, start=1):
        params = ordered(spec).params
        phrases = ", ".join(phrase(axis, value) for axis, value in params.items())
        print(f"{number:>3}. {spec.family}: {phrases}")
    return EXIT_OK


# --------------------------------------------------------------------------
# families and vocabulary (spec §7, §8, §11, §13)
# --------------------------------------------------------------------------

#: Wide enough for the longest label — `rhythm` — plus a gap, so no label ever
#: runs into the list beside it.
_LABEL_COLUMN = 8
_IDENTIFIER_COLUMN = 24

#: Where the two explanatory notes wrap. Narrower than the 100-column source
#: limit, because these are paragraphs read on a terminal rather than code.
_WRAP = 88

_RHYTHM_NOTE = (
    "Rhythm is a modifier over all four families rather than a fifth family (§8), so every "
    "exercise also carries these axes:"
)

_RANGE_NOTE = (
    "The list above is every axis with an enumerated vocabulary, and it is not every axis. "
    "These are ranges rather than vocabularies — a root is a pitch class, a fret number and an "
    "octave count and a string set are bounded by the instrument profile (§5) — so they are "
    "validated against the profile rather than against a list, and a frozen enumeration here "
    "would be a second source of truth for something the profile already decides:"
)


def _families(_args: argparse.Namespace, _root: Path) -> int:
    """§11's `families`: the registry, printed.

    Every line is read out of `REGISTRY` — the axes a family declares and the
    tempo range §7 assigns it — so a fifth family is listed here by existing
    rather than by being added to a second list.
    """
    for name, family in REGISTRY.items():
        slowest, fastest = family.default_tempo_range
        print(f"{name}")
        print(f"  {'tempo':<{_LABEL_COLUMN}}{slowest}-{fastest} bpm")
        print(f"  {'axes':<{_LABEL_COLUMN}}{', '.join(family.axes)}")
    print()
    print(textwrap.fill(_RHYTHM_NOTE, width=_WRAP))
    print(f"  {'rhythm':<{_LABEL_COLUMN}}{', '.join(rhythm.AXES)}")
    return EXIT_OK


def _unenumerated() -> list[str]:
    """The axes every family reads that `vocabulary` deliberately does not enumerate.

    Derived rather than listed. Restating them here would be the third copy of
    a set that already exists twice — once as what the families declare, once
    as what the registry holds — and a fifth family's range axis would go
    unmentioned rather than appearing.
    """
    every = {axis for family in REGISTRY.values() for axis in family.axes}
    every.update(rhythm.AXES)
    return sorted(every - set(vocabulary.AXES))


def _vocabulary(_args: argparse.Namespace, _root: Path) -> int:
    """§11's `vocabulary`: every axis and its accepted values, from `vocabulary.AXES`.

    This is the registry §13 quotes when it refuses a misspelled key, printed
    so that it can be read before the refusal rather than after it.

    The range axes are named at the end rather than silently omitted. A list
    that looks exhaustive and is not will be read as one, and a reader who
    concluded that melete has no `root` axis would be reading a defect into the
    output of a command whose job is to be complete.
    """
    for axis, values in vocabulary.AXES.items():
        print(axis)
        for identifier, name in values.items():
            print(f"  {identifier:<{_IDENTIFIER_COLUMN}}{name}")
    print()
    print(textwrap.fill(_RANGE_NOTE, width=_WRAP))
    print(f"  {', '.join(_unenumerated())}")
    return EXIT_OK


# --------------------------------------------------------------------------
# The command table (spec §11)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Command:
    """One subcommand: what it does, what it is for, and what it parses."""

    #: The handler, run with the parsed arguments and the project root.
    run: Handler
    #: The one-line description `melete --help` lists.
    help: str
    #: Declares this subcommand's own arguments onto its own subparser.
    arguments: Arguments


#: §11's five subcommands. This table builds the parser and dispatches it, so a
#: handler with no subparser — or a subparser reaching no handler — is not a
#: state this module can be in.
COMMANDS: dict[str, Command] = {
    "generate": Command(
        _generate,
        "draw a day's exercises and engrave them as one printable document",
        _generate_flags,
    ),
    "replay": Command(_replay, "re-engrave a past session from its record", _a_date),
    "show": Command(_show, "summarize a past session", _a_date),
    "families": Command(_families, "list the families and their parameter axes", _no_arguments),
    "vocabulary": Command(_vocabulary, "list every axis and its accepted values", _no_arguments),
}
