r"""Score to alphaTex source text (epic #46, Task 6).

This module is a pass-through, as the original `lilypond/emit.py` was. It receives
a `Score` — pitches, string and fret positions, and **written** durations — plus
the `Measure`s a `bar()` pass produced, and turns them into alphaTex source.
It never learns what a Dorian mode is, and it never learns that the alphaTab
renderer binary exists: `render` is the only module aware of the binary, and
nothing here shells out or touches the filesystem.

**This module is renderer-specific** — melete's only emitter, and the successor
to the original `lilypond/emit.py` (removed in epic #46, Task 10). Everything it
consumes — `theory` and the whole spelling model, `instrument`, `score`,
`bar()` — is renderer-agnostic. The two emitters met only at the `Score`/`Measure`
seam; the LilyPond one is now gone, and this is the single emitter that remains.

## Every syntax token here is spike-confirmed (epic #46, Task 1)

The exact alphaTex was pinned by experiment against the installed
`@coderline/alphatab` 1.8.4 (`epics/46-alphatab-output/spike-findings.md`) and
re-verified for this task by parsing probe alphaTex back through the real
`AlphaTexImporter`. Nothing below is guessed:

* **Positional notes, not pitches.** A beat is `<fret>.<string>`; alphaTab
  derives the pitch from the tuning and fret. There is therefore **no octave
  transposition** — the LilyPond emitter's `+12` was a LilyPond convention (its
  clef read the fret off the written pitch); alphaTab reads sounding pitch off
  the tuning directly. The tuning we declare is sounding pitch, and the notation
  shows sounding pitch on a plain bass clef (the spike's Q3b decision).
* **The string convention is reversed**, as it was under LilyPond: the IR indexes
  strings from 0 as the lowest; alphaTex numbers from 1 as the highest. See
  `_alphatex_string`.
* **`\clef bass`, no `\ottava`.** The spike's final, human-reviewed decision:
  sounding pitch shown directly, no octave-displacing clef (unlike v1's
  `bass_8`). The `.gp` diverges from the v1 `.pdf` on octave *display* only.
* **alphaTab does not auto-bar.** The `|` barline is the only thing that starts a
  new bar, so we place one between every `Measure` (spike Q1). And it does not
  auto-tie, so a note split across a barline by `bar()` is emitted as an explicit
  tie (below).

## Spelling: the key signature plus a forced accidental, mirroring `forget`

alphaTab spells the notation staff itself from the positional note, so faithful
spelling means telling it *both* the key and, where the key alone is not enough,
the exact accidental. Both are expressible, so there is **no fidelity gap** with
the original LilyPond path (verified against the importer, epic #46 Task 6):

* **`\ks <name>`** sets the key signature (round-trips to alphaTab's
  `KeySignature`, −7…+7). We derive it from `score.key` through `theory`: a
  tier-1 mode signs with its own diatonic collection, a tier-2 scale with its
  parent's, and a tier-3/keyless exercise takes no signature — the same three
  cases the original `lilypond/emit.py`'s `_key_lines` answered. Under the
  signature alphaTab spells every diatonic pitch to `theory`'s letter with no
  accidental glyph.
* **`{acc <glyph>}`** forces one note's accidental (round-trips to
  `NoteAccidentalMode.Force*`). We force a note **iff** its spelling differs from
  what the signature already gives its letter — which is exactly LilyPond's
  `\accidentalStyle forget`: a diatonic tone prints nothing, an altered tone
  reprints on every occurrence. The forced glyph fixes the letter, because a
  pitch class plus a chosen accidental names exactly one letter — `theory`'s.

The spelling itself is `theory.spell`'s, asked for and never decided here, as in
the original `lilypond/emit.py`. Only the *rendering* of that spelling — signature
token plus forced glyph — is alphaTab knowledge and belongs here.

## Ties are emitted onto the destination (spike Q2)

`bar()` splits a bar-crossing note and marks the origin piece `tied=True`; the
following piece is the continuation. alphaTab writes a tie as a beat whose fret
is `-` on the same string: `-.<string>.<duration>`. So a note whose immediately
preceding note (in the flat stream, across barlines) was `tied` is emitted with
`-` in place of its fret, and carries no note effects — a sustained note is not
re-fingered, re-accented or re-spelled. The tie state is threaded across the
whole exercise's measures, since a split can chain across several bars.

## Nested tuplets are flattened to a cumulative ratio (spike Q4)

alphaTab models a tuplet as one flat `{tu N D}` per beat; there is no nesting
bracket. The port's families never emit nested tuplets, but the IR permits them
(melete#87), so a nested tuplet handed here is flattened by multiplying the
ratios outward — an inner 3:2 inside an outer 3:2 becomes `{tu 9 4}` on the leaf.
The rhythm is exact; only a true nested bracket (a non-requirement) is lost.

## Instructional prose is the session's, not an exercise's (spec §12)

As in the original `lilypond/emit.py`, `Score.instruction` never reaches an
exercise. A book carries the session title and the date/instrument subtitle; the
per-exercise `\section` marker names each exercise by number and title.
"""

