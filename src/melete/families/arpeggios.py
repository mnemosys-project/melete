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
    apex_doubled,
    box,
    layout_hints,
    realizable,
    windowed,
)
from melete.families.arpeggio_shapes import shape_places
from melete.families.arpeggio_tap_shapes import box_places, seventh_box_places
from melete.families.journey import updown
from melete.layout import Lever
from melete.score import Attack, Hand, Note, Score

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from melete.instrument import InstrumentProfile
    from melete.layout import LayoutHints
    from melete.score import Voice

    #: A two-hand tap box's placer: chord tones from a root anchor to
    #: `(string, fret, hand, finger)` placements. `box_places` (triad) and
    #: `seventh_box_places` (seventh) share this shape, so `_tile_boxes` tiles
    #: either up the neck without knowing which box it holds.
    BoxPlacer = Callable[
        [InstrumentProfile, tuple[int, int], str], list[tuple[int, int, Hand, int]]
    ]

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

#: The string offset of the two-hand box's top string, per box shape — the tile
#: loop needs it to know the box fits before laying it (its top string must
#: exist). The triad box spans three strings (offsets 0, 1, 1, 2) so its top sits
#: `_OCTAVE_STRING_STEP` up; the seventh grid spans two strings (offsets 0, 0, 1,
#: 1) so its top sits one string up.
_TRIAD_TOP_OFFSET = _OCTAVE_STRING_STEP
_SEVENTH_TOP_OFFSET = 1

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
    places: BoxPlacer,
    top_offset: int,
) -> list[list[tuple[int, int, Hand, int]]]:
    """Tile a two-hand tap box up the neck, low octave first (spec §5, §6).

    Anchors the first box at the chord root on the lowest string that sounds it
    (string 0), then climbs `+2` strings / `+2` frets per octave — the octave
    above the box's root sits `+2` strings / `+2` frets up in fourths tuning — and
    re-roots the next box there. Placement goes through `box`'s two-anchor path so
    each hand honours its own `position_span`. The climb stops when the next box
    would leave the neck: either its top string (`top_offset` above the box's
    lowest) runs past the instrument or a derived fret runs off the fretboard. It
    is never clamped to fit (spec §9); an empty result — not even the first box
    fits — is the caller's cue to raise.

    `places` is the box's own placer — `box_places` (triad) or `seventh_box_places`
    (seventh) — so the tiling machinery is shared and only the shape differs. Each
    box is returned as its `(string, fret, hand, finger)` placements in role order
    (triad: root, third, fifth, octave-root; seventh: root, third, fifth, seventh).
    """
    root_fret = root - profile.tuning[0]
    num_strings = len(profile.tuning)

    boxes: list[list[tuple[int, int, Hand, int]]] = []
    string, fret = 0, root_fret
    while string + top_offset < num_strings:  # the box's top string must exist
        shape = places(profile, (string, fret), quality)
        if not all(0 <= box_fret <= profile.fret_count for _s, box_fret, _h, _f in shape):
            break  # a derived fret ran off the neck: the journey turns around here
        pitches = [profile.tuning[s] + f for s, f, _h, _f in shape]
        strings = tuple(sorted({s for s, _f, _h, _fg in shape}))
        hands = [hand for _s, _f, hand, _fg in shape]
        fingers = [finger for _s, _f, _h, finger in shape]
        # The two-anchor reach gate (spec §6): left anchor at the box's first
        # (lower-fret, left) tone, right anchor at its last (upper-fret, right)
        # tone; `box` places each hand near its own anchor and raises if either
        # hand exceeds one position.
        anchors = (shape[0][1], shape[-1][1])
        placed = box(profile, pitches, strings, anchors, _FAMILY, _TAP_AXES, hands)
        boxes.append([(s, f, h, finger) for (s, f, h), finger in zip(placed, fingers, strict=True)])
        string += _OCTAVE_STRING_STEP
        fret += _OCTAVE_FRET_STEP
    return boxes


def _tap_note(profile: InstrumentProfile, string: int, fret: int, hand: Hand, finger: int) -> Note:
    """One tapped note of a two-hand box, pitch derived from its position (spec §6).

    Every note a tapped journey emits is `TAPPED` and carries the box's own
    `hand`/`finger`; the legato pass (`_shared.derive_legato`, run after the
    fitter) is what may later turn same-string-run followers into slurs.
    """
    return Note(
        pitch=profile.tuning[string] + fret,
        string=string,
        fret=fret,
        duration=NOTE_DURATION,
        finger=finger,
        accent=False,
        hand=hand,
        attack=Attack.TAPPED,
    )


def _no_on_neck_box(profile: InstrumentProfile, root: int, quality: str) -> ValueError:
    """The §9 refusal when not even the first box fits on the neck (never clamped)."""
    msg = (
        f"{_FAMILY}: a {quality} rooted at pitch {root} has no on-neck two-hand box on "
        f"profile {profile.name!r} (frets 0 to {profile.fret_count}); the tapped journey "
        f"is unrealizable here rather than clamped (spec §9)"
    )
    return ValueError(msg)


