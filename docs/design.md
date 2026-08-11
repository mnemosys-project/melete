# Melete — Design Orientation

**This page is not the design.** The authoritative specification lives in the
`mnemosys-project/.github` repository and is amended as decisions are recorded.
This page exists only to orient a reader who arrived at the code first, and to
point at the documents that govern it. If something here disagrees with the
spec, the spec is correct and this page is stale.

## Table of Contents

- [What melete is](#what-melete-is)
- [Running it](#running-it)
- [Module layout](#module-layout)
- [What the design is made of](#what-the-design-is-made-of)
- [The two load-bearing boundaries](#the-two-load-bearing-boundaries)
- [The renderer boundary](#the-renderer-boundary)
- [The central invariant](#the-central-invariant)
- [The written-pitch convention](#the-written-pitch-convention)
- [Reference documents](#reference-documents)
- [Authoritative documents](#authoritative-documents)

## What melete is

Melete is a command-line tool that generates daily bass practice sheets. It
reads a configuration file describing an instrument and a pool of exercise
parameters, selects a small set of parameterized exercises with deliberate
variety, and engraves them into a single printable PDF per day containing both
standard notation and tablature.

The engraver is LilyPond today and is being replaced; see
[The renderer boundary](#the-renderer-boundary).

The success criterion is practical, not architectural: run one command each
morning and get a practice sheet good enough to hand to a bass instructor.

## Running it

`examples/config.toml` is the worked example from §10 of the spec. Copy it to
wherever you intend to run from — it is a starting point, not a file the tool
reads out of the repository.

Melete resolves both the configuration and the `sessions/` output directory
relative to the current working directory, so run experiments from `build/`
rather than the repository root. `build/` is gitignored, which keeps generated
sheets and session logs out of tracked space without ignoring them case by
case:

```bash
mkdir -p build && cd build && cp ../examples/config.toml .
melete generate
```

## Module layout

`[LP]` marks the two modules that know the renderer exists. Everything
unmarked is renderer-agnostic.

```text
src/melete/
  instrument.py         InstrumentProfile and fretboard queries
  score.py              The IR: Note, Tuplet, Voice, Score. Pure data.
  theory.py             Pitch, interval, scale and chord math, and the
                        §10a spelling model (Key, SpelledPitch)
  vocabulary.py         Canonical parameter identifiers and display names
  families/
    __init__.py         REGISTRY: family name -> generator function
    _shared.py          Parameter reading and direction ordering. Not
                        a family; decides nothing about exercises.
    scales.py           }
    arpeggios.py        }  One pure function per family:
    intervals.py        }  parameters -> Score
    chromatic.py        }
  rhythm.py             Cross-cutting modifier: Score -> Score
  selection.py          Coverage-aware sampling; ExerciseSpec, WeightInputs
  lilypond/
    emit.py       [LP]  Score -> LilyPond source text. Knows the syntax.
    render.py     [LP]  Adapter over the LilyPond binary. Knows the binary.
  session.py            Writes and reads sessions/YYYY-MM-DD/
  config.py             Loads and validates config.toml
  cli.py                Argument parsing; wires the pipeline
```

The pipeline runs left to right through those modules: config selects an
exercise, a family generates a `Score`, the rhythm modifier rewrites it, the
emitter turns it into renderer source text, and the renderer produces the PDF.
Only the last two stages name a renderer.

## What the design is made of

Five pieces do the work. All five are renderer-agnostic; the spec section
against each one is authoritative.

**The spelling model (§10a).** A note's letter and accidental are decided from
the key, not from the semitone: `theory.spell` returns a `SpelledPitch` —
letter, alteration, octave — and the octave is the *letter's*, which differs
from the pitch's whenever a spelling crosses C (C♭, B♯). This is the part of
the design that took the most effort and the part most certain to outlive the
renderer.

**The Score IR (§6).** `Note`, `Tuplet`, `Voice`, `Score` — pure data, one
level of tuplet nesting, and durations stored as **written** values so a
triplet eighth is `1/8` inside a `3/2` tuplet rather than an unwritable `1/12`.

**The four families (§7).** Scales, arpeggios, intervals and chromatic
permutations, each a pure function from parameters to a `Score`, registered in
`families.REGISTRY`.

**Coverage-aware selection (§9).** The selector weights candidate exercises by
what has been practised recently, gates them for validity, and is deterministic
under a seed.

**The session log and replay (§9, §12).** Every generated day writes a
`session.json` recording the `WeightInputs` and the chosen specs, which is what
makes `melete replay` reproduce a past sheet exactly.

## The two load-bearing boundaries

Two boundaries carry the structure. Understand these before changing anything.

**`score.py` is the seam.** Families produce a `Score`; the emitter consumes
one. Neither imports the other. A family never learns that LilyPond exists; the
emitter never learns what a Dorian mode is. Every family is therefore a pure
function, testable without rendering anything.

**`lilypond/` is the blast door.** Two modules, and the split between them is
what the name is about: `render.py` is the only module aware that a LilyPond
*binary* exists, and `emit.py` is the only module that knows LilyPond *syntax*.
If the LilyPond **distribution** changes, exactly one file changes — that was
paid out once, when the PyPI redistribution turned out to have no aarch64 wheel
and the binary moved to `PATH`, at a cost of one line of `pyproject.toml` and no
application code. A change of **renderer** is wider: it is both modules and
their golden files. See below.

## The renderer boundary

Melete engraves through LilyPond and **that renderer is being replaced.** The
evaluation is
[`melete#71`](https://github.com/mnemosys-project/melete/issues/71) — what
LilyPond cost, where it falls short, and what a successor must do. Engraving
quality was never the problem. The alternatives surveyed are in
[`docs/reports/`](reports/).

None of the LilyPond material in this repository is deprecated. It is the
record of what was learned about engraving from this IR, and it is the
migration's input.

**Renderer-specific — the whole of it:**

- `src/melete/lilypond/emit.py` — the LilyPond syntax, including the
  `\tabFullNotation` branch and the written-pitch convention below
- `src/melete/lilypond/render.py` — the binary, its invocation and its
  failure modes
- `tests/lilypond/golden/*.ly` — the four golden files, and golden-file
  comparison as the verification strategy
- LilyPond as a system prerequisite: `vergil.toml`'s `system-packages`, the
  `bundled-lilypond` extra, and the `integration` pytest marker

**Everything else survives**, which is nearly the whole codebase: `theory`
including the entire spelling model, `instrument` and the fretboard model,
`score` and the IR, all four families, `rhythm`, `selection`, `config`,
`session`, and the CLI apart from wiring. `melete#71` measures the
renderer-specific part at roughly 210 statements.

It survives because `SpelledPitch` is notation-neutral by construction — a
letter, an alteration and an octave, with no LilyPond in it — and the IR
carries no renderer at all. Any successor that accepts a spelled pitch rather
than an integer inherits the spelling model intact.

The authoritative statement of this boundary, in both directions and with the
specification section for each element, is epic #1's spec §4, *The renderer
boundary*. This section is the local on-ramp; the spec is correct where the two
disagree.

## The central invariant

A note stores both what is played and where it is played. Those two facts must
agree:

```text
note.pitch == instrument.tuning[note.string] + note.fret
```

Every family test asserts this for every generated note. It is why the fretboard
model looks the way it does: position is musical information decided by the
family, not a rendering detail derived later.

`note.pitch` is the **sounding** pitch, everywhere in the IR. That is
renderer-agnostic and is not negotiable.

## The written-pitch convention

Renderer-specific, one owner, and worth knowing before you touch `emit.py`.

Bass guitar is written an octave above its sound. Melete owns that octave: the
emitter writes the **printed** pitch — `note.pitch` plus twelve — under a
**plain** `\clef "bass"` or `\clef "treble"`. The notes and the `stringTunings`
chord are transposed together and must always move together, because LilyPond
derives each fret number from the pitch against the declared tuning.

The clef must therefore not transpose as well. `\clef "bass_8"` does not
*describe* an octave already applied, it *performs* one. Melete transposed and
octavated for the whole of Phase B, so every exercise engraved two octaves above
its sound while the tablature stayed correct. Over 2,700 tests at 100% branch
coverage passed over it, because the tests assert the emitted text and the
emitted text was exactly what was intended. It was found by rendering a sheet
and looking at it (`melete#58`, fixed in `melete#66`).

The alternative — emit sounding pitch and let an octavated clef do the work —
is a defensible convention and a successor renderer may expect it; LilyPond's
own `bass-six-string-tuning` is defined that way.
[`melete#69`](https://github.com/mnemosys-project/melete/issues/69) records it
and why it was closed unbuilt. Until a renderer changes, the convention here is
the printed pitch, and `emit.py`'s module docstring is where it is specified.

## Reference documents

- [cli.md](cli.md) — every subcommand and flag, what each writes and what
  each refuses.
- [configuration.md](configuration.md) — every section and key of
  `config.toml`, with defaults and accepted values.
- [repository-standards.md](repository-standards.md) — repository profile,
  toolchain, the checks that must pass, and the deliberate departures from
  the Vergil default.
- [reports/](reports/) — research findings. The renderer question is an open
  one only here: the notation display targets and viability survey, the
  LilyPond/Guitar Pro annotation gap, and the Guitar Pro 8 generation
  feasibility study.
- [`melete#71`](https://github.com/mnemosys-project/melete/issues/71) — the
  LilyPond evaluation. Not a file in this repository, but it is the reason
  the renderer boundary above is marked at all.

## Authoritative documents

All of these live in `mnemosys-project/.github`, not here.

- [Specification](https://github.com/mnemosys-project/.github/blob/develop/epics/1-org-bootstrap-melete-v1/spec.md)
  — the design. Authoritative. §4, *The renderer boundary*, states in both
  directions which parts of the design outlive LilyPond; decisions #39 and #41
  cover the written-pitch convention and the marking of the boundary.
- [Implementation plan](https://github.com/mnemosys-project/.github/blob/develop/epics/1-org-bootstrap-melete-v1/plan.md)
  — how the spec is being built, task by task.
- [Epic #1](https://github.com/mnemosys-project/.github/issues/1)
  — the tracking issue and its task list.
- [Naming convention](https://github.com/mnemosys-project/.github/blob/develop/NAMING.md)
  — why the tool is called melete, and how future tools are named.
