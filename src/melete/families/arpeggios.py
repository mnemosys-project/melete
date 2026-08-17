"""`arpeggios` — chord tones (spec §6, §7, MNEMOSYS A1, A2).

`generate` is a pure function: no I/O, no randomness, no clock. The selector
(§9) chooses the parameters and this module realizes them, which is what makes
a sheet reproducible from its session log and this family testable without any
of the machinery around it. It therefore imports neither `selection` nor
`config`.

## What one exercise is

One exercise is the chord's up-and-down *journey* across the instrument (spec
§5): the tones ascend from the root on the lowest string, laid out by the
quality's canonical seed shape, until the shape reaches the opposite outer
string, and then return without replaying the turnaround. Extent and octave
count are emergent — they fall out of reaching the top string — rather than a
sampled target, exactly as `scales` and every other family now compute their
geometry (spec §8). Direction is never sampled: the journey is always up and
down (`journey.updown`).

## Which notes, then where: two passes, in that order

The pitch content comes from `theory.chord_pitches` and nothing here
reimplements chord maths. The family's own work is the second half of §6's
promise — **it decides where each note is played**, not only which note it is —
and it delegates that placement to `arpeggio_shapes.shape_places`, which tiles
one canonical seed shape per quality up the strings. Positions are assigned to
the *ascending chord tones*, once, before `pattern` is applied: a pattern like
`numeric_1353` plays most tones three times, and a chord whose tones moved
around under the hand between repetitions would be a different exercise every
time it came round.

## The axes, and what this module decided about them

**Arpeggios have one layout in v1 — the seed shape.** The `traversal` axis is
gone (spec §6, §8): its three former values (`positional`, `across_strings`,
`single_string`) would all now route through `shape_places` to identical output,
so keeping it would be a no-op axis §9's coverage accounting could not tell
apart. The single/two-string modes are deferred (spec §13). The
`direction`, `string_set` and `range_octaves` axes are gone for the same reason
they left every family: direction is always up-and-down, the string set is the
whole instrument outer-to-outer, and the octave count is emergent.

**`inversion` is a registry identifier, not a rotation count.** §7 writes the
column as root/first/second/third, `vocabulary` carries those four identifiers
and `config` samples the axis through the same `_registry` path as every other
identifier, so that is what arrives here. The bare integer
`theory.chord_pitches` takes is an implementation detail of `theory`, and
`INVERSIONS` is the one place the two meet: a value's *position* in it is the
rotation count. An inversion the chord cannot support — a triad's third — is
rejected by `theory` and the refusal is allowed through unwrapped, because its
message already names the quality and the range it accepted.

**`pattern` shapes the sequence and the journey then orders it**, the same way
round as in `scales`. Each pattern is a window of tone offsets slid along the
ascending chord: `numeric_1353` is `(0, 1, 2, 1)`, so it emits 1-3-5-3, 3-5-7-5;
`broken` is `(0, 2)`, which skips a tone and comes back for it. `sweep_ordered`
is the three-tone window `(0, 1, 2)` — the arpeggio rolled up in overlapping
three-note sweeps, which is how sweep picking is drilled.

**`finger` is left unspecified.** §6 makes fingering first class because in
*chromatic* permutation work the fingering is the exercise. Here the position
is, and prescribing a finger would engrave a fingering the caller never asked
for. The field is `None`, which §6 defines as unspecified rather than absent.

## The key, and what it costs the fully diminished seventh

§10a: chords are spelled by function, and `theory.IMPLIED_PARENT` is what turns
that into the one `Key` mechanism the scales already use — the chord tones fall
out as a subset of the parent's spelling. Stating the key costs this family
nothing, because it already holds the root and the quality; *not* stating it
would cost every note on the sheet its spelling, silently, because a key-less
Score still constructs and still engraves.

## Running off the neck

A specification that cannot be laid out as a full journey to the top string
raises, naming the axes that could not be satisfied. It is never clamped to fit
— a clamped exercise is a plausible-looking sheet that is not the one the
selector drew, and §9's validity gate exists precisely to resample this case.
"""

from __future__ import annotations

from fractions import Fraction
from typing import TYPE_CHECKING, cast

from melete import theory, vocabulary
from melete.families._shared import (
    Parameters,
    box,
    layout_hints,
    realizable,
    there_and_back,
    windowed,
)
from melete.families.arpeggio_shapes import shape_places
from melete.families.arpeggio_tap_shapes import box_places
from melete.families.journey import updown
from melete.layout import Lever
from melete.score import Attack, Hand, Note, Score

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from melete.instrument import InstrumentProfile
    from melete.layout import LayoutHints
    from melete.score import Voice