def _root_position_only(inversion: str) -> ValueError:
    """The §2 refusal for a non-root tapped inversion (the captured boxes are root shapes)."""
    msg = (
        f"{_FAMILY}: the two-hand tap box is a root-position shape; inversion "
        f"{inversion!r} is deferred (spec §2, §12) — only {INVERSIONS[0]!r} taps in v1"
    )
    return ValueError(msg)


def _tapped_ascending(
    profile: InstrumentProfile,
    root: int,
    quality: str,
    inversion: str,
) -> list[Note]:
    """The ascending half of the two-hand tapped *triad* journey, low root to top (spec §6).

    The tiled boxes overlap by one pitch: box N's octave-root and box N+1's root
    are the *same* pitch (an octave up, `+2` strings, `+2` frets). That shared
    pitch is realized **once**, as the upper box's root — left hand, ring finger,
    faithful to B0's tiling rule ("the octave-root becomes the next box's root,
    retapped by the left ring finger"). So every box but the last contributes
    only its root, third and fifth, and the final box adds its octave-root to cap
    the ascent. The emitted ascending pitch sequence is then exactly the triad's
    `theory.chord_pitches` tiled across the register — each pitch once (spec §10).

    The captured box is a root-position shape (spec §2); a non-root inversion is
    deferred and raises rather than silently tapping the root-position shape.
    """
    if inversion != INVERSIONS[0]:
        raise _root_position_only(inversion)

    boxes = _tile_boxes(profile, root, quality, box_places, _TRIAD_TOP_OFFSET)
    if not boxes:
        raise _no_on_neck_box(profile, root, quality)

    notes: list[Note] = []
    for index, shape in enumerate(boxes):
        # Every box but the last drops its octave-root: it is box N+1's root,
        # emitted once, there. The final box keeps it to cap the ascent.
        used = shape if index == len(boxes) - 1 else shape[:_TRIAD_TONES]
        notes.extend(_tap_note(profile, s, f, h, finger) for s, f, h, finger in used)
    return notes


def _seventh_tapped_ascending(
    profile: InstrumentProfile,
    root: int,
    quality: str,
    inversion: str,
) -> list[Note]:
    """The ascending half of the two-hand tapped *seventh* journey (spec §6, corpus R11).

    A seventh chord's four tones tap on a compact two-string grid
    (`seventh_box_places`): string N carries root (left) + third (right), string
    N+1 carries fifth (left) + seventh (right). Unlike the triad box there is **no
    octave-tiling overlap** — the four tones fill the grid — so the next octave
    tiles onto the *next string-pair up* (`+2` strings / `+2` frets) with no shared
    pitch, and every box contributes all four of its tones. The emitted ascending
    pitch sequence is therefore the seventh's `theory.chord_pitches` tiled across
    the register, strictly increasing, each pitch once (spec §10; the instructor
    example `Tapping_Arpeggios_7th_Chords.gp`, bars 5-6).

    The seventh grid is a root-position shape (spec §2); a non-root inversion is
    deferred and raises rather than silently tapping the root-position shape.
    """
    if inversion != INVERSIONS[0]:
        raise _root_position_only(inversion)

    boxes = _tile_boxes(profile, root, quality, seventh_box_places, _SEVENTH_TOP_OFFSET)
    if not boxes:
        raise _no_on_neck_box(profile, root, quality)

    notes: list[Note] = []
    for shape in boxes:  # no overlap: every box contributes all four tones
        notes.extend(_tap_note(profile, s, f, h, finger) for s, f, h, finger in shape)
    return notes


def _ascending_notes(
    profile: InstrumentProfile,
    root: int,
    quality: str,
    inversion: str,
    hands: int,
) -> list[Note]:
    """The journey's ascending pass as notes, routed by `hands` then quality (spec §6).

    Routing keys on the hand count first, then the quality class:

    * `hands == 2` + a **triad** → the two-hand tapped triad journey
      (`TAP_BOX` tiled with an octave overlap);
    * `hands == 2` + a **seventh** → the two-hand tapped seventh journey
      (`SEVENTH_TAP_BOX` tiled on the next string-pair up, no overlap — G2);
    * `hands == 1` → the one-hand `shape_places` journey, for any quality.

    In practice `hands` is *derived* (`derive`): a triad draws two hands, a seventh
    one — so the two-hand seventh is reachable only when a caller supplies
    `hands == 2` explicitly (the selection wiring is the follow-up G3). Whichever
    path runs, all three return the ascending pass as one note per tone, which
    `generate` then windows by `pattern` and orders up-and-down — the same
    machinery round for every path, so `pattern`, the turnaround and the layout
    hints are computed once.
    """
    if hands == _TWO_HANDS:
        if _is_triad(quality):
            return _tapped_ascending(profile, root, quality, inversion)
        return _seventh_tapped_ascending(profile, root, quality, inversion)
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