from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING

from melete import theory
from melete.score import Measure, Note, Tuplet, bar

if TYPE_CHECKING:
    from collections.abc import Sequence

    from melete.score import Score

#: The alphaTab General MIDI program for electric bass (finger). The spike used
#: `\instrument(34)`; alphaTab reads it onto the track.
INSTRUMENT_BASS = 34

#: alphaTab's title for a day's session. A book is one alphaTex score whose
#: exercises are `\section`-delimited; this is the score title, and the date and
#: instrument ride the subtitle (spec §12).
SESSION_TITLE = "Practice session"

#: The barline that starts a new bar. alphaTab does not auto-bar (spike Q1), so
#: this sits between every emitted `Measure` and nowhere else.
BAR_SEPARATOR = "|"

#: The tie destination's fret: a beat `-.<string>.<duration>` continues the
#: previous note (spike Q2). Not a fret number — the sounded note is the origin.
TIE_FRET = "-"

#: The repeat-open marker (`\ro`) and repeat-close-for-two-passes marker
#: (`\rc 2`), which bracket an exercise-level repeat (`Score.repeat`, spec §5).
#: Both were spike-confirmed against `@coderline/alphatab` 1.8.4 by rendering a
#: probe and re-importing the `.gp`: `\ro` sets the master bar's `isRepeatStart`
#: and `\rc 2` sets its `repeatCount`. The close **leads** its bar rather than
#: trailing it — a trailing `\rc` makes alphaTab open a spurious empty master
#: bar for the marker, so it is prepended to the last bar's beats (melete#112).
REPEAT_OPEN = "\\ro"
REPEAT_CLOSE = "\\rc 2"

#: The track-property directive that puts each exercise on its own system in a
#: book (melete#138). alphaTab lays out `defaultSystemsLayout` bars per system —
#: 3 by default — so consecutive short exercises share a system and their
#: `\section` titles overprint. Setting `systemsLayout` to the per-exercise bar
#: counts makes each exercise fill exactly one system.
#:
#: For a **single-track** score alphaTab reads the layout off the *track*
#: (`ModelUtils.getSystemLayout` uses `displayedTracks[0].systemsLayout` when
#: `tracks.length === 1`); the score-level `\systemslayout` metadata is *not*
#: honored there, so the value must land on the track. The `\track "…" { … }`
#: property-block form carries a track-level `systemslayout` property, and an
#: empty name leaves the (already unnamed) single track's name untouched. Placed
#: once, right after the header's terminating `.` and ahead of the bar stream, it
#: configures that one track without adding a second.
#:
#: Confirmed empirically against `@coderline/alphatab` 1.8.4: rendering a book
#: with this directive and reading back the exported `Content/score.gpif` shows
#: the master track's `<SystemsLayout>` equal to the emitted counts (e.g.
#: `<SystemsLayout>2 2 2 2 2</SystemsLayout>` for five 2-bar exercises), while
#: every other node — tuning, instrument, bars, beats — is byte-identical to the
#: same book without it. `emit_score` needs no such directive: a single exercise
#: is one `\section`, so nothing can overprint.
SYSTEMS_LAYOUT_PROPERTY = "systemslayout"

