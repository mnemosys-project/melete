"""Package marker for the alphaTab tests.

`test_render.py` shares its basename with `tests/lilypond/test_render.py` — the
adapter under test is the alphaTab mirror of the LilyPond one, so the mirrored
name is deliberate. Under pytest's default (prepend) import mode two test
modules may not share a basename unless one of them is inside a package, so this
marker qualifies the alphaTab tests as `alphatab.*` and keeps the LilyPond suite
untouched.
"""