#: This family's identifier in `vocabulary.AXES["family"]`, and the prefix on
#: every error this module raises (§13). Written once so the two cannot drift.
_FAMILY = "arpeggios"

#: Spec §7's tempo range for this family, in beats per minute. The *family*
#: declares it and the selector never samples it (decision #20); configuration
#: overrides it per family through `[pool.arpeggios] tempo`.
#:
#: The demand here is comparable to `scales`, so the range is the same one.
DEFAULT_TEMPO_RANGE = (80, 140)

#: The un-modified reading: one note per beat in common time. `rhythm.py` (§8)
#: is the cross-cutting modifier that re-times a Score into subdivisions and
#: other meters, so this family states the plainest possible rhythm and leaves
#: the subject to the one module that owns it.
DEFAULT_TIME_SIGNATURE = (4, 4)
NOTE_DURATION = Fraction(1, 4)

INSTRUCTION = "Name each chord tone as it sounds; keep the string crossings even."

#: §7's axis columns this family reads, after epic #72 retired the geometry axes
#: (`direction`, `string_set`, `range_octaves`) and the now-redundant `traversal`
#: (arpeggios have one layout in v1 — the seed shape). Named here so a missing
#: parameter can list what the family expected rather than only what it did not
#: find.
AXES = (
    "root",
    "quality",
    "inversion",
    "pattern",
)

#: §7's `inversion` column, and the one place its identifiers meet the integer
#: rotation count `theory.chord_pitches` takes: a value's *position* here is
#: that count. `theory` decides whether the chord can support it — a triad has
#: no third inversion — so nothing is enumerated twice.
INVERSIONS: tuple[str, ...] = ("root", "first", "second", "third")

_STRAIGHT = "straight"

#: Each pattern as the tone offsets of one window, slid one chord tone at a
#: time along the ascending chord. `straight` is the identity window.
#:
#: The widest window spans three tones and the shortest journey this family can
#: produce reaches the top string over several octaves, so no pattern can be
#: starved of tones to slide along.
_PATTERN_WINDOWS: dict[str, tuple[int, ...]] = {
    _STRAIGHT: (0,),
    "numeric_1353": (0, 1, 2, 1),
    "broken": (0, 2),
    "sweep_ordered": (0, 1, 2),
}

_SEMITONES_PER_OCTAVE = len(theory.PITCH_CLASSES)

#: Strings an octave spans in perfect-fourths tuning — the same step
#: `arpeggio_shapes` tiles the seed by, so the two cannot disagree about how far
#: up the neck a higher octave sits.
_OCTAVE_STRING_STEP = 2

#: Frets an octave adds when the two-hand box climbs one octave: ten of a
#: fourth-tuned octave's twelve semitones are the `+2` strings, the other two are
#: frets. The box's octave-root sits `+2` frets above its root two strings up,
#: and the next box re-roots there — so a box climbs `+2` strings / `+2` frets.
_OCTAVE_FRET_STEP = 2

#: A triad has three chord tones. A quality with this many is walked as a
#: two-hand tapped journey; a seventh (four tones) keeps the one-hand journey.
_TRIAD_TONES = 3

#: The axes named in a reach failure the two-hand box raises (spec §13).
_TAP_AXES = "root, quality, inversion"

#: §7's derived `hands` axis: how many hands an exercise is played with. It is
#: never sampled — the recency-weighted selector draws axes independently and
#: cannot couple `hands` to `quality` (decision 8) — so this family *derives* it
#: from the drawn quality instead, and the selector records it like any other
#: axis for coverage and replay.
HANDS = "hands"
_ONE_HAND = 1
_TWO_HANDS = 2


def derive(params: Mapping[str, object]) -> dict[str, object]:
    """The axes `arpeggios` derives from a drawn quality, not sampled (§7, decision 8).

    Tapping is not a sampled axis: a **triad** quality is inherently a tapped
    candidate (there is no one-hand triad seed shape — decision 10), so the
    selector lists the four triads alongside the sevenths in the ordinary
    `qualities` pool and this function turns the drawn quality into the two
    values that follow from it deterministically:

    * `hands` — `2` for a triad, `1` for a seventh — so coverage accounting and
      replay see the hand count like any other axis without a `hands`↔`quality`
      coupling the independent sampler cannot express.
    * `inversion` — pinned to root for a triad, because the captured tap box is a
      root-position shape (spec §2) and a non-root triad raises (`_tapped_ascending`).
      Fixing it here means the selector never *samples* `first`/`second` for a
      triad and then discards it — the value is derived, so a triad draw does not
      consume the `inversion` pool at all. A seventh is not a tapped candidate,
      so its `inversion` is left to be sampled normally (it is absent from the
      returned mapping).

    Called incrementally by the selector as it samples, so `quality` may not have
    been drawn yet; until it has, there is nothing to derive and the mapping is
    empty.
    """
    quality = params.get("quality")
    if quality is None:
        return {}
    if _is_triad(cast("str", quality)):
        return {HANDS: _TWO_HANDS, "inversion": INVERSIONS[0]}
    return {HANDS: _ONE_HAND}


