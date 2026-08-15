"""Tests for the realization pipeline (spec §4, §7, #118).

`pipeline.realize` is the seam that composes the three renderer-agnostic stages —
family, layout fitter, rhythm modifier — into one laid-out `Score`. The property
that matters here is the one the fitter exists to guarantee: a realized exercise
**tiles into whole measures**, with no short final bar, because the meter and
subdivision are derived from the note count rather than sampled (#118). The other
half is that the sampled `subdivision` and `time_signature` axes no longer reach
the page — the fitter overrides them — which is what makes this the integration
task that retires sampling as the driver of rhythm.
"""

from __future__ import annotations

from fractions import Fraction
from random import Random

from melete import pipeline
from melete.config import load_string
from melete.families import REGISTRY
from melete.instrument import PROFILES
from melete.score import Attack, Hand, bar, notes, sounding_duration
from melete.selection import select

BASS6 = PROFILES["bass6"]

#: All four families declared with §10-shaped pools, two exercises each, so one
#: draw exercises every family the way `generate` does. The rhythm pool still
#: carries `subdivisions` and `time_signatures` — the selector samples them, and
#: the point of #118 is that the fitter overrides both, so they must be present
#: to prove they are ignored.
CONFIG = """\
[instrument]
profile = "bass6"

[session]
shape = { chromatic = 2, scales = 2, arpeggios = 2, intervals = 2 }

[pool.chromatic]
permutations = [[1, 2, 3, 4], [1, 3, 2, 4], [2, 1, 4, 3], [4, 3, 2, 1]]
start_strings = [0, 1, 2]
start_frets = [1, 3, 5, 7]
string_traversals = ["adjacent"]
shifts = ["none", "fret_per_cycle"]
spans = [3, 4]

[pool.scales]
roots = "all"
scale_types = ["ionian", "dorian", "phrygian", "lydian", "mixolydian", "aeolian"]
traversals = ["positional"]
patterns = ["straight", "thirds", "groups_of_3"]

[pool.arpeggios]
roots = "all"
qualities = ["maj", "min", "maj7", "min7", "dom7"]
inversions = ["root", "first", "second"]
patterns = ["straight", "broken"]

[pool.intervals]
intervals = [3, 4, 5, 6]
contexts = ["chromatic", "diatonic"]
roots = "all"
scale_types = ["ionian", "dorian", "aeolian"]
string_skips = ["0", "1"]
patterns = ["ascending_pairs", "descending_pairs", "alternating"]

[pool.rhythm]
accent_patterns = ["none", "every_3"]
note_value_patterns = ["straight", "long_short"]
"""

#: One realizable `scales` specification, for the ignored-legacy-key test: a
#: positional A Dorian journey. The retired rhythm keys are set per-test so the
#: two params differ only in the keys #118 makes irrelevant and #119 has since
#: retired.
SCALES_SPEC: dict[str, object] = {
    "root": 33,
    "scale_type": "dorian",
    "traversal": "positional",
    "pattern": "straight",
    "accent_pattern": "none",
    "note_value_pattern": "straight",
}


def test_every_realized_exercise_tiles_into_whole_measures() -> None:
    """Spec §7: no partial measure. The last bar is full, across every family."""
    config = load_string(CONFIG)
    picks = select(config, [], Random(0))  # noqa: S311 - reproducibility (§9)

    families_seen = set()
    for spec, _inputs in picks:
        score, plan = pipeline.realize(config.instrument, spec.family, spec.params)
        families_seen.add(spec.family)

        measures = bar(score.voice, score.time_signature)
        beats, beat_value = score.time_signature
        capacity = beats * Fraction(1, beat_value)
        # The last measure is full: the voice tiles exactly, with no short bar.
        assert sounding_duration(measures[-1].voice) == capacity

        assert score.time_signature == plan.time_signature
        assert score.repeat is True
        assert "layout_trace" in score.params

    assert families_seen == set(REGISTRY)


