"""Melete — parameterized bass practice exercise generation.

The organization is named for memory; each tool under it is named for a Muse.
Melete (Μελέτη, MEL-uh-tee) is deliberate practice and study — recall under
constraint. See NAMING.md in mnemosys-project/.github.

Module layout (spec section 4):

    theory       pitch, interval, scale and chord math (12-TET integers)
    vocabulary   canonical parameter identifiers and display names
    instrument   InstrumentProfile and fretboard queries
    score        the IR: Note, Tuplet, Voice, Score. Pure data.
    families/    one pure function per exercise family
    rhythm       cross-cutting modifier: Score -> Score
    selection    coverage-aware sampling; ExerciseSpec, WeightInputs
    alphatab/    emit (Score -> alphaTex text) and render (the binary adapter)
    session      reads and writes sessions/YYYY-MM-DD/
    config       loads and validates config.toml
    cli          argument parsing; wires the pipeline

Two boundaries are load-bearing. `score` is the seam: families produce a
Score and the emitter consumes one, and neither imports the other.

The `alphatab` package is the blast door, and it is two modules rather than
one: `render` is the only module aware that a renderer *binary* (Node, driving
melete-render) exists, and `emit` is the only module that knows alphaTex
*syntax*. A change of how the renderer is invoked touches `render` alone; a
change of renderer touches both, plus their golden files. Every other module
here is renderer-agnostic. The renderer was migrated from LilyPond to alphaTab
(melete#71, epic #46) — see docs/design.md, *The renderer boundary*.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