def _hands(params: Mapping[str, object], quality: str) -> int:
    """The hand count this exercise is played with (§7's derived `hands` axis).

    Read from `params` when present — that is how a caller reaches the two-hand
    seventh journey (`hands == 2` + a seventh) and how the selector replays a
    recorded draw. When it is absent — a hand-written specification that names
    only the sampled axes — it is *derived* from the quality (`derive`), so a
    triad still taps and a seventh still plucks exactly as before `hands` routed
    anything. A non-integer (or a `bool`, which is not a hand count) is a loud
    failure, never a silent default.
    """
    value = params.get(HANDS)
    if value is None:
        return cast("int", derive({"quality": quality})[HANDS])
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"{_FAMILY}: {HANDS} must be an integer, got {value!r}"
        raise ValueError(msg)
    return value


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

    The voice is the up-and-down journey (spec §5), routed by `hands` then quality
    class: with two hands a **triad** is walked as a two-hand *tapped* journey (the
    universal `TAP_BOX` tiled up the chord tones, `_tapped_ascending`) and a
    **seventh** as its own two-hand tapped journey (the `SEVENTH_TAP_BOX` grid
    tiled on the next string-pair up, `_seventh_tapped_ascending`, G2); with one
    hand either quality keeps the one-hand `arpeggio_shapes.shape_places` journey.
    Whichever runs, the ascending pass is placed once and `pattern` slides its
    window along it; `_order_and_hints` then orders the result up and back. The
    two kinds of path turn around differently — the one-hand journey at a *cell*
    boundary (apex cell dropped, so the count stays tileable), the two-hand tapped
    journey at the *note* level (an apex-doubled symmetric palindrome that retraces
    the full ascent in reverse and re-taps the apex at the turn, so its even count
    tiles with no lever and the closing root survives, spec §6, corpus R7/R12).

    The hints are the fitter's window onto what the voice alone does not carry:
    the natural cell (one turn of the `pattern` window for the one-hand journey,
    the single tap for a tapped journey) and the apex the journey turns around at.
    The one-hand journey declares the note-count levers so the fitter can reach a
    whole-bar tile; a tapped journey declares none, because its even count always
    tiles and a lever would only break the symmetry.
    """
    read = Parameters(_FAMILY, AXES, params)
    root = read.integer("root")
    quality = read.identifier("quality")
    inversion = read.identifier("inversion")
    pattern = realizable(read, "pattern", tuple(_PATTERN_WINDOWS))

    hands = _hands(params, quality)
    ascending_notes = _ascending_notes(profile, root, quality, inversion, hands)
    window = _PATTERN_WINDOWS[pattern]
    ascending = windowed(window, len(ascending_notes))
    order, hints = _order_and_hints(hands == _TWO_HANDS, window, ascending)

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


_ONE_HAND_LEVERS = (Lever.ADD_ONE, Lever.DROP_ONE, Lever.APEX_REPEAT, Lever.APEX_OMIT)


def _order_and_hints(
    tapped: bool, window: tuple[int, ...], ascending: Sequence[int]
) -> tuple[list[int], LayoutHints]:
    """The playing order of the ascending indices, and the §4.2 hints, per path.

    Both paths are the up-and-down journey (spec §5), but they turn around
    differently:

    * The **one-hand** journey (a one-hand draw, or every plucked family) turns
      around at a *cell* boundary: `journey.updown` plays the ascent, then the retrograde
      of the ascent *minus its trailing apex cell*, so the note count stays a whole
      number of `pattern` cells and the fitter always has whole beats (the #132
      fix). Its cell is one turn of the window and its seam is that cell's last
      note, and it declares the full lever set — its count is not guaranteed even,
      so the fitter may need one to reach a whole-bar tile.

    * The **two-hand tapped** journey (a triad, or a seventh via G2) turns around
      at the *note* level, an **apex-doubled** symmetric palindrome: the descent
      retraces the full ascending pitch sequence in reverse and the apex is
      *re-tapped* at the turn
      (`apex_doubled`), so the whole journey reads the same forwards and backwards
      and ends where it began — on the root (spec §6, corpus R7/R12, `melete#205`).
      The re-tapped apex makes the count **even** (2L), which always tiles into
      whole bars with **no note-count lever** — so this path declares `levers=()`,
      the one thing that guarantees the fitter never drops the closing root
      (`DROP_ONE` on the old odd count did exactly that, undoing the symmetry, F1
      `melete#201`). Its natural rhythmic cell is the single tap (`cell = 1`); the
      seam is the last ascending note, the first of the doubled apex.
    """
    if tapped:
        order = apex_doubled(list(ascending))
        hints = layout_hints(cell=1, seam=len(ascending) - 1, levers=())
        return order, hints
    order = updown(ascending, len(window))
    hints = layout_hints(cell=len(window), seam=len(ascending) - 1, levers=_ONE_HAND_LEVERS)
    return order, hints
