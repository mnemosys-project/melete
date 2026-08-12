# Melete — Command-Line Reference

Every subcommand, every flag, what each one writes and what each one refuses.
This page states behaviour; the reasoning behind it lives in the epic #1
specification (§9 *Determinism*, §11 *Command-Line Interface*, §12 *Output and
Session Log*, §13 *Error Handling*), which
[docs/design.md](design.md) links to.

For the configuration file every command reads, see
[configuration.md](configuration.md).

## Table of Contents

- [The working directory is the project](#the-working-directory-is-the-project)
- [Synopsis](#synopsis)
- [`generate`](#generate)
- [The session directory](#the-session-directory)
- [`session.json` is written last](#sessionjson-is-written-last)
- [`replay`](#replay)
- [`show`](#show)
- [`families`](#families)
- [`vocabulary`](#vocabulary)
- [Exit status](#exit-status)
- [What is renderer-specific](#what-is-renderer-specific)

## The working directory is the project

No command takes a path. Both the configuration and the output directory are
resolved against the process's current working directory:

```text
<cwd>/config.toml           the configuration (configuration.md)
<cwd>/sessions/YYYY-MM-DD/  one directory per generated day
```

A project is therefore a directory, not a set of paths that have to agree with
each other. Run melete from the directory that holds `config.toml`.

A missing or unreadable `config.toml` is a hard error naming the path. There is
no built-in default configuration.

## Synopsis

```text
melete generate [--date YYYY-MM-DD] [--seed N] [--dry-run]
                [--staves {both,tab,notation}] [--count N] [--force] [--split]
melete replay YYYY-MM-DD
melete show YYYY-MM-DD
melete families
melete vocabulary
```

`generate` is the only command that draws exercises, and the only one that
writes a session log. `replay`, `show`, `families` and `vocabulary` read; of
those, only `replay` writes anything, and what it writes is an engraving of a
record that already exists.

## `generate`

Draws a day's exercises and engraves them as one Guitar Pro document.

The run, in order:

1. Load `config.toml` from the working directory.
2. Apply the `--staves` and `--count` overrides to the loaded configuration.
3. Resolve the date: `--date`, or today.
4. **Refuse** if `sessions/<date>/` already exists and `--force` was not given.
5. Resolve the seed: `--seed`, or a value derived from the date and a hash of
   the configuration.
6. Read the history — the most recent `[session] horizon` session logs under
   `sessions/`, excluding the date being generated — and draw the session.
7. With `--dry-run`, print the draw and stop, having written nothing.
8. With `--force`, remove the existing directory (after the draw succeeded).
9. Write `src/<exercise>.atex` for every exercise, render the book to
   `practice.gp`, then render the `--split` `.gp`s if asked for.
10. Write `session.json`.
11. Print `wrote sessions/<date>/practice.gp`.

### `--date YYYY-MM-DD`

The session date. Defaults to today. The value must be an ISO date; anything
else is an argument error naming the flag and the format.

The date is part of the seed, and it is the directory name, so generating a
past date is how a missed day is filled in.

### `--seed N`

Fix the draw's random seed. `N` is an integer of 0 or greater; a negative value
is rejected by the parser.

Without it the seed is derived from the session date plus a hash of the
configuration, so a re-run of the same date against the same configuration
draws the same session, and an edited pool draws a different one.

**`--seed` is not a reproduction.** The draw also depends on the session
history, which grows every day, so the same seed against a different history
produces a different sheet. `--seed` fixes the draw against whatever history
exists *now*; it is useful for exploring a pool. `replay` is the operation that
reproduces a past sheet. See spec §9 *Determinism*.

The seed actually used is recorded in `session.json` either way.

### `--dry-run`

Print the draw and render nothing.

The output is the date, the instrument name and the seed, followed by each
selected exercise: its family, and every drawn axis with the value in the words
the cover page would use for it.

**Nothing is written at all** — not the `.gp`, not the sources, not the session
directory. A dry run that logged its draw would be counted by the history as a
day that was practised, corrupting the recency weighting from the one command
whose promise is that it changes nothing.

The refusal on an existing session directory (step 4) happens *before* the
draw, so `--dry-run` on an already-generated date refuses rather than
previewing. Add `--force` to preview one.

### `--staves {both,tab,notation}`

Override `[output] staves` for this run. See
[configuration.md](configuration.md#output) for what the three modes mean.

This does not change the draw. The configuration hash the seed is derived from
deliberately excludes `[output]`, so a staff mode cannot hand back a different
set of exercises.

**Inert for the `.gp` output.** A Guitar Pro file carries notation and
tablature together and inseparably, so the flag is accepted but selects
nothing — see [What is renderer-specific](#what-is-renderer-specific).

### `--count N`

Override `[session] count` for this run. `N` is an integer of 1 or greater.

**Refused when `[session] shape` is declared**, because a shape names one
family per exercise slot and therefore already fixes the count. The error names
the count the shape declares. Edit the shape, or remove it to weight families
instead.

Unlike `--staves`, this *does* change the draw: `[session]` is part of the
configuration hash the derived seed reads.

### `--force`

Replace an existing session directory.

The directory is **removed and recreated**, not written into. A `--split` run
followed by a forced run without `--split` would otherwise leave the previous
day's per-exercise `.gp`s sitting beside the new sheet, presented as part of it.

The removal happens after the draw succeeds, so a configuration that no longer
selects cannot destroy the record of the day it was going to replace.

### `--split`

Additionally render one `.gp` per exercise, as `exercise-01.gp`,
`exercise-02.gp`, … beside `practice.gp`.

The combined document is the printing unit and is always produced; the split
`.gp`s are an extra, and they are rendered after it.

Renderer-specific — see [What is renderer-specific](#what-is-renderer-specific).

### What `generate` refuses

| Condition | Behaviour |
|---|---|
| No readable `config.toml` in the working directory | Error naming the path |
| Any configuration error | Error naming the key (see configuration.md) |
| `sessions/<date>/` exists, no `--force` | Error naming the directory |
| `--count` given alongside `[session] shape` | Error naming both counts |
| A `[pool.*]` axis the family reads is undeclared | Error naming the axis and the section |
| The pool cannot produce a valid exercise in 500 attempts | Error naming the over-constrained axis |
| A directory under `sessions/` not named for a date | Error naming the directory |
| A session log in the history window that cannot be read | Error naming the file and the position in it |
| The renderer binary is missing, or the render fails | Error carrying the renderer's own output |

## The session directory

```text
sessions/2026-08-09/
  practice.gp         cover page + exercises: one Guitar Pro document
  session.json        every parameter of every exercise, the seed, and the
                      weight inputs that produced the draw
  src/                generated alphaTex source
    book.atex         the combined document
    exercise-01.atex  one file per exercise
    exercise-02.atex
    ...
```

`--split` adds one `.gp` per exercise at the top level of the directory, named
for the same stems as the sources:

```text
sessions/2026-08-09/
  practice.gp
  exercise-01.gp
  exercise-02.gp
  ...
```

Sources are written before anything is rendered, and they are rendered *in*
`src/` with the finished `.gp`s moved up, because the finished documents belong
at the top of the session directory and a render writes its `.gp` beside its
`.atex`. The renderer may leave its own by-products in `src/` as well.

`session.json` is described in spec §12 *The session log*. It is
human-readable, key-sorted, git-committable and hand-editable, and it is the
history later draws are weighted against.

## `session.json` is written last

The log is written **after** a successful render, not before it. Its presence
therefore means exactly one thing: **this session completed.**

The consequence is worth stating, because it surprises people:

- **A failed render leaves the session directory and its `.atex` sources on
  disk, and no `session.json`.** That is deliberate — the source is kept for
  inspection and for re-running the renderer by hand.
- Such a directory **is not a session**. The next run for that date refuses it
  by name, and `--force` replaces it. `replay` and `show` refuse it with a
  message saying the run never completed and that deleting the directory clears
  the day.
- A *later* date whose history window reaches that directory stops with a hard
  error naming the file, rather than quietly drawing against a history with a
  hole in it. The repair is to delete the directory the message names.

Written the other way round, a day that produced no sheet at all would still
count as a session and would push down every value it drew for the next
`horizon` days, invisibly.

## `replay`

```text
melete replay YYYY-MM-DD
```

Re-engrave a recorded day from its own record, writing `practice.gp` into that
day's existing session directory. `src/` is removed and regenerated for the
same reason `--force` replaces a directory: a source left over from the run
being replayed is not part of this engraving. No session log is written, and
the recorded log is not modified. Prints
`replayed <date> to sessions/<date>/practice.gp`.

**`replay` is read-back, not re-execution.** `session.json` holds every
exercise in full, so the reproduction is reading those exercises back and
running them through the family generator, the rhythm modifier, the emitter and
the renderer — the same pipeline `generate` uses, minus the draw. The recorded
seed and weight inputs are the *account* of why that draw happened, which is
what makes a day auditable; they are not re-fed to the selector.

**What that therefore does not catch.** Replay is not a regression test on the
selector. A change to the selection logic that would have drawn a different
session for that seed and those weight inputs is invisible here: the recorded
exercises come back either way. Re-execution would be a stronger guarantee, and
it is a different feature.

**What is read from the configuration rather than from the record.** The record
identifies the instrument by name only, so the profile itself — the tuning, the
fret count, the position span — comes from the current `config.toml`, as do the
tempo ranges (`[pool.<family>] tempo`). The `[output]` keys are read too, but
they no longer change the `.gp` — see
[What is renderer-specific](#what-is-renderer-specific).

| Condition | Behaviour |
|---|---|
| No `sessions/<date>/` directory | Error: nothing was generated for that day |
| Directory with no `session.json` | Error: that run never completed |
| `session.json` unreadable or malformed | Error naming the file and the position in it |
| The log names a family melete does not generate | Error naming the value and the accepted families |
| `[instrument] profile` no longer names the recorded instrument | **Refused**: the recorded string indices and frets would engrave as convincing tablature for the wrong bass |
| The configuration hash no longer matches | **Note printed, then it proceeds**: the exercises are the recorded ones, but tempo ranges are read from the configuration as it is now |

`replay` takes no flags. It is not affected by `--split`, and it always renders
the combined document only.

## `show`

```text
melete show YYYY-MM-DD
```

Summarize a past session on standard output. Writes nothing.

The first line is the date, the instrument and the seed; then one line per
exercise, giving its family and its recorded parameters in the order they were
drawn — the same order the cover page lists them in.

**`show` does not read `config.toml` at all.** The instrument it reports is the
recorded one. A profile edited since the session was generated would otherwise
make this command misreport every day before the edit, and a configuration that
no longer loads would stop it reporting anything.

Roots, fret numbers and octave counts print as numbers. Spelling a root as a
letter depends on the exercise's key, which is decided when the exercise is
realized, which needs the configuration this command deliberately does not
read — printing `F#` where the sheet engraved `Gb` would be exactly the
disagreement the spelling model (§10a) exists to rule out.

It refuses a missing directory and an incomplete one with the same two messages
`replay` uses.

## `families`

```text
melete families
```

Print the family registry: for each of `chromatic`, `scales`, `arpeggios` and
`intervals`, its default tempo range in beats per minute and the parameter axes
it reads. Then, separately, the rhythm axes, which are a modifier over all four
families rather than a fifth family and are carried by every exercise.

Takes no arguments and writes nothing. This is a self-documenting dump of the
registry the code dispatches on, so it cannot drift from what melete actually
generates. It is the command that answers "which axes must my `[pool.<family>]`
section declare?".

## `vocabulary`

```text
melete vocabulary
```

Print every parameter axis with an enumerated vocabulary, each accepted
identifier and its display name — the same registry the configuration validator
quotes when it refuses a misspelled value, and the same one the cover page
reads for display names.

The output ends by naming the axes that are deliberately **not** enumerated:
roots, fret numbers, octave counts, spans, intervals, string sets and
permutations are ranges bounded by the instrument profile rather than
vocabularies, so they are validated against the profile rather than against a
list.

Takes no arguments and writes nothing.

## Exit status

| Status | Meaning |
|---|---|
| 0 | The command succeeded |
| 1 | A handled failure: a configuration error, a refusal, an over-constrained pool, an unreadable session log, or a failed render. The message is printed to standard error, prefixed `melete: ` |
| 2 | An argument error from the parser: an unknown subcommand or flag, a malformed date, a non-integer or out-of-range `--seed` or `--count` |

Handled failures print the message the failing stage wrote, unchanged, because
those messages name the key, the axis or the file that has to be fixed. Anything
else — a defect rather than a refusal — surfaces as a traceback.

## What is renderer-specific

Melete engraves through alphaTab: the emitter writes alphaTex, and the vendored
`melete-render` Node tool renders it to a Guitar Pro `.gp`. Node with alphaTab
is an environment prerequisite, not a Python dependency: if Node is not
available, `generate` and `replay` fail with a message naming the missing tool
and how to resolve it. A failed render keeps the `.atex` source and reports the
renderer's own output verbatim.

Two parts of this page name the renderer:

- **`--split`**, which asks for one `.gp` per exercise in addition to the
  combined one, and **the contents of `src/`**, which are alphaTex source files.
- **`--staves` and `[output] staves`** are **inert** for the `.gp` output. A
  Guitar Pro file carries standard notation and tablature together and
  inseparably, so there is no notation-only or tablature-only mode to select;
  the flag and the key are accepted for compatibility but change nothing.

Everything else on this page — the subcommands, the session directory, the
draw, the log and its refusals — is renderer-agnostic.