#: The seven letters in ascending order, and the pitch class each names
#: unaltered. A key signature adds sharps in the order F C G D A E B and flats in
#: the order B E A D G C F; `_signature` walks these to name each letter's
#: alteration under a given signature.
_SHARP_ORDER = "FCGDAEB"
_FLAT_ORDER = "BEADGCF"

#: `theory`'s scale identifiers that carry a key signature: the seven diatonic
#: modes. A tier-1 mode signs with itself and a tier-2 scale with its parent
#: (always one of these); a tier-3 symmetric scale resolves to none of them and
#: takes no signature. This mirrored `lilypond/emit.py`'s `_LILYPOND_MODES` keys —
#: the same "which scales have a signature" question. The LilyPond path has been
#: removed (epic #46, Task 10), so this table is now the sole home for that answer.
_DIATONIC_MODES = (
    "ionian",
    "dorian",
    "phrygian",
    "lydian",
    "mixolydian",
    "aeolian",
    "locrian",
)

#: The alphaTex `\ks` names, indexed by circle-of-fifths position from −7 (seven
#: flats, `cb`) through 0 (`c`) to +7 (seven sharps, `c#`). Confirmed against the
#: importer's enum map. Given a signature's signed accidental count `p`, the
#: token is `_KS_NAMES[p + 7]`.
_KS_NAMES = ("cb", "gb", "db", "ab", "eb", "bb", "f", "c", "g", "d", "a", "e", "b", "f#", "c#")

#: A `SpelledPitch.alteration` (−2…+2 semitones) as the alphaTex `{acc}` glyph
#: that forces exactly that accidental (`x`/`##` double sharp, `#` sharp, `n`
#: natural, `b` flat, `bb` double flat). Confirmed to round-trip to the matching
#: `NoteAccidentalMode.Force*`.
_ACCIDENTAL_GLYPH = {2: "x", 1: "#", 0: "n", -1: "b", -2: "bb"}

#: Written duration as a multiple of the undotted note it augments — no dots, one
#: dot (×3/2), two dots (×7/4). This encodes, as `(dots, augmentation)` pairs for
#: token emission, the same writable set `score._split_writable` uses (and that
#: the original `lilypond/emit.py` encoded); it is duplicated across the renderer
#: boundary deliberately so `score` stays renderer-agnostic, and `bar()` only ever
#: hands us values from exactly this set.
_AUGMENTATIONS: tuple[tuple[int, Fraction], ...] = (
    (0, Fraction(1)),
    (1, Fraction(3, 2)),
    (2, Fraction(7, 4)),
)


@dataclass(frozen=True)
class Cover:
    """The session's cover content: the date and the instrument (spec §12).

    The successor to the original `lilypond.emit.Cover`, defined in the emitter
    rather than in `score` so the renderer-agnostic side carries no cover type.
    Everything else about the session — one `\\section` per exercise — is derived
    from the scores themselves, so the two cannot drift apart.
    """

    date: str
    instrument: str


# --------------------------------------------------------------------------
# The two units that are wrong silently
# --------------------------------------------------------------------------


