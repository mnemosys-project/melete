"""The exercise families (spec §7): one pure function per family.

A family is `generate(profile, params) -> (Score, LayoutHints)` and nothing else. It has no
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

## Why the entries are records rather than functions

A family is more than its function to the modules around it. `config` needs the
tempo range §7 assigns to the *family* (decision #20) to default
`[pool.<family>] tempo`, and it needs the axes the family reads to know which
pool keys that section accepts. Both were held elsewhere and both drifted:
`config.DEFAULT_TEMPO` disagreed with three of the four families about tempo,
and its axis table omitted two of `intervals`' axes, which made every
`intervals` specification the selector could draw an invalid one.

`Family` is the fix, and the shape was chosen for what it costs to add the
fifth family: one line of `REGISTRY`, naming the module three times, and
nothing anywhere else. A parallel `TEMPO` lookup beside `REGISTRY` would have
been a second line to add and a second one to forget, which is the failure this
module is repairing rather than a shape to repeat.

Every field is a *reference* to the family module's own declaration, never a
copy of it. The family still owns the numbers and the axis list; this is only
where a caller that does not import the family module reaches them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from melete.families import arpeggios, chromatic, intervals, scales

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from melete.instrument import InstrumentProfile
    from melete.layout import LayoutHints
    from melete.score import Score

#: One exercise specification: §7 axis identifiers and range values, plus
#: whatever §8's rhythm modifier travels alongside them. Deliberately loose —
#: each family validates the axes it reads, against `vocabulary` and against
#: the active profile.
type Params = Mapping[str, object]

#: The family contract. Every `Family.generate` has this shape: a family realizes
#: a `Score` and, alongside it, the §4.2 `LayoutHints` the fitter needs — the two
#: are one return because neither is derivable from the other after the fact.
type Generate = Callable[[InstrumentProfile, Params], tuple[Score, LayoutHints]]


@dataclass(frozen=True)
class Family:
    """One family, as the modules that do not import it see it (§7)."""

    #: The pure function that realizes an exercise: `generate(profile, params)`.
    generate: Generate
    #: Every axis the family reads, in the order §7's table lists them. This is
    #: what `config` builds a `[pool.<family>]` section from and what `selection`
    #: must supply, so it is the family's declaration and not a restatement.
    axes: tuple[str, ...]
    #: §7's tempo range for this family, in beats per minute, slowest to
    #: fastest. A default the user overrides in `[pool.<family>] tempo`, never a
    #: sampled axis (decision #20).
    default_tempo_range: tuple[int, int]


#: Family identifier -> the record that describes it. All four of §7's families
#: are here; `vocabulary.AXES["family"]` enumerates the same keys.
REGISTRY: dict[str, Family] = {
    "chromatic": Family(chromatic.generate, chromatic.AXES, chromatic.DEFAULT_TEMPO_RANGE),
    "scales": Family(scales.generate, scales.AXES, scales.DEFAULT_TEMPO_RANGE),
    "arpeggios": Family(arpeggios.generate, arpeggios.AXES, arpeggios.DEFAULT_TEMPO_RANGE),
    "intervals": Family(intervals.generate, intervals.AXES, intervals.DEFAULT_TEMPO_RANGE),
}

__all__ = ["REGISTRY", "Family", "Generate", "Params"]
