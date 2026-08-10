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
    lilypond/    emit (Score -> text) and render (the binary adapter)
    session      reads and writes sessions/YYYY-MM-DD/
    config       loads and validates config.toml
    cli          argument parsing; wires the pipeline

Two boundaries are load-bearing. `score` is the seam: families produce a
Score and the emitter consumes one, and neither imports the other.
`lilypond.render` is the blast door: the only module aware that a LilyPond
binary exists.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
