"""The alphaTab output surface: the alphaTex emitter and (later) the blast door.

This package is the alphaTab counterpart of `melete.lilypond`. `emit` turns a
`Score` into alphaTex text; `render` is the only module that learns a renderer
binary (Node, driving melete-render) exists. The renderer is being replaced —
see melete#71 and epic #46 — and this package is its replacement's Python half.
"""
