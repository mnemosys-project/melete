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
variety, and renders them into a single Guitar Pro file per day containing both
standard notation and tablature.

The renderer is alphaTab: melete emits alphaTex and renders a Guitar Pro `.gp`
through the vendored `melete-render` Node tool; see
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

`[AT]` marks the two modules that know the renderer exists. Everything
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
    _shared.py          Parameter reading, direction ordering, and the
                        one-hand `box` placement primitive. Not a family;
                        decides nothing about exercises.
    journey.py          The coherent up-and-down journey: places a pitch run
                        outer string to opposite outer string (boxed_span,
                        per_string) and plays it up and back (updown).
    arpeggio_shapes.py  Canonical per-quality seed shapes and their
                        derivation (provisional, instructor-validated).
    scales.py           }
    arpeggios.py        }  One pure function per family:
    intervals.py        }  parameters -> (Score, LayoutHints)
    chromatic.py        }
  layout.py             The layout fitter: LayoutHints + note count -> a
                        whole-bar (subdivision, time signature, bars) plan
  rhythm.py             Cross-cutting modifier: restamps a Voice's durations,
                        tuplets and accents at the fitter's subdivision
  pipeline.py           realize(): family -> fitter -> restamp, one laid-out Score
  selection.py          Coverage-aware sampling; ExerciseSpec, WeightInputs
  alphatab/
    emit.py       [AT]  Score -> alphaTex source text. Knows the syntax.
    render.py     [AT]  Adapter over the melete-render Node tool. Knows the binary.
  session.py            Writes and reads sessions/YYYY-MM-DD/
  config.py             Loads and validates config.toml
  cli.py                Argument parsing; wires the pipeline
```

The pipeline runs left to right through those modules: config selects an
exercise; a family generates a `Score` and the `LayoutHints` that travel with
it; the layout fitter derives a subdivision, time signature and bar count under
which the notes tile into whole, complete measures, wrapped in repeat barlines;
the rhythm modifier restamps the voice's durations, tuplets and accents at that
subdivision; `pipeline.realize` is the one place those three renderer-agnostic
stages are wired together into a single laid-out `Score`; the emitter turns it
into alphaTex source text — wrapping each exercise into even, roughly four-bar
systems so no exercise is engraved as a lonely one-bar line; and the renderer
produces the Guitar Pro `.gp`. Only the last two stages name a renderer.

## What the design is made of

Six pieces do the work. All six are renderer-agnostic; the spec section
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
A `Score` also carries a `repeat` flag (§5): a renderer-agnostic intent that
the exercise plays twice, which the emitter draws as repeat barlines.

**The four families (§7).** Scales, arpeggios, intervals and chromatic
permutations, each a pure function from parameters to a `Score` and the
`LayoutHints` the fitter needs, registered in `families.REGISTRY`. Every family
now realizes **one coherent up-and-down journey** (§5): anchored at the root on
the lowest string, it traverses outer string to opposite outer string under the
chosen fingering style and returns as the exact retrograde. The geometry is
**computed, not sampled** — direction is always up-and-down, string coverage is
the whole instrument, and the octave count is *emergent* rather than a target.
The old sampled `direction`, `string_set` and `range_octaves` axes were retired
with that model (epic #72); `families/journey.py` and the `box` primitive
compute the placement those axes used to name. `scales` keeps the `traversal`
axis as a fingering style (positional or three-note-per-string); `arpeggios`
drop it, laying every quality out from a canonical seed shape.

**The layout fitter (§4, §5).** A family emits a `Score` plus `LayoutHints` —
a cell size, a seam, and the note-count levers that are musically legal here —
and the fitter (`layout.py`) derives the (subdivision, time signature, bar
count) under which the note count tiles into whole, complete measures, never a
partial bar, wrapped in repeat barlines. It ranks meters by a priority ladder —
a whitelisted beats-per-bar, an even bar count, then seam alignment — and
engages a single cell-granular lever (repeat or omit the apex, add or drop a
whole cell) only when a clean fit needs one, recording a legibility trace for
why the chosen meter won. `2/4` is demoted to a strict last resort: any non-2
fit — even one that burns a lever — outranks it, so `2/4` wins only when every
reachable fit is `2/4` (the genuinely one-beat drill). `pipeline.realize` wires it between the family and the
rhythm modifier.

**Coverage-aware selection (§9).** The selector weights candidate exercises by
what has been practised recently, gates them for validity, and is deterministic
under a seed.

**The session log and replay (§9, §12).** Every generated day writes a
`session.json` recording the `WeightInputs` and the chosen specs, which is what
makes `melete replay` reproduce a past sheet exactly.

## The two load-bearing boundaries

Two boundaries carry the structure. Understand these before changing anything.

**`score.py` is the seam.** Families produce a `Score`; the emitter consumes
one. Neither imports the other. A family never learns that alphaTab exists; the
emitter never learns what a Dorian mode is. Every family is therefore a pure
function, testable without rendering anything.

**`alphatab/` is the blast door.** Two modules, and the split between them is
what the name is about: `render.py` is the only module aware that a renderer
*binary* (Node, driving melete-render) exists, and `emit.py` is the only module
that knows alphaTex *syntax*. If the way the renderer is invoked changes, exactly
one file changes. A change of **renderer** is wider: it is both modules and their
golden files. See below.

## The renderer boundary

Melete renders through alphaTab: the emitter produces alphaTex and the renderer
drives the vendored `melete-render` Node tool to write a Guitar Pro `.gp`. This
is the successor to the original LilyPond pipeline, whose evaluation is
[`melete#71`](https://github.com/mnemosys-project/melete/issues/71) — what
LilyPond cost, where it fell short, and what a successor had to do. Engraving
quality was never the problem. The alternatives surveyed are in
[`docs/reports/`](reports/).

