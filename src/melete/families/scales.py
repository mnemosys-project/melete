"""`scales` — modes and scale patterns (spec §7, MNEMOSYS H1, H2, H3, H5).

`generate` is a pure function: no I/O, no randomness, no clock. The selector
(§9) chooses the parameters and this module realizes them, which is what makes
a sheet reproducible from its session log and this family testable without any
of the machinery around it. It therefore imports neither `selection` nor
`config`.

The largest family — roughly 24,000 variants before rhythm is applied.

## What one exercise is: the outer-to-outer journey (epic #72, spec §5)

One exercise is **one computed round trip** across the instrument. The root is
anchored on the lowest string (the selector realizes that anchor, §5) and the
journey climbs **outward, string by string, to the opposite outer string** under
the chosen fingering style — then turns around and returns as the exact
retrograde of the ascent. Direction is never sampled: every scale is drilled up
and back (spec §5, decision 1).

**Extent is governed by reaching the opposite outer string, and the octave count
is emergent** — never a sampled target (spec §5, decision 11). A six-string
already spans every string within one boxed hand position; a
three-note-per-string climb walks string by string to the top. What that yields
in octaves is whatever the instrument gives (≈2.5 on a six-string), and the
family no longer carries the one-octave `positional` fallback the old
two-octave target needed — there is no fixed target to fall short of.

## Which notes, then where: two passes, in that order

The pitch content comes from `theory.scale_pitches` — a long ascending supply,
enough octaves to reach the top string on any profile — and nothing here
reimplements it. The family's own work is the second half of §6's promise: it
decides **where** each note is played. Placement is delegated to the shared
`journey` builder, which returns the pitches it actually used and their
`(string, fret)` places; the family picks the fingering style and its pitch
content and leaves the geometry to `journey`.

Positions are assigned to the *degrees of the ascending journey*, once, before
the `pattern` window and the up-and-down retrograde are applied. That ordering
is the design, not an implementation convenience: a pattern like `groups_of_3`
plays most degrees three times, and a scale whose notes moved around under the
hand between repetitions would be a different exercise every time it came round.

## The axes this family reads (spec §7, §8)

Four axes: `root`, `scale_type`, `traversal` (the fingering style), and
`pattern`. The three geometry axes the old model sampled — `direction`,
`string_set`, `range_octaves` — are gone (spec §8): direction is always
up-and-down, string coverage is the whole instrument, and octave count is
emergent. Those keys may still arrive in `params` while the config migration
(#72 Task E2) lands; the family simply no longer reads them, and extra keys are
carried into the Score untouched, per the existing contract.

**`traversal` is the fingering style**, and it is a sampled *content* choice —
which mapping to drill — whose geometry is then computed (spec §6):

- **`positional`** — the box climbs the neck by string, every note sitting under
  one hand within `position_span`. `journey.boxed_span` grows the box pitch by
  pitch from the low anchor while it still fits one position.
- **`three_note_per_string`** — three consecutive scale degrees on each string,
  climbing outward to the top string by construction.

The two single-string / one-octave-per-string readings the old model carried are
deferred to the single/two-string modes (spec §13) and are not realized here.

**`pattern` shapes the sequence and the journey then plays it up and back.**
Every pattern is a window of degree offsets slid one degree at a time along the
full ascent (spec §7) — `thirds` is `(0, 2)`, so it emits 1-3, 2-4, 3-5;
`groups_of_3` is `(0, 1, 2)`, so it emits 1-2-3, 2-3-4, 3-4-5. The window reaches
across the whole neck because the journey supplies the full outer-to-outer ascent
it slides along (the fix for defect 3). The retrograde of the patterned ascent
*is* the descent — `journey.updown` reuses `directed_by_cell`, turning around a
whole cell at a time so the note count stays a whole number of beats.

**`finger` is left unspecified.** §6 makes fingering first class because in
*chromatic* permutation work the fingering is the exercise. Here the position
is, and prescribing a finger would engrave a fingering the caller never asked
for. The field is `None`, which §6 defines as unspecified rather than absent.

## Running off the neck

A specification that cannot be realized on the profile raises, naming the axes
that could not be satisfied (spec §10). It is never clamped or truncated to fit
— the journey is never shortened to make it playable — and §9's validity gate
resamples the draw.
"""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from typing import TYPE_CHECKING

