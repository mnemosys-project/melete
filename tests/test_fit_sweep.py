"""§132 fit-rate sweep: every realizable (family, direction) tiles into whole bars.

Before this fix, whole classes of (family, direction) could not tile. A cell>1
`up_down` turned around at the *note* level and left a half-cell no `cell`-wide
meter could divide, and the single-note add/drop levers could not repair a prime
beat count (intervals' 13 chromatic pairs the standing example). This sweep is
the regression guard: it draws a representative grid of specifications for each
family, and asserts that every realizable draw both generates *and fits* —
`layout.plan_voice` returns a plan without raising.

A draw `generate` rejects is an over-constrained specification §9 resamples (a
scale off the neck, a traversal the string set cannot carry); it is skipped
rather than scored, because the fit rate is about the draws that *become*
exercises. The property under test is that once a specification is realizable the
fitter always tiles it — the §14 uniformity #132 restores. The expected rate is
therefore exactly 1.0 for every (family, direction), and any shortfall is a real
defect this test refuses to paper over.
"""

from __future__ import annotations

from itertools import product
from typing import TYPE_CHECKING

from melete import layout
from melete.families import REGISTRY
from melete.instrument import PROFILES

if TYPE_CHECKING:
    from collections.abc import Iterator

BASS6 = PROFILES["bass6"]
DIRECTIONS = ("up", "down", "up_down")


def _specs() -> Iterator[tuple[str, dict[str, object]]]:
    """A representative (family, params) grid, swept over every direction.

    The swept axes are the ones the #132 defect turned on: `direction` for every
    family, plus whatever moves the cell size and the beat count — `pattern` and
    `range_octaves` for the windowed families, `interval` and `context` for
    intervals (chromatic context is the 13-pair prime), `span` and
    `string_traversal` for chromatic (`single_string` forces the single-cell,
    one-beat edge). `root`/`start_*` are held at a known-realizable value; draws
    that still run off the neck are filtered by `generate` at the call site.
    """
    for scale_type, traversal, pattern, octaves, strings, direction in product(
        ("ionian", "major_pentatonic", "blues"),
        ("positional", "three_note_per_string"),
        ("straight", "thirds", "fourths", "groups_of_3", "groups_of_4", "numeric_1235"),
        (1, 2),
        ((0, 1, 2, 3, 4, 5), (2, 3, 4, 5), (0, 1, 2)),
        DIRECTIONS,
    ):
        params: dict[str, object] = {
            "root": 33,
            "scale_type": scale_type,
            "traversal": traversal,
            "string_set": strings,
            "pattern": pattern,
            "range_octaves": octaves,
            "direction": direction,
        }
        yield "scales", params

    for quality, inversion, traversal, pattern, octaves, strings, direction in product(
        ("maj7", "min7", "dom7", "min6"),
        ("root", "first", "second"),
        ("positional", "across_strings"),
        ("straight", "numeric_1353", "broken", "sweep_ordered"),
        (1, 2),
        ((0, 1, 2, 3), (2, 3, 4, 5)),
        DIRECTIONS,
    ):
        params = {
            "root": 33,
            "quality": quality,
            "inversion": inversion,
            "traversal": traversal,
            "string_set": strings,
            "pattern": pattern,
            "range_octaves": octaves,
            "direction": direction,
        }
        yield "arpeggios", params

    for interval, context, scale_type, skip, strings, pattern, direction in product(
        (3, 4, 5, 6),
        ("diatonic", "chromatic"),
        ("ionian", "aeolian"),
        ("0", "1"),
        ((0, 1, 2, 3), (1, 2, 3, 4), (0, 1, 2, 3, 4, 5)),
        ("ascending_pairs", "descending_pairs", "alternating"),
        DIRECTIONS,
    ):
        params = {
            "interval": interval,
            "context": context,
            "root": 33,
            "scale_type": scale_type,
            "string_skip": skip,
            "string_set": strings,
            "direction": direction,
            "pattern": pattern,
        }
        yield "intervals", params

    for permutation, traversal, shift, span, direction in product(
        ((1, 2, 3, 4), (1, 3, 2, 4)),
        ("adjacent", "skip_1", "single_string"),
        ("none", "fret_per_cycle", "position_per_cycle"),
        (1, 3, 4),
        DIRECTIONS,
    ):
        params = {
            "permutation": permutation,
            "start_string": 0,
            "start_fret": 5,
            "direction": direction,
            "string_traversal": traversal,
            "shift": shift,
            "span": span,
        }
        yield "chromatic", params


def _sweep() -> tuple[dict[tuple[str, str], tuple[int, int]], list[str]]:
    """Fit outcomes per (family, direction), and the specs whose fit raised.

    Returns a `{(family, direction): (fit_ok, drawn)}` tally and a list of the
    realizable draws whose `plan_voice` raised — the fit failures the assertion
    forbids. A draw `generate` rejects is not realizable and is not tallied.
    """
    tally: dict[tuple[str, str], list[int]] = {}
    failures: list[str] = []
    for family, params in _specs():
        direction = str(params["direction"])
        try:
            score, hints = REGISTRY[family].generate(BASS6, params)
        except ValueError:
            continue  # over-constrained draw; §9 resamples it, not a fit failure.
        cell = tally.setdefault((family, direction), [0, 0])
        cell[1] += 1
        try:
            layout.plan_voice(score.voice, hints)
        except ValueError as error:
            failures.append(f"{family}/{direction} {params}: {error}")
            continue
        cell[0] += 1
    return {key: (ok, drawn) for key, (ok, drawn) in tally.items()}, failures


def test_every_realizable_family_direction_tiles() -> None:
    rates, failures = _sweep()

    # Every (family, direction) the grid reaches must have been drawn at least
    # once, or the sweep is not exercising it and the 1.0 below is vacuous.
    for family in REGISTRY:
        for direction in DIRECTIONS:
            assert (family, direction) in rates, f"{family}/{direction} drew no realizable spec"

    # The property #132 restores: once realizable, every draw fits (rate 1.0).
    imperfect = {key: (ok, drawn) for key, (ok, drawn) in rates.items() if ok != drawn}
    assert not failures, "fit raised on realizable draws:\n" + "\n".join(failures[:10])
    assert not imperfect, f"fit rate below 1.0 for {imperfect}"
