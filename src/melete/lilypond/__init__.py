"""Everything that knows LilyPond exists.

Two modules, and the split between them is the point:

    emit     Score -> LilyPond source text. Pure; tested on the text.
    render   source text -> PDF. The only module aware of the binary.

This package is the blast door (spec §4), and the name is narrower than it
sounds. `render` isolates the **binary**: if the LilyPond distribution changes,
exactly one file changes — as it did when the PyPI redistribution turned out to
have no aarch64 wheel and the binary moved to `PATH` (decision #23), which cost
one line of `pyproject.toml` and no application code at all.

`emit` isolates the **syntax**, and it is the larger of the two. A change of
*renderer* is therefore both modules and all four golden `.ly` files —
roughly 210 statements, measured in melete#71 — not the one-file swap "blast
door" suggests. Everything outside this package is renderer-agnostic, which is
what the boundary bought. See spec §4, *The renderer boundary*.
"""
