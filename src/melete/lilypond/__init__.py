"""Everything that knows LilyPond exists.

Two modules, and the split between them is the point:

    emit     Score -> LilyPond source text. Pure; tested on the text.
    render   source text -> PDF. The only module aware of the binary.

`render` is the blast door (spec §4). If the LilyPond distribution changes,
exactly one file changes — as it did when the PyPI redistribution turned out to
have no aarch64 wheel and the binary moved to `PATH` (decision #23), which cost
one line of `pyproject.toml` and no application code at all.
"""