from melete import theory, vocabulary
from melete.families._shared import Parameters, apex_doubled, layout_hints, realizable, windowed
from melete.families.journey import boxed_span, per_string, updown
from melete.layout import Lever
from melete.score import Attack, Hand, Note, Score

if TYPE_CHECKING:
    from collections.abc import Mapping

    from melete.instrument import InstrumentProfile
    from melete.layout import LayoutHints
    from melete.score import Voice

#: This family's identifier in `vocabulary.AXES["family"]`, and the prefix on
#: every error this module raises (§13). Written once so the two cannot drift.
_FAMILY = "scales"

#: Spec §7's tempo range for this family, in beats per minute. The *family*
#: declares it and the selector never samples it (decision #20); configuration
#: overrides it per family through `[pool.scales] tempo`.
#:
#: Three notes per string in triplet eighths is practised near the top of this
#: range and the bottom of it is a warm-up, which is why the original 80-100 —
#: reasoned from categories rather than from an instrument — printed a tempo
#: nobody works at. §7 carries that reasoning; the number is declared here.
DEFAULT_TEMPO_RANGE = (80, 140)

#: The un-modified reading: one note per beat in common time. `rhythm.py` (§8)
#: is the cross-cutting modifier that re-times a Score into subdivisions and
#: other meters, so this family states the plainest possible rhythm and leaves
#: the subject to the one module that owns it.
DEFAULT_TIME_SIGNATURE = (4, 4)
NOTE_DURATION = Fraction(1, 4)

INSTRUCTION = "Keep the plucking hand even through the string crossings."

#: §7's axis columns, after epic #72 retired the three geometry axes
#: (`direction`, `string_set`, `range_octaves`). Named here so a missing
#: parameter can list what the family expected rather than only what it did not
#: find.
AXES = (
    "root",
    "scale_type",
    "traversal",
    "pattern",
)

_POSITIONAL = "positional"
_THREE_NOTE_PER_STRING = "three_note_per_string"
_STRAIGHT = "straight"

#: The subset of §7's `traversal` column this family realizes as a fingering
#: style (spec §6). `vocabulary` carries the union of every family's traversals
#: in one axis, so the family states which of them it can lay out — the
#: single-string and one-octave-per-string readings are deferred (spec §13), and
#: `across_strings` belongs to `arpeggios`.
_TRAVERSALS = (_POSITIONAL, _THREE_NOTE_PER_STRING)

#: Each pattern as the degree offsets of one window, slid one degree at a time
#: along the full ascent. `straight` is the identity window; §7's "numeric
#: permutations (1-2-3-5)" is `(0, 1, 2, 4)`.
#:
#: The widest window spans five degrees, and the outer-to-outer journey supplies
#: far more than that on any profile, so no pattern can be starved of degrees to
#: slide along.
_PATTERN_WINDOWS: dict[str, tuple[int, ...]] = {
    _STRAIGHT: (0,),
    "thirds": (0, 2),
    "fourths": (0, 3),
    "groups_of_3": (0, 1, 2),
    "groups_of_4": (0, 1, 2, 3),
    "numeric_1235": (0, 1, 2, 4),
}

#: The axes the `journey` builder names when a note falls off the neck (§13).
#: The builder raises with this rather than a sentence of its own, because
#: naming *this family's* axes is the whole of what the error is for.
_JOURNEY_AXES = "root and scale_type"

#: How many degrees `three_note_per_string` puts on each string. Named because
#: the identifier and the number must not be able to disagree.
_NOTES_PER_STRING = 3