def duration_token(written: Fraction) -> tuple[int, int]:
    """One **written** value as an alphaTex duration: `(number, dots)`.

    `1/4` is `(4, 0)`, a dotted quarter `3/8` is `(4, 1)`, a double-dotted
    quarter `7/16` is `(4, 2)`. alphaTex writes the base value inline (`.4`) and
    the dots as a `{d}`/`{dd}` beat effect, so the two are returned apart.

    A value that is not a power-of-two note with zero, one or two dots has no
    notehead and raises — the written-duration contract of the `score` seam
    (decision #16), enforced here as the original `lilypond/emit.py`'s
    `duration_token` enforced it. A sounding triplet eighth is `1/12` and there is
    no twelfth
    note; it belongs inside a `Tuplet`, whose ratio scales it.
    """
    for dots, augmentation in _AUGMENTATIONS:
        base = written / augmentation
        if base.numerator == 1 and not base.denominator & (base.denominator - 1):
            return base.denominator, dots

    msg = (
        f"{written} is not a representable note value. Durations are the "
        f"written value (decision #16): a power-of-two note, optionally with "
        f"one or two dots. A sounding triplet eighth is 1/12 and there is no "
        f"twelfth note — store 1/8 inside a Tuplet and let the ratio scale it."
    )
    raise ValueError(msg)


def _alphatex_string(index: int, string_count: int) -> int:
    """The alphaTex string number for an IR string index.

    **The two conventions are reversed**, as they were for LilyPond: the IR indexes
    strings from 0 as the *lowest* (spec §5); alphaTex numbers from 1 as the
    *highest*. On a six-string bass, IR index 5 is alphaTex string 1 and IR index
    0 is string 6. Getting it wrong puts every fret on the wrong line while the
    tablature still reads as music, so it is a named function with its own test.

    An index the instrument has no string for raises rather than wrapping: a
    negative index would address the tuning from the top and emit plausible
    tablature for the wrong strings, exactly as §5 says of tunings.
    """
    if not 0 <= index < string_count:
        msg = (
            f"string index {index} is out of range for an instrument with "
            f"{string_count} strings: expected 0 to {string_count - 1}, "
            f"counting from the lowest string."
        )
        raise ValueError(msg)
    return string_count - index


# --------------------------------------------------------------------------
# Spelling: the key signature and the forced accidental
# --------------------------------------------------------------------------


def _signature(key: theory.Key | None) -> tuple[str | None, dict[str, int]]:
    r"""The `\ks` token for a key, and each letter's alteration under it.

    Three cases take no signature, and each is a real answer rather than a
    fallback — the same three the original `lilypond/emit.py`'s `_key_lines` gave
    nothing for. `key` is `None` (no tonal centre, as the chromatic family
    produces); the
    scale is tier-3 symmetric (no parent to inherit a signature from); otherwise
    the signature is the diatonic collection of a tier-1 mode or a tier-2 scale's
    parent. In the no-signature cases every altered note is forced explicitly,
    which is `forget` with an empty signature.

    The returned map names the alteration the signature gives each of the seven
    letters — `+1` for a sharped letter, `-1` for a flatted one, `0` otherwise —
    so `_note_effects` can force exactly the notes the signature does not spell.
    """
    if key is None:
        return None, {}

    base = theory.parent_scale(key.scale_type) or key.scale_type
    if base not in _DIATONIC_MODES:
        return None, {}

    # Spell the signature scale's seven degrees from the tonic. `theory` picks the
    # tonic letter that minimises this same signature, so the parent's tonic
    # letter matches the mode's and the accidentals are the standard ones.
    pitches = [key.tonic + offset for offset in theory.SCALES[base]]
    spelled = theory.spell(theory.Key(key.tonic, base), pitches)
    signature = {pitch.letter: pitch.alteration for pitch in spelled}

    position = sum(signature.values())
    return _KS_NAMES[position + 7], signature


def _accidental(note: Note, key: theory.Key | None, signature: dict[str, int]) -> str | None:
    """The `{acc}` glyph a note needs, or `None` when the signature suffices.

    `theory.spell` decides the letter and alteration; the signature already draws
    that letter's accidental for a diatonic tone, so only a tone the signature
    spells differently is forced. This is `\\accidentalStyle forget`: nothing on a
    diatonic note, an explicit glyph on every altered one. The pitch is the
    **sounding** pitch (no octave shift) — alphaTab derives the octave from the
    tuning, so only the letter and alteration are needed here.
    """
    spelled = theory.spell(key, [note.pitch])[0]
    if spelled.alteration == signature.get(spelled.letter, 0):
        return None
    return _ACCIDENTAL_GLYPH[spelled.alteration]


