# Melete — Design Orientation

**This page is not the design.** The authoritative specification lives in the
`mnemosys-project/.github` repository and is amended as decisions are recorded.
This page exists only to orient a reader who arrived at the code first, and to
point at the documents that govern it. If something here disagrees with the
spec, the spec is correct and this page is stale.

## Table of Contents

- [What melete is](#what-melete-is)
- [Module layout](#module-layout)
- [The two load-bearing boundaries](#the-two-load-bearing-boundaries)
- [The central invariant](#the-central-invariant)
- [Authoritative documents](#authoritative-documents)

## What melete is

Melete is a command-line tool that generates daily bass practice sheets. It
reads a configuration file describing an instrument and a pool of exercise
parameters, selects a small set of parameterized exercises with deliberate
variety, and renders them through LilyPond into a single printable PDF per day
containing both standard notation and tablature.

The success criterion is practical, not architectural: run one command each
morning and get a practice sheet good enough to hand to a bass instructor.

## Module layout

```text
src/melete/
  instrument.py    InstrumentProfile and fretboard queries
  score.py         The IR: Note, Tuplet, Voice, Score. Pure data.
  theory.py        Pitch, interval, scale, and chord math (12-TET integers)
  vocabulary.py    Canonical parameter identifiers and their display names
  families/        One module per exercise family, plus the registry
  rhythm.py        Cross-cutting modifier: Score -> Score
  selection.py     Coverage-aware sampling; ExerciseSpec and WeightInputs
  lilypond/
    emit.py        Score -> LilyPond source text
    render.py      Adapter over the LilyPond binary
  session.py       Writes and reads sessions/YYYY-MM-DD/
  config.py        Loads and validates config.toml
  cli.py           Argument parsing; wires the pipeline
```

The pipeline runs left to right through those modules: config selects an
exercise, a family generates a `Score`, the rhythm modifier rewrites it, the
emitter turns it into LilyPond source, and the renderer produces the PDF.

## The two load-bearing boundaries

Two boundaries carry the structure. Understand these before changing anything.

**`score.py` is the seam.** Families produce a `Score`; the emitter consumes
one. Neither imports the other. A family never learns that LilyPond exists; the
emitter never learns what a Dorian mode is. Every family is therefore a pure
function, testable without rendering anything.

**`lilypond/render.py` is the blast door.** It is the only module aware that a
LilyPond binary exists. If the LilyPond distribution changes, exactly one file
changes.

## The central invariant

A note stores both what is played and where it is played. Those two facts must
agree:

```text
note.pitch == instrument.tuning[note.string] + note.fret
```

Every family test asserts this for every generated note. It is why the fretboard
model looks the way it does: position is musical information decided by the
family, not a rendering detail derived later.

## Authoritative documents

All of these live in `mnemosys-project/.github`, not here.

- [Specification](https://github.com/mnemosys-project/.github/blob/develop/epics/1-org-bootstrap-melete-v1/spec.md)
  — the design. Authoritative.
- [Implementation plan](https://github.com/mnemosys-project/.github/blob/develop/epics/1-org-bootstrap-melete-v1/plan.md)
  — how the spec is being built, task by task.
- [Epic #1](https://github.com/mnemosys-project/.github/issues/1)
  — the tracking issue and its task list.
- [Naming convention](https://github.com/mnemosys-project/.github/blob/develop/NAMING.md)
  — why the tool is called melete, and how future tools are named.