#: §7's derived `hands` axis: how many hands the scale is played with. A one-hand
#: scale is the default (nothing derives two hands from a scale the way a triad
#: quality does in `arpeggios`), so an absent `hands` reads as `1` and the
#: existing one-hand journey is byte-for-byte unchanged. `hands == 2` is reachable
#: only by a caller passing it explicitly (the selection wiring is the follow-up
#: H2); it routes a `three_note_per_string` scale through the two-hand tapped
#: journey (corpus R9/R10).
HANDS = "hands"
_ONE_HAND = 1
_TWO_HANDS = 2

#: The last of a string's three tapped degrees is the RIGHT hand's; the two lower
#: are the LEFT hand's (corpus R9, "low = left, high = right" per string).
_TOP_OF_STRING = _NOTES_PER_STRING - 1


def _title(root: int, scale_type: str, traversal: str, pattern: str) -> str:
    """The plain-language name §12's cover page prints, built from the registry.

    Direction is no longer named: every scale is drilled up and down (spec §5),
    so stating it would print a word that is always the same.
    """
    name = (
        f"{theory.PITCH_CLASSES[root % len(theory.PITCH_CLASSES)]} "
        f"{vocabulary.display('scale_type', scale_type)}, "
        f"{vocabulary.display('traversal', traversal)}"
    )
    if pattern != _STRAIGHT:
        name = f"{name}, {vocabulary.display('pattern', pattern)}"
    return name


def _hands(params: Mapping[str, object]) -> int:
    """The hand count this scale is played with (§7's derived `hands` axis).

    Read from `params` when present — that is how a caller reaches the two-hand
    tapped 3nps scale (`hands == 2`) and how a replayed draw restores it. When it
    is absent — every one-hand specification, and every draw until the H2
    selection wiring lands — the scale is one-hand (`1`); nothing derives two
    hands from a scale the way a triad quality does in `arpeggios`, so the default
    keeps the existing journey byte-for-byte. A non-integer (or a `bool`, which is
    not a hand count) is a loud failure, never a silent default (§13).
    """
    value = params.get(HANDS)
    if value is None:
        return _ONE_HAND
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"{_FAMILY}: {HANDS} must be an integer, got {value!r}"
        raise ValueError(msg)
    return value


def _positional_tapped_is_deferred(traversal: str) -> ValueError:
    """The refusal for a two-hand *positional* scale (only 3nps taps in H1)."""
    msg = (
        f"{_FAMILY}: two-hand tapping is realized only for the "
        f"{_THREE_NOTE_PER_STRING!r} traversal (corpus R9); traversal {traversal!r} "
        f"with {HANDS} == {_TWO_HANDS} is a separate deferred shape (H1, melete#214)"
    )
    return ValueError(msg)


def _tapped_notes(pitches: list[int], places: list[tuple[int, int]]) -> list[Note]:
    """The ascending 3nps journey as tapped notes, one hand assigned per degree.

    `per_string` lays exactly three consecutive degrees on each string, low to
    high, so a degree's index modulo three is its role within the string: the
    **top** (`_TOP_OF_STRING`) is the RIGHT hand's tap, the two **lower** degrees
    are the LEFT hand's (corpus R9, per-string "low = left, high = right"). Every
    note is emitted `TAPPED`; the ascending hammer-ons and the descending
    same-hand pull-offs are the legato pass's to derive after the fitter, and the
    descending *cross-hand* pull-off is stamped by `_stamp_descending_pulls`.
    """
    notes: list[Note] = []
    for index, (pitch, (string, fret)) in enumerate(zip(pitches, places, strict=True)):
        hand = Hand.RIGHT if index % _NOTES_PER_STRING == _TOP_OF_STRING else Hand.LEFT
        notes.append(
            Note(
                pitch=pitch,
                string=string,
                fret=fret,
                duration=NOTE_DURATION,
                finger=None,
                accent=False,
                hand=hand,
                attack=Attack.TAPPED,
            )
        )
    return notes