# --------------------------------------------------------------------------
# Notes, beats and measures
# --------------------------------------------------------------------------


@dataclass
class _TieState:
    """Whether the previous note tied into this one, threaded down the stream.

    A `bar()` split marks the origin piece `tied`; the next note is then a tie
    destination and is emitted with `-` in place of its fret. The flag flows
    across measure boundaries within an exercise, because a split can chain
    across several bars.
    """

    previous_tied: bool = False


def _quoted(text: str) -> str:
    r"""An alphaTex string literal. Backslash first, or it escapes the escapes."""
    escaped = text.replace("\\", r"\\").replace('"', r"\"")
    return f'"{escaped}"'


def _beat_effects(dots: int, ratio: tuple[int, int] | None) -> str:
    """The `{...}` block after a duration: tuplet ratio and dots, or empty.

    A tuplet is written as an explicit `{tu N D}` (numerator in the time of
    denominator) rather than relying on alphaTab's default denominators, so the
    ratio is exact for any tuplet, flat or flattened-from-nested. Dots follow as
    `d` (one) or `dd` (two).
    """
    parts = []
    if ratio is not None:
        parts.append(f"tu {ratio[0]} {ratio[1]}")
    if dots == 1:
        parts.append("d")
    elif dots == 2:
        parts.append("dd")
    return "{" + " ".join(parts) + "}" if parts else ""


def _note_token(
    note: Note,
    string_count: int,
    key: theory.Key | None,
    signature: dict[str, int],
    tie: _TieState,
    ratio: tuple[int, int] | None,
) -> str:
    r"""One beat: `<fret>.<string>{note-effects}.<duration>{beat-effects}`.

    A tie destination — the note after a `tied` one — is emitted with `-` for its
    fret and no note effects: a sustained note is not re-fingered, re-accented or
    re-spelled. Otherwise the fret is the note's, and the note-effect brace before
    the duration carries, in order, the forced accidental, the left-hand
    fingering and the accent — the three that must sit before the duration
    (spike Q3). `ratio`, when set, is the enclosing tuplet's (cumulative) ratio.
    """
    number, dots = duration_token(note.duration)
    string = _alphatex_string(note.string, string_count)
    beat_effects = _beat_effects(dots, ratio)

    if tie.previous_tied:
        tie.previous_tied = note.tied
        return f"{TIE_FRET}.{string}.{number}{beat_effects}"
    tie.previous_tied = note.tied

    effects = []
    accidental = _accidental(note, key, signature)
    if accidental is not None:
        effects.append(f"acc {accidental}")
    if note.finger is not None:
        # melete fingers index..little as 1..4; alphaTab's `lf` is thumb..little
        # as 1..5, so the fretting fingers are 2..5 — one more than melete's.
        effects.append(f"lf {note.finger + 1}")
    if note.accent:
        effects.append("ac")
    note_effects = "{" + " ".join(effects) + "}" if effects else ""

    return f"{note.fret}.{string}{note_effects}.{number}{beat_effects}"


def _voice_tokens(
    voice: Sequence[Note | Tuplet],
    string_count: int,
    key: theory.Key | None,
    signature: dict[str, int],
    tie: _TieState,
    ratio: tuple[int, int] | None,
) -> list[str]:
    """One beat token per note, tuplets expanded in place.

    A nested tuplet is flattened by multiplying the ratios outward (spike Q4):
    each level scales the ratio it passes down, so a leaf note carries the
    product of every enclosing tuplet's ratio and the rhythm stays exact.
    `ratio` is the ratio accumulated so far — `None` outside any tuplet.
    """
    tokens: list[str] = []
    for item in voice:
        if isinstance(item, Tuplet):
            inner = ratio or (1, 1)
            combined = (inner[0] * item.ratio[0], inner[1] * item.ratio[1])
            tokens += _voice_tokens(item.notes, string_count, key, signature, tie, combined)
        else:
            tokens.append(_note_token(item, string_count, key, signature, tie, ratio))
    return tokens


