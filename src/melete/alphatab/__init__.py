"""The alphaTab output surface: the alphaTex emitter and the renderer blast door.

`emit` turns a `Score` into alphaTex text; `render` is the only module that
learns a renderer binary (Node, driving melete-render) exists. This package is
melete's renderer half: it succeeded the original `melete.lilypond` package,
which was removed once the migration landed (melete#71, epic #46). See
docs/design.md, *The renderer boundary*.
"""