def test_the_fitter_derives_a_quarter_denominated_meter() -> None:
    """Spec §4.1: the fitter fills a beat with the subdivision, so the meter is /4."""
    config = load_string(CONFIG)

    for spec, _inputs in select(config, [], Random(1)):  # noqa: S311 - §9
        score, _plan = pipeline.realize(config.instrument, spec.family, spec.params)
        assert score.time_signature[1] == 4


#: A two-hand tapped triad (spec §6, epic #67): E minor rooted low on the bass,
#: with room for the box. The retired rhythm keys are supplied so the pipeline
#: exercises the same shape a real draw would.
TAPPED_TRIAD: dict[str, object] = {
    "root": 28,
    "quality": "min",
    "inversion": "root",
    "pattern": "straight",
    "accent_pattern": "none",
    "note_value_pattern": "straight",
}


def _no_slur_is_stranded(voice) -> bool:  # noqa: ANN001 - a Voice
    """Every SLURRED note has an open same-string+same-hand TAPPED run ahead of it.

    The post-fitter guarantee (spec §3): legato runs last, so a slur is never
    left without the tapped attack that begins its run — even after a lever
    repeated or dropped notes.
    """
    open_run: tuple[int, Hand] | None = None
    for note in notes(voice):
        key = (note.string, note.hand)
        if note.attack is Attack.SLURRED:
            if open_run != key:
                return False
        elif note.attack is Attack.TAPPED:
            open_run = key
        else:
            open_run = None
    return True


def test_a_tapped_triad_realizes_two_handed_and_the_legato_is_a_noop() -> None:
    """Spec §6: the triad default taps every note, so the wired legato pass is a no-op."""
    score, _plan = pipeline.realize(BASS6, "arpeggios", TAPPED_TRIAD)
    played = list(notes(score.voice))

    assert {note.hand for note in played} == {Hand.LEFT, Hand.RIGHT}
    assert all(note.attack is Attack.TAPPED for note in played)
    assert _no_slur_is_stranded(score.voice)


def test_the_post_fitter_legato_strands_no_slur_when_it_fires() -> None:
    """Spec §3: run after the fitter, legato leaves a correct first-TAPPED-per-run.

    `numeric_1353` repeats a chord tone on the same string and hand, so the
    legato pass does fire here (unlike the straight default). It runs on the
    already-tiled voice, so every slur it derives still has its tapped attack
    ahead of it — no slur is stranded by a note the fitter repeated or dropped.
    """
    score, _plan = pipeline.realize(BASS6, "arpeggios", {**TAPPED_TRIAD, "pattern": "numeric_1353"})
    played = list(notes(score.voice))

    assert any(note.attack is Attack.SLURRED for note in played)  # the pass fired
    assert _no_slur_is_stranded(score.voice)


def test_a_seventh_stays_one_handed_and_plucked_through_the_pipeline() -> None:
    """The untapped path is unchanged: a seventh realizes all-plucked, one hand."""
    spec = {**TAPPED_TRIAD, "root": 33, "quality": "min7"}
    score, _plan = pipeline.realize(BASS6, "arpeggios", spec)
    played = list(notes(score.voice))

    assert all(note.attack is Attack.PLUCKED for note in played)
    assert all(note.hand is Hand.LEFT for note in played)


def test_a_stray_subdivision_or_meter_key_does_not_reach_the_page() -> None:
    """#118/#119: the fitter drives meter and subdivision; stray keys are ignored.

    `subdivision` and `time_signature` are no longer sampled axes (#119), but a
    hand-edited or pre-#119 `session.json` replayed through the pipeline may
    still carry them. Two params that differ *only* in those retired keys realize
    to the identical Score — same voice, same meter — because the fitter derives
    both (#118). If a stray key still drove the rhythm, the two voices would differ.
    """
    fast = pipeline.realize(
        BASS6, "scales", {**SCALES_SPEC, "subdivision": "sixteenth", "time_signature": "3_4"}
    )[0]
    slow = pipeline.realize(
        BASS6, "scales", {**SCALES_SPEC, "subdivision": "triplet_eighth", "time_signature": "4_4"}
    )[0]

    assert fast.time_signature == slow.time_signature
    assert fast.voice == slow.voice
    assert fast.time_signature[1] == 4