The v1 LilyPond pipeline was removed in epic #46, Task 10; it last rendered at
commit `a2b26cb` (2026-08-12), the parent of the removal commit — a reference
pointer in git history, not a restorable artifact.

**Renderer-specific — the whole of it:**

- `src/melete/alphatab/emit.py` — the alphaTex syntax, including the positional
  `<fret>.<string>` notes and the written-pitch handling below
- `src/melete/alphatab/render.py` — the Node binary and the melete-render tool,
  their invocation and their failure modes
- `tests/alphatab/` — the emitter and renderer tests and the `golden/*.atex`
  fixtures they compare against
- alphaTab as a prerequisite: `vergil.toml`'s `[container].build-command`
  installs `@coderline/alphatab`, and Node is an environment prerequisite

**Everything else survives**, which is nearly the whole codebase: `theory`
including the entire spelling model, `instrument` and the fretboard model,
`score` and the IR, all four families, `rhythm`, `selection`, `config`,
`session`, and the CLI apart from wiring.

It survives because `SpelledPitch` is notation-neutral by construction — a
letter, an alteration and an octave, with no renderer in it — and the IR carries
no renderer at all. alphaTab accepts a spelled pitch rather than an integer, so
it inherited the spelling model intact.

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

Renderer-specific, one owner, and worth knowing before you touch
`alphatab/emit.py`.

The alphaTab emitter writes **positional** notes: a beat is `<fret>.<string>`,
and alphaTab derives the sounding pitch from the declared tuning and fret. There
is therefore no octave transposition to apply in the emitter — the tuning melete
declares is sounding pitch, and the notation shows sounding pitch directly on a
plain `\clef bass` (the spike's human-reviewed decision; see `emit.py`'s module
docstring). The `.gp` diverges from the old v1 `.pdf` on octave *display* only.

This is a deliberate departure from the v1 LilyPond convention, kept here as
design history. LilyPond derived each fret from the *written* pitch, so melete
wrote the printed pitch — `note.pitch` plus twelve — under a plain
`\clef "bass"`, transposing the notes and the `stringTunings` chord together. An
octavating clef would have double-applied the shift: melete transposed *and*
octavated for the whole of Phase B, engraving every exercise two octaves above
its sound while the tablature stayed correct, and over 2,700 tests at 100% branch
coverage passed over it because they asserted the emitted text and the emitted
text was exactly what was intended. It was found by rendering a sheet and looking
at it (`melete#58`, fixed in `melete#66`), and
[`melete#69`](https://github.com/mnemosys-project/melete/issues/69) records the
sounding-pitch alternative that alphaTab now realises.

## Reference documents

- [cli.md](cli.md) — every subcommand and flag, what each writes and what
  each refuses.
- [configuration.md](configuration.md) — every section and key of
  `config.toml`, with defaults and accepted values.
- [repository-standards.md](repository-standards.md) — repository profile,
  toolchain, the checks that must pass, and the deliberate departures from
  the Vergil default.
- [reports/](reports/) — the research findings behind the renderer decision:
  the notation display targets and viability survey, the LilyPond/Guitar Pro
  annotation gap, and the Guitar Pro 8 generation feasibility study.
- [`melete#71`](https://github.com/mnemosys-project/melete/issues/71) — the
  LilyPond evaluation. Not a file in this repository, but it is why the
  renderer boundary exists and why the migration to alphaTab was made.

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