def _measure_bodies(
    measures: Sequence[Measure],
    string_count: int,
    key: theory.Key | None,
    signature: dict[str, int],
) -> list[str]:
    """Each measure as its space-joined beats, tie state threaded across all.

    The tie flag is shared across the whole list so a split note continues
    correctly from one bar into the next; the `|` between measures is added by the
    caller, which prepends each exercise's leading directives to its first bar.
    """
    tie = _TieState()
    return [
        " ".join(_voice_tokens(measure.voice, string_count, key, signature, tie, None))
        for measure in measures
    ]


# --------------------------------------------------------------------------
# Exercises and the two entry points
# --------------------------------------------------------------------------


def _tuning_name(pitch: int) -> str:
    """One tuning pitch as an alphaTex note name, e.g. `C3`, `A1`.

    Spelled keylessly — a tuning has no key — and at sounding pitch, since
    alphaTab reads the fret off this tuning to recover sounding pitch. The octave
    is the letter's, which for a natural open string is the pitch's.
    """
    spelled = theory.spell(None, [pitch])[0]
    accidental = "#" * spelled.alteration + "b" * -spelled.alteration
    return f"{spelled.letter}{accidental}{spelled.octave}"


def _tuning_line(score: Score) -> str:
    r"""`\tuning(...)`, high string first (spike Q3).

    The IR lists the tuning low string first; alphaTex lists it high first, the
    same reversal `_alphatex_string` applies to a note. alphaTab reads it into the
    staff tuning and derives every note's pitch from it.
    """
    names = (_tuning_name(pitch) for pitch in reversed(score.instrument.tuning))
    return f"\\tuning({' '.join(names)})"


def _exercise_directives(score: Score, section: str | None) -> str:
    r"""The per-exercise leading directives, prepended to its first bar.

    `\section` (a book only, naming the exercise), then the time signature, the
    key signature when there is one, the plain bass clef, and the tempo. alphaTab
    propagates all of these to later bars, so they are emitted once per exercise
    and override the previous exercise's.

    The tempo is a single value where `score.tempo_range` is a range: alphaTab's
    tempo is a playback automation, not a printed range, so the slowest — the
    practice starting tempo — is used.

    When `score.repeat`, the repeat-open marker follows the tempo so it leads the
    first bar (spec §5): a `\\ro` at the start of a bar opens the repeat there.
    Its matching close is placed by `_exercise_bars` on the last bar.
    """
    beats, beat_value = score.time_signature
    slowest, _ = score.tempo_range
    ks_name, _ = _signature(score.key)

    directives = []
    if section is not None:
        directives.append(f"\\section {_quoted(section)}")
    directives.append(f"\\ts {beats} {beat_value}")
    if ks_name is not None:
        directives.append(f"\\ks {ks_name}")
    directives.append("\\clef bass")
    directives.append(f"\\tempo {slowest}")
    if score.repeat:
        directives.append(REPEAT_OPEN)
    return " ".join(directives)