def _tones_to_the_top(octave_len: int, top: int) -> int:
    """How many ascending tones the seed lays out before one lands on `top`.

    The seed places tone `index` on string `(index % octave_len) +
    _OCTAVE_STRING_STEP * (index // octave_len)` (one tone per string, an octave
    two strings up), mirroring `arpeggio_shapes.shape_places`. Every string is
    reached in turn, so `top` is always hit exactly; the count is the index that
    first lands on it, plus one.
    """
    index = 0
    while (index % octave_len) + _OCTAVE_STRING_STEP * (index // octave_len) != top:
        index += 1
    return index + 1


def _journey(
    profile: InstrumentProfile,
    root: int,
    quality: str,
    inversion: str,
) -> tuple[list[int], list[tuple[int, int]]]:
    """Ascending chord tones placed by the seed shape, low string to top string.

    The tones climb from the root's placement on the lowest instrument string,
    laid out by `arpeggio_shapes.shape_places`, until the shape reaches the
    opposite outer string — the point where the journey turns around (spec §5).
    Extent and octave count are emergent, never a sampled target: the count of
    tones is exactly what it takes the seed to reach the top string.

    `shape_places` is the authority on placement, so its refusals propagate
    unwrapped (§13): an unknown quality, or a tone that runs off the neck before
    the top string — the "unrealizable journey" §9 resamples rather than
    engraving a short arpeggio.
    """
    chord = theory.chord_pitches(root, quality, INVERSIONS.index(inversion))
    root_place = (0, root - profile.tuning[0])
    top = len(profile.tuning) - 1

    count = _tones_to_the_top(len(chord), top)
    tones = [
        chord[index % len(chord)] + _SEMITONES_PER_OCTAVE * (index // len(chord))
        for index in range(count)
    ]
    places = shape_places(profile, root_place, quality, tones)
    return tones, places


def _is_triad(quality: str) -> bool:
    """Whether `quality` is a three-tone triad (so it taps) or not (so it plucks).

    The routing between the two placement paths is a data lookup, not a code
    branch per quality: any three-tone chord in `theory.CHORDS` — `maj`, `min`,
    `dim`, `aug` — walks the two-hand tapped journey, and every richer chord (a
    seventh, a sixth) keeps the one-hand `shape_places` journey. `dim`/`aug`
    are therefore data, exactly as spec §6 requires.
    """
    return len(theory.CHORDS[quality]) == _TRIAD_TONES


def _tile_boxes(
    profile: InstrumentProfile,
    root: int,
    quality: str,
) -> list[list[tuple[int, int, Hand, int]]]:
    """Tile the universal tap box up the neck, low octave first (spec §5, §6).

    Anchors the first box at the triad root on the lowest string that sounds it
    (string 0), then climbs `+2` strings / `+2` frets per octave — the box's
    octave-root becomes the next box's root — realizing each box through `box`'s
    two-anchor path so the placement honours each hand's `position_span`. The
    climb stops when the next box would leave the neck: either its top string
    runs past the instrument or a derived fret runs off the fretboard. It is
    never clamped to fit (spec §9); an empty result — not even the first box
    fits — is the caller's cue to raise.

    Each box is returned as its four `(string, fret, hand, finger)` placements
    in role order (root, third, fifth, octave-root).
    """
    root_fret = root - profile.tuning[0]
    num_strings = len(profile.tuning)

    boxes: list[list[tuple[int, int, Hand, int]]] = []
    string, fret = 0, root_fret
    while string + _OCTAVE_STRING_STEP < num_strings:  # the box's top string must exist
        shape = box_places(profile, (string, fret), quality)
        if not all(0 <= box_fret <= profile.fret_count for _s, box_fret, _h, _f in shape):
            break  # a derived fret ran off the neck: the journey turns around here
        pitches = [profile.tuning[s] + f for s, f, _h, _f in shape]
        strings = tuple(sorted({s for s, _f, _h, _fg in shape}))
        hands = [hand for _s, _f, hand, _fg in shape]
        fingers = [finger for _s, _f, _h, finger in shape]
        # The two-anchor reach gate (spec §6): left anchor at the root fret,
        # right anchor at the octave-root fret; `box` places each hand near its
        # own anchor and raises if either hand exceeds one position.
        anchors = (shape[0][1], shape[-1][1])
        placed = box(profile, pitches, strings, anchors, _FAMILY, _TAP_AXES, hands)
        boxes.append([(s, f, h, finger) for (s, f, h), finger in zip(placed, fingers, strict=True)])
        string += _OCTAVE_STRING_STEP
        fret += _OCTAVE_FRET_STEP
    return boxes


def _tapped_ascending(
    profile: InstrumentProfile,
    root: int,
    quality: str,
    inversion: str,
) -> list[Note]:
    """The ascending half of the two-hand tapped journey, low root to top (spec §6).

    The tiled boxes overlap by one pitch: box N's octave-root and box N+1's root
    are the *same* pitch (an octave up, `+2` strings, `+2` frets). That shared
    pitch is realized **once**, as the upper box's root — left hand, ring finger,
    faithful to B0's tiling rule ("the octave-root becomes the next box's root,
    retapped by the left ring finger"). So every box but the last contributes
    only its root, third and fifth, and the final box adds its octave-root to cap
    the ascent. The emitted ascending pitch sequence is then exactly the triad's
    `theory.chord_pitches` tiled across the register — each pitch once (spec §10).

    Every note is `TAPPED`; the legato pass (`_shared.derive_legato`, run after
    the fitter) is what may later turn same-string-run followers into slurs, and
    it is a no-op here because the box puts nothing on the same string and hand
    consecutively.

    The captured box is a root-position shape (spec §2); a non-root inversion is
    deferred and raises rather than silently tapping the root-position shape.
    """
    if inversion != INVERSIONS[0]:
        msg = (
            f"{_FAMILY}: the two-hand tap box is a root-position shape; inversion "
            f"{inversion!r} is deferred (spec §2, §12) — only {INVERSIONS[0]!r} taps in v1"
        )
        raise ValueError(msg)

    boxes = _tile_boxes(profile, root, quality)
    if not boxes:
        msg = (
            f"{_FAMILY}: a {quality} rooted at pitch {root} has no on-neck two-hand box on "
            f"profile {profile.name!r} (frets 0 to {profile.fret_count}); the tapped journey "
            f"is unrealizable here rather than clamped (spec §9)"
        )
        raise ValueError(msg)

    notes: list[Note] = []
    for index, shape in enumerate(boxes):
        used = shape if index == len(boxes) - 1 else shape[:_TRIAD_TONES]
        for string, fret, hand, finger in used:
            notes.append(
                Note(
                    pitch=profile.tuning[string] + fret,
                    string=string,
                    fret=fret,
                    duration=NOTE_DURATION,
                    finger=finger,
                    accent=False,
                    hand=hand,
                    attack=Attack.TAPPED,
                )
            )
    return notes


def _ascending_notes(
    profile: InstrumentProfile,
    root: int,
    quality: str,
    inversion: str,
) -> list[Note]:
    """The journey's ascending pass as notes, routed by quality class (spec §6).

    A triad walks the two-hand tapped journey; a seventh keeps the one-hand
    `shape_places` journey. Both return the ascending pass as one note per tone,
    which `generate` then windows by `pattern` and orders up-and-down — the same
    machinery round for both paths, so `pattern`, the turnaround and the layout
    hints are computed once.
    """
    if _is_triad(quality):
        return _tapped_ascending(profile, root, quality, inversion)
    tones, places = _journey(profile, root, quality, inversion)
    return [
        Note(
            pitch=tones[index],
            string=places[index][0],
            fret=places[index][1],
            duration=NOTE_DURATION,
            finger=None,
            accent=False,
        )
        for index in range(len(tones))
    ]


def _title(root: int, quality: str, inversion: str, pattern: str) -> str:
    """The plain-language name §12's cover page prints, built from the registry.

    The journey is always up-and-down (spec §5), so the title states no
    direction: what it names is the chord, its inversion when there is one, and
    the pattern figure when it is not the plain reading.
    """
    name = (
        f"{theory.PITCH_CLASSES[root % _SEMITONES_PER_OCTAVE]} "
        f"{vocabulary.display('quality', quality)}"
    )
    if inversion != INVERSIONS[0]:
        name += f", {vocabulary.display('inversion', inversion)}"
    if pattern != _STRAIGHT:
        name += f", {vocabulary.display('pattern', pattern)}"
    return name


def generate(profile: InstrumentProfile, params: Mapping[str, object]) -> tuple[Score, LayoutHints]:
    """Realize one arpeggio exercise on `profile`, with the §4.2 layout hints.

    Pure: the same profile and parameters always produce the same Score. Extra
    keys in `params` are carried into the Score untouched rather than rejected
    — §8's rhythm axes travel in the same dictionary — but every axis this
    family reads is required, so a misspelled one is a loud failure and never a
    silent default.

    The voice is the up-and-down journey (spec §5), routed by quality class: a
    triad is walked as a two-hand *tapped* journey — the universal tap box tiled
    up the chord tones (`_tapped_ascending`) — and a seventh keeps the one-hand
    `arpeggio_shapes.shape_places` journey. Either way the ascending pass is
    placed once and `pattern` slides its window along it; `_order_and_hints` then
    orders the result up and back. The two paths turn around differently — the
    one-hand journey at a *cell* boundary (apex cell dropped, so the count stays
    tileable), the tapped triad at the *note* level (a clean symmetric palindrome
    that retraces the full ascent in reverse, spec §6, corpus R7).

    The hints are the fitter's window onto what the voice alone does not carry:
    the natural cell (one turn of the `pattern` window for the one-hand journey,
    the single tap for the tapped triad) and the apex the journey turns around at,
    so the fitter's apex levers know where to act.
    """
    read = Parameters(_FAMILY, AXES, params)
    root = read.integer("root")
    quality = read.identifier("quality")
    inversion = read.identifier("inversion")
    pattern = realizable(read, "pattern", tuple(_PATTERN_WINDOWS))

    ascending_notes = _ascending_notes(profile, root, quality, inversion)
    window = _PATTERN_WINDOWS[pattern]
    ascending = windowed(window, len(ascending_notes))
    order, hints = _order_and_hints(_is_triad(quality), window, ascending)

    voice: Voice = [ascending_notes[index] for index in order]

    score = Score(
        title=_title(root, quality, inversion, pattern),
        instruction=INSTRUCTION,
        instrument=profile,
        time_signature=DEFAULT_TIME_SIGNATURE,
        tempo_range=DEFAULT_TEMPO_RANGE,
        voice=voice,
        # §10a: a chord is spelled by function, and the implied parent is what
        # turns that into the one `Key` mechanism the scales use. `root`
        # reduces to a pitch class because A1 and A2 are the same key.
        key=theory.Key(root % _SEMITONES_PER_OCTAVE, theory.IMPLIED_PARENT[quality]),
        params=dict(params),
    )
    return score, hints


_TAPPED_LEVERS = (Lever.ADD_ONE, Lever.DROP_ONE, Lever.APEX_REPEAT, Lever.APEX_OMIT)


def _order_and_hints(
    tapped: bool, window: tuple[int, ...], ascending: Sequence[int]
) -> tuple[list[int], LayoutHints]:
    """The playing order of the ascending indices, and the §4.2 hints, per path.

    Both paths are the up-and-down journey (spec §5), but they turn around
    differently:

    * The **one-hand** journey (a seventh, or every plucked family) turns around
      at a *cell* boundary: `journey.updown` plays the ascent, then the retrograde
      of the ascent *minus its trailing apex cell*, so the note count stays a whole
      number of `pattern` cells and the fitter always has whole beats (the #132
      fix). Its cell is one turn of the window and its seam is that cell's last note.

    * The **two-hand tapped** triad journey turns around at the *note* level, a
      clean symmetric palindrome: the descent retraces the **full** ascending pitch
      sequence in reverse (`there_and_back`), the apex tapped once at the turn, so
      the whole journey reads the same forwards and backwards (spec §6, corpus R7,
      `melete#200`). Nothing is dropped — the tapped line mirrors exactly, with no
      cascade repeat. Its natural rhythmic cell is the single tap (`cell = 1`), so
      the odd up-and-back count tiles the way the plain `straight` line already
      does; the seam is the apex, the last ascending note.
    """
    if tapped:
        order = there_and_back(list(ascending))
        hints = layout_hints(cell=1, seam=len(ascending) - 1, levers=_TAPPED_LEVERS)
        return order, hints
    order = updown(ascending, len(window))
    hints = layout_hints(cell=len(window), seam=len(ascending) - 1, levers=_TAPPED_LEVERS)
    return order, hints