def _stamp_descending_pulls(notes: list[Note]) -> Voice:
    """Stamp the descending group's cross-hand pull-off as `SLURRED` (corpus R9/R10).

    In a descending 3nps group the right-tapped top is pulled off to the
    left-fretted note directly below it: a slur that **crosses hands** on one
    string with a *falling* fret. The shared legato pass derives only *same-hand*
    runs and cannot tell this pull from a fresh-tapped hand leapfrog, so the
    family stamps it here (the note directly after a same-string, other-hand,
    higher-fret note) and `derive_legato` preserves the stamp (`melete#214`). The
    same-hand slurs — the ascending hammer-on and the lower descending pull — are
    left `TAPPED` for the legato pass to derive; the ascending top, a *rising*
    cross-hand tap, is not a pull-off and stays `TAPPED`.

    Operates on the flat run of tapped `Note`s the tapped journey emits, before
    the barring pass groups any tuplet.
    """
    stamped: Voice = []
    for index, note in enumerate(notes):
        prev = notes[index - 1] if index else None
        pull = (
            prev is not None
            and prev.string == note.string
            and prev.hand is not note.hand
            and prev.fret > note.fret
        )
        stamped.append(replace(note, attack=Attack.SLURRED) if pull else note)
    return stamped


def _tapped_scale(
    profile: InstrumentProfile, supply: list[int], pattern: str
) -> tuple[Voice, LayoutHints]:
    """The two-hand tapped 3nps scale, up and back (corpus R9/R10, spec §6).

    The 3nps placement is the one-hand journey's (`journey.per_string`) — three
    consecutive scale tones per string, climbing outward — but each degree carries
    its hand (R9) and every note is tapped. The `pattern` window slides along the
    ascending degrees exactly as the one-hand path, then the journey turns around
    at the *note* level as an **apex-doubled** symmetric palindrome
    (`apex_doubled`): the descent is the exact retrograde of the ascent with the
    apex re-tapped, so each string's descending group reads top-down (tap · pull ·
    pull) and the even note count tiles into whole bars with no lever — the same
    turnaround the tapped arpeggio journey uses (corpus R7/R12). The descending
    cross-hand pull is then stamped (`_stamp_descending_pulls`).
    """
    pitches, places = per_string(profile, supply, _NOTES_PER_STRING, _FAMILY, _JOURNEY_AXES)
    ascending_notes = _tapped_notes(pitches, places)

    window = _PATTERN_WINDOWS[pattern]
    ascending = windowed(window, len(ascending_notes))
    order = apex_doubled(ascending)

    voice = _stamp_descending_pulls([ascending_notes[degree] for degree in order])
    # The single tap is the natural cell; the seam is the apex (the last ascending
    # note, the first of the doubled pair). The even apex-doubled count always
    # tiles, so no note-count lever is offered — the one thing that keeps the
    # symmetric descent's closing root from being stripped (corpus R12).
    hints = layout_hints(cell=1, seam=len(ascending) - 1, levers=())
    return voice, hints