def _exercise_bars(score: Score, section: str | None) -> list[str]:
    """One exercise as a list of bar bodies, first bar carrying its directives.

    `bar()` is the seam that makes the barline explicit: it splits the voice into
    `Measure`s (splitting and tying any bar-crossing note), and each `Measure`
    becomes one bar. alphaTab does not auto-bar, so this is real work, not a
    no-op (spike Q1).
    """
    measures = bar(score.voice, score.time_signature)
    _, signature = _signature(score.key)
    bodies = _measure_bodies(measures, len(score.instrument.tuning), score.key, signature)

    # `bar()` never yields an empty measure — a voice with notes fills at least
    # one bar — so the first body always has beats to prepend the directives to.
    directives = _exercise_directives(score, section)
    bodies[0] = f"{directives} {bodies[0]}"

    # The repeat close leads the last bar: a `\rc` after that bar's beats makes
    # alphaTab open a spurious empty master bar for the marker (spike-confirmed),
    # so it is prepended, before the beats and any directives already merged in.
    # For a single-bar exercise the last bar is also the first, so the close sits
    # ahead of the directives on the one bar, which alphaTab reads as that bar's
    # metadata (spike-confirmed: one master bar carrying both repeat markers).
    if score.repeat:
        bodies[-1] = f"{REPEAT_CLOSE} {bodies[-1]}"
    return bodies


def _systems_layout_line(bar_counts: Sequence[int]) -> str:
    r"""The `\track` directive giving each exercise its own system (melete#138).

    One `systemslayout` property per exercise, each its bar count, so alphaTab
    breaks a new system at every exercise boundary instead of running short
    exercises together three-bars-to-a-system. Emitted on a single, unnamed track
    so it configures the book's one track rather than adding a second. See
    `SYSTEMS_LAYOUT_PROPERTY` for why this must be track-level, not score-level.
    """
    counts = " ".join(str(count) for count in bar_counts)
    return f'\\track "" {{ {SYSTEMS_LAYOUT_PROPERTY} {counts} }}'


def _header(title: str, subtitle: str | None, score: Score) -> list[str]:
    r"""The alphaTex metadata block, terminated by the lone `.`.

    The title, an optional subtitle (the session's date and instrument), the
    tuning and the bass instrument. The per-exercise directives (meter, key,
    clef, tempo) live in the bar stream, not here, so a book's exercises can each
    carry their own.
    """
    lines = [f"\\title {_quoted(title)}"]
    if subtitle is not None:
        lines.append(f"\\subtitle {_quoted(subtitle)}")
    lines += [
        _tuning_line(score),
        f"\\instrument({INSTRUMENT_BASS})",
        ".",
    ]
    return lines


def emit_score(score: Score) -> str:
    """One exercise as a standalone alphaTex document.

    A complete score: the metadata header, then the exercise's bars separated by
    `|`. `score.instruction` is not read here and never appears — it is the
    session's, not an exercise's (spec §12).
    """
    lines = _header(score.title, None, score)
    bars = _exercise_bars(score, None)
    lines.append(f" {BAR_SEPARATOR} ".join(bars))
    return "\n".join(lines) + "\n"


def emit_book(scores: Sequence[Score], cover: Cover) -> str:
    """A day's session as one alphaTex document: several exercises in a row.

    One score whose exercises are `\\section`-delimited, so the day is a single
    `.gp`. The cover carries the session title and the date/instrument subtitle;
    each exercise is named `N. <title>` by its section marker and sets its own
    meter, key, clef and tempo (spec §12). Bars are joined by `|` throughout,
    across exercise boundaries as well — alphaTab starts a new bar only at a `|`.

    A `\\track` systems-layout directive precedes the bars, one entry per exercise
    holding that exercise's bar count, so alphaTab gives each exercise its own
    system rather than running short ones together and overprinting their
    `\\section` titles (melete#138; see `SYSTEMS_LAYOUT_PROPERTY`).
    """
    if not scores:
        msg = "a book needs at least one exercise; a cover with no exercises is not a session"
        raise ValueError(msg)

    subtitle = f"{cover.date} - {cover.instrument}"
    lines = _header(SESSION_TITLE, subtitle, scores[0])

    bars: list[str] = []
    layout: list[int] = []
    for number, score in enumerate(scores, start=1):
        exercise_bars = _exercise_bars(score, f"{number}. {score.title}")
        layout.append(len(exercise_bars))
        bars += exercise_bars

    lines.append(_systems_layout_line(layout))
    lines.append(f" {BAR_SEPARATOR} ".join(bars))
    return "\n".join(lines) + "\n"
