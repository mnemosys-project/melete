"""The exercise families (spec §7): one pure function per family.

A family is `generate(profile, params) -> Score` and nothing else. It has no
I/O, no randomness and no clock: the selector (§9) chooses the parameters and
the family realizes them, which is what makes a sheet reproducible from its
session log. Nothing here imports `selection` or `config`, and no family
imports another. `_shared` is the exception that proves it: it is not a family,
it decides nothing about what an exercise is, and it holds only the parameter
reading and `direction` ordering every family would otherwise write out again.

`REGISTRY` is the dispatch table those callers use. Keying it on the same
identifiers as `vocabulary.AXES["family"]` is what lets `config` validate a
pool section, `selection` draw a family, and `cli` list them without any of
the three keeping a private list of families that could drift from this one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from melete.families import arpeggios, chromatic, intervals, scales

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from melete.instrument import InstrumentProfile
    from melete.score import Score

#: One exercise specification: §7 axis identifiers and range values, plus
#: whatever §8's rhythm modifier travels alongside them. Deliberately loose —
#: each family validates the axes it reads, against `vocabulary` and against
#: the active profile.
type Params = Mapping[str, object]

#: The family contract. Every entry in `REGISTRY` has this shape.
type Generate = Callable[[InstrumentProfile, Params], Score]

#: Family identifier -> the pure function that realizes it. All four of §7's
#: families are here; `vocabulary.AXES["family"]` enumerates the same keys.
REGISTRY: dict[str, Generate] = {
    "chromatic": chromatic.generate,
    "scales": scales.generate,
    "arpeggios": arpeggios.generate,
    "intervals": intervals.generate,
}

__all__ = ["REGISTRY", "Generate", "Params"]