def generate(profile: InstrumentProfile, params: Mapping[str, object]) -> tuple[Score, LayoutHints]:
    """Realize one scale exercise on `profile`, with the §4.2 layout hints.

    Pure: the same profile and parameters always produce the same Score. Extra
    keys in `params` are carried into the Score untouched rather than rejected —
    §8's rhythm axes travel in the same dictionary, and so do the retired
    geometry axes until the config migration (#72 Task E2) lands — but every axis
    this family reads is required.

    The journey is computed, not sampled: a long ascending pitch supply is placed
    outer-string to opposite-outer-string under the chosen fingering style
    (`journey.boxed_span` for `positional`, `journey.per_string` for
    `three_note_per_string`), the `pattern` window slides along the notes the
    journey actually used, and `journey.updown` plays that ascent and its exact
    retrograde. Extent and octave count are emergent from reaching the top string
    (spec §5); there is no octave target and no one-octave fallback.

    The hints carry §4.2's layout accounting: one turn of the `pattern` window is
    the natural cell, and the up-and-down voice declares its apex — the `seam`
    where the ascending half turns around — with the apex-repeat/omit levers the
    fitter uses to reach a whole-bar count.

    With `hands == 2` a `three_note_per_string` scale is instead realized as the
    **two-hand tapped** journey (corpus R9/R10, `_tapped_scale`): the same 3nps
    placement, but each string's two lower notes are left-hand and its top is
    right-hand, ascending groups tap · hammer · tap and descending groups tap ·
    pull · pull. A two-hand *positional* scale is a separate deferred shape and
    raises. One-hand scales (the default) are byte-for-byte unchanged.
    """
    read = Parameters(_FAMILY, AXES, params)
    root = read.integer("root")
    scale_type = read.identifier("scale_type")
    traversal = realizable(read, "traversal", _TRAVERSALS)
    pattern = realizable(read, "pattern", tuple(_PATTERN_WINDOWS))
    hands = _hands(params)

    # Enough octaves that the ascent reaches the opposite outer string on any
    # profile: one per string is always more than a hand or the string count
    # needs, and `journey` uses only the leading run it can actually place.
    supply = theory.scale_pitches(root, scale_type, len(profile.tuning) + 1)

    if hands == _TWO_HANDS:
        if traversal != _THREE_NOTE_PER_STRING:
            raise _positional_tapped_is_deferred(traversal)
        voice, hints = _tapped_scale(profile, supply, pattern)
    else:
        voice, hints = _one_hand_scale(profile, supply, traversal, pattern)

    score = Score(
        title=_title(root, scale_type, traversal, pattern),
        instruction=INSTRUCTION,
        instrument=profile,
        time_signature=DEFAULT_TIME_SIGNATURE,
        tempo_range=DEFAULT_TEMPO_RANGE,
        voice=voice,
        # §10a: the exercise is spelled against its own scale, and `root`
        # reduces to a pitch class because A1 and A2 are the same key.
        key=theory.Key(root % len(theory.PITCH_CLASSES), scale_type),
        params=dict(params),
    )
    return score, hints


def _one_hand_scale(
    profile: InstrumentProfile, supply: list[int], traversal: str, pattern: str
) -> tuple[Voice, LayoutHints]:
    """The one-hand journey (the default), placed then played up and back (spec §5, §6).

    The long ascending pitch supply is placed outer-string to opposite-outer-string
    under the chosen fingering style (`journey.boxed_span` for `positional`,
    `journey.per_string` for `three_note_per_string`), the `pattern` window slides
    along the notes the journey actually used, and `journey.updown` plays that
    ascent and its exact retrograde. Extent and octave count are emergent from
    reaching the top string (spec §5); there is no octave target and no one-octave
    fallback.

    The hints carry §4.2's accounting: one turn of the `pattern` window is the
    natural cell, the up-and-down voice declares its apex — the `seam` where the
    ascending half turns around — and the apex-repeat/omit levers the fitter uses
    to reach a whole-bar count.
    """
    if traversal == _THREE_NOTE_PER_STRING:
        pitches, places = per_string(profile, supply, _NOTES_PER_STRING, _FAMILY, _JOURNEY_AXES)
    else:  # positional
        pitches, places = boxed_span(profile, supply, _FAMILY, _JOURNEY_AXES)

    window = _PATTERN_WINDOWS[pattern]
    ascending = windowed(window, len(pitches))
    order = updown(ascending, len(window))

    voice: Voice = [
        Note(
            pitch=pitches[degree],
            string=places[degree][0],
            fret=places[degree][1],
            duration=NOTE_DURATION,
            finger=None,
            accent=False,
        )
        for degree in order
    ]
    hints = layout_hints(
        cell=len(window),
        seam=len(ascending) - 1,
        levers=(Lever.APEX_REPEAT, Lever.APEX_OMIT),
    )
    return voice, hints
