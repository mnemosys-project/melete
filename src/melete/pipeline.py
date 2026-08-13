"""The realization pipeline: family -> fitter -> restamp -> one laid-out Score.

Spec §4 runs three renderer-agnostic stages to turn a specification into an
engravable exercise: the *family* (§7) decides which notes and where, the layout
*fitter* (§4, `layout.py`) derives a meter and subdivision under which the note
count tiles into whole measures, and the rhythm *modifier* (§8, `rhythm.py`)
stamps the written durations, tuplet grouping and accents at that subdivision.

`realize` is the one place those three are wired together, so the two call sites
that need a fully laid-out Score — `cli._score` for the sheet, `selection._rejected`
for the validity gate — compose them the same way rather than each duplicating
the wiring. It is deliberately below both: it imports `families`, `layout`,
`rhythm` and `score`, and imports neither `cli` nor `selection`, so the selector
can route a draw through it without the import cycle that `cli -> selection`
already forbids the other way round.

## What `realize` decides, and what it leaves to the caller

The fitter's meter replaces the family's placeholder `time_signature`, the
exercise is wrapped in a repeat (§5) so the practice loop plays it twice, and the
fitter's human-readable trace is recorded in `params["layout_trace"]` — the
account of *why* this meter won, kept beside the exercise the way the family's
own axes are (§12). Everything else the family set — the key (§10a), the title,
the instruction, the notes' pitches and positions — is carried through by
`replace`.

The **tempo** is not decided here. §10's `[pool.<family>] tempo` override is a
fact only `cli` holds (it reads the configuration), and it is not a sampled axis,
so `realize` leaves `tempo_range` as the family set it and `cli._score` applies
the override on the Score it hands back (decision #20).
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from melete import layout, rhythm
from melete.families import REGISTRY

if TYPE_CHECKING:
    from melete.families import Params
    from melete.instrument import InstrumentProfile
    from melete.layout import LayoutPlan
    from melete.score import Score


def realize(profile: InstrumentProfile, family: str, params: Params) -> tuple[Score, LayoutPlan]:
    """Family -> fitter -> restamp: one fully-laid-out Score, plus its LayoutPlan.

    Sets the fitter's meter, wraps the exercise in a repeat, and records the
    legibility trace in `params["layout_trace"]`. The subdivision and meter are
    the fitter's (§4), not sampled axes (#118), so a `time_signature` or
    `subdivision` still travelling in `params` is ignored here. Tempo override
    stays with the CLI caller (§10).

    A `ValueError` from any stage — a family running off the neck, or the fitter
    finding no whole-bar fit — propagates unchanged, which is what lets the
    selector's validity gate treat both as one rejection reason (§9).
    """
    score, hints = REGISTRY[family].generate(profile, params)
    adjusted, plan = layout.plan_voice(score.voice, hints)
    voice = rhythm.restamp(
        adjusted,
        plan.subdivision,
        note_value_pattern=cast("str", params.get("note_value_pattern", "straight")),
        accent_pattern=cast("str", params.get("accent_pattern", "none")),
    )
    laid_out = replace(
        score,
        voice=voice,
        time_signature=plan.time_signature,
        repeat=True,
        params={**score.params, "layout_trace": plan.trace},
    )
    return laid_out, plan
