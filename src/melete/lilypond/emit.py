r"""Score to LilyPond source text (spec §4, §10, §12).

This module is a pass-through. It receives a `Score` — pitches, string and
fret positions, and **written** durations — and turns it into LilyPond source.
It never learns what a Dorian mode is, and it never learns that a LilyPond
binary exists: `render` is the only module aware of the binary (spec §4), and
nothing here shells out or touches the filesystem.

## Written durations arrive already writable (decision #16)

`Note.duration` is the engraved value and `Tuplet.ratio` supplies the scaling,
so a triplet of eighths is three `Note`s of `1/8` inside a `\tuplet 3/2 { }`.
`duration_token` therefore has no arithmetic to undo, and it **raises** on a
duration with no notehead. That raise is the contract enforced at the
boundary: a sounding triplet eighth is `1/12`, there is no twelfth note, and a
pipeline that ever stored sounding time would fail here rather than silently
engrave the wrong note value.

## Two conventions are reversed, and both bite silently

**Strings.** The IR indexes from 0 as the lowest; LilyPond numbers from 1 as
the highest. `lily_string_number` is the only place that mapping exists.

**Octaves.** Bass guitar is written an octave above its sound. Everything
emitted here — the notes *and* the `stringTunings` chord — is transposed up by
`_WRITTEN_OCTAVE`, so every pitch in the generated source is the **written**
pitch. The two must move together: LilyPond derives each fret number from the
note's pitch against the declared tuning, so a transposition applied to one and
not the other would put every fret number twelve semitones out while the
tablature still looked like music.

**The clef must therefore not transpose as well** (issue #58). This module
emitted `\clef "bass_8"`, on the reading that the `_8` *described* the octave
already applied. It does not describe it, it performs it: an octavated clef
moves the staff's reference an octave down, which prints a given pitch an
octave *higher* than the plain clef does. LilyPond's own
`bass-six-string-tuning` is `<b,,, e,, a,, d, g, c>` — sounding pitch — and is
paired with `bass_8` for exactly that reason. Transposing the source *and*
octavating the clef applied the same octave twice and drew every exercise two
octaves above its sound, with the tablature correct throughout, so the sheet
read as music and merely accumulated ledger lines. Both accepted clefs are
therefore plain, which is also how published bass material is written: the
reader takes the octave off once, by the convention, not from a marking.

## The clef is chosen from the written range (spec §10, issue #58)

A six-string bass covers four octaves, and an exercise high on the neck can sit
far enough above the bass staff that the notation is unreadable while the
tablature reads perfectly — bass clef is simply the wrong clef for that
register. `_clef` therefore picks the clef that needs **fewer ledger lines**
over the notes the exercise actually prints, counting them the way an engraver
does, and leaves bass in place on a tie. Bass is the instrument's home clef, so
treble has to be strictly better before a reader is asked to change clef; middle
C is exactly one ledger line from each staff and stays in bass.

Counting rather than thresholding is what makes a wide exercise come out right.
A passage that reaches high but also touches the open B string would be pushed
into treble by any "highest note above *x*" rule and would then need more ledger
lines below than it saved above. One number, measured over the whole exercise,
answers both cases with no threshold to tune.

**The count is over staff positions, not pitches.** A ledger line is a matter of
where a notehead sits, which is a function of the letter and the letter's
octave — see the `SpelledPitch` warning below — and never of the semitone.

## Spelling is asked for, never decided here (spec §10a)

`theory.spell` returns notation-neutral `SpelledPitch` values and this module
writes them down in LilyPond's Dutch note names. The emitter still never learns
what a Dorian mode is; it learns only that `\dorian` is the keyword LilyPond
spells one with, which is LilyPond knowledge and belongs here.

**`SpelledPitch.octave` is the letter's octave, not the pitch's**, and the two
differ whenever a spelling crosses the C boundary — a C♭ that sounds a B, a B♯
that sounds a C. There are 42 such notes across the 12x27 sweep. It is used
verbatim and is never recomputed from `Note.pitch`: deriving it from the
sounding pitch would put every one of those notes an octave wrong on the staff
while the tablature stayed right and every test still passed, which is the
original defect's failure mode exactly.

**The tab staff spells keylessly, and that is the boundary, not a shortcut.** A
fret number is a function of pitch, and F♯ and G♭ are the same pitch, so a
change of key cannot move a fret. Feeding the tab staff the key's spelling would
make its source vary with a change that cannot affect it; §10a requires instead
that a spelling change leave the tab staff untouched, and §14 asserts it. The
two staves therefore carry the same pitches under different names — the notation
staff in the key, the tab staff by direction — and LilyPond derives identical
frets from both.

## The staff mode is a branch, not a flag (spec §10)

`TabStaff` suppresses stems and beams by default, assuming a notation staff
above supplies the rhythm. In `tab` mode there is no staff above, so the tab
staff stands alone: it asks for `\tabFullNotation`, keeps its fingerings, and
carries the tempo mark that the notation staff would otherwise hold.

## Instructional prose is cover-page only (spec §12, decision #10)

`Score.instruction` is read by `emit_book` and by nothing else. It never
reaches an exercise page, where it would compete with the notes.
"""

from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING

from melete import theory, vocabulary

# The accepted staff modes are taken from `config` rather than restated here.
# §10's switch has to mean the same thing to the loader that validates it and
# to the emitter that branches on it, and two tuples that must agree are the
# drift decision #19 exists to prevent.
from melete.config import STAVES
from melete.score import Note, Tuplet, notes

if TYPE_CHECKING:
    from collections.abc import Sequence

    from melete.score import Score, Voice

#: Declared in every emitted file. LilyPond warns loudly without one and
#: `convert-ly` reads it, so it is pinned to the oldest release melete targets
#: — Debian trixie's 2.24 series — rather than to whatever is installed.
LILYPOND_VERSION = "2.24.0"

#: Bass guitar sounds an octave below its notation. Notes and tunings are both
#: written up by this, and the clef must not apply it a second time — see the
#: module docstring.
_WRITTEN_OCTAVE = 12

#: LilyPond's unmarked octave: `c` is C3 and `c'` is middle C, so a
#: `SpelledPitch` in octave 3 needs no `'` or `,`. The octave being counted is
#: the **letter's**, which is what `theory` reports and what a staff means.
_REFERENCE_OCTAVE = 3

#: Voice items per line of generated source. §12 keeps the `.ly` on disk for
#: inspection, and a hundred notes on one line is not inspectable.
_ITEMS_PER_LINE = 8

#: Written duration as a multiple of the undotted note it augments. A dot adds
#: half, a second dot adds a quarter; three dots are deliberately absent — see
#: `duration_token`.
_AUGMENTATIONS: tuple[tuple[int, Fraction], ...] = (
    (0, Fraction(1)),
    (1, Fraction(3, 2)),
    (2, Fraction(7, 4)),
)

#: The axes §12 prints as one musical phrase — "D Dorian", "D minor 7th" —
#: rather than as separate comma-separated items.
_TONAL_AXES = ("scale_type", "quality")

_PREAMBLE = "% Generated by melete. Edits here are overwritten by the next run."

#: `theory`'s scale identifiers in the keywords LilyPond spells a signature
#: with. It maps the seven tier-1 modes, which is also every tier-2 parent:
#: §10a gives every parented scale either ionian or aeolian, so a tier-2 key
#: resolves through its parent into this same table and prints `\major` or
#: `\minor`. Ionian and aeolian are written that way in both roles, because
#: `\key c \major` is what a reader expects to see and `\key c \ionian`
#: engraves identically.
#:
#: Tier 3 is absent, and its absence is the rule rather than an oversight: a
#: symmetric scale has no parent to resolve through and LilyPond has no
#: signature for a six- or eight-note scale, so a lookup that misses is exactly
#: the case that prints no signature at all.
_LILYPOND_MODES: dict[str, str] = {
    "ionian": "major",
    "dorian": "dorian",
    "phrygian": "phrygian",
    "lydian": "lydian",
    "mixolydian": "mixolydian",
    "aeolian": "minor",
    "locrian": "locrian",
}


#: The seven letters in staff order from C, so that a position on a staff is
#: `letters * octave + index`. A staff position counts *diatonic steps*, which
#: is why this is a string of letters and not a count of semitones: C♭5 and B4
#: sound the same note and sit one step apart on the page.
_STAFF_LETTERS = "CDEFGAB"


@dataclass(frozen=True)
class _Clef:
    """One clef: its LilyPond name, and where its outermost lines sit.

    Neither is octavated, and that is the invariant rather than a coincidence:
    the source already carries written pitch, so a clef that transposed would
    apply the octave twice (see the module docstring).
    """

    name: str
    bottom_line: int
    top_line: int


def _line(letter: str, octave: int) -> int:
    """The staff position of a line, named by the note that sits on it."""
    return len(_STAFF_LETTERS) * octave + _STAFF_LETTERS.index(letter)


#: The bass staff, from the G below middle C on its bottom line to the A on its
#: top line. The instrument's home clef, and the one a tie is settled in favour
#: of.
_BASS = _Clef(name="bass", bottom_line=_line("G", 2), top_line=_line("A", 3))

#: The treble staff, bottom line E above middle C to top line F. Chosen only
#: when the exercise genuinely reads better in it.
_TREBLE = _Clef(name="treble", bottom_line=_line("E", 4), top_line=_line("F", 5))


@dataclass(frozen=True)
class Cover:
    """The cover page's own content: the date and the instrument (spec §12).

    Everything else on the page — one entry per exercise, in plain language —
    is derived from the scores themselves, so the two cannot drift apart.
    """

    date: str
    instrument: str


# --------------------------------------------------------------------------
# The two units that are wrong silently
# --------------------------------------------------------------------------


def duration_token(written: Fraction) -> str:
    r"""The LilyPond duration for one **written** value: `1/4` is `"4"`.

    Dots are recovered by division rather than by table: `3/8` is `4.` and
    `7/16` is `4..`. A value that is not a power-of-two note with zero, one or
    two dots has no notehead and raises.

    The raise is the point. Sounding durations inside a tuplet are not
    representable — a triplet eighth is `1/12` — so this is where the
    written-duration contract of the `score` seam is enforced (decision #16).
    Three dots are excluded with the same intent: LilyPond can engrave one, but
    nothing upstream produces one, and widening the accepted set quietly is how
    an unwritable duration eventually reaches the page.
    """
    for dots, augmentation in _AUGMENTATIONS:
        base = written / augmentation
        if base.numerator == 1 and not base.denominator & (base.denominator - 1):
            return f"{base.denominator}" + "." * dots

    msg = (
        f"{written} is not a representable note value. Durations are the "
        f"written value (decision #16): a power-of-two note, optionally with "
        f"one or two dots. A sounding triplet eighth is 1/12 and there is no "
        f"twelfth note — store 1/8 inside a Tuplet and let the ratio scale it."
    )
    raise ValueError(msg)


def lily_string_number(index: int, string_count: int) -> int:
    """The LilyPond string number for an IR string index.

    **The two conventions are reversed.** The IR indexes strings from 0 as the
    *lowest* (spec §5); LilyPond numbers them from 1 as the *highest*. On a
    six-string bass, IR index 5 is LilyPond string 1 and IR index 0 is string
    6. The mapping is not the identity anywhere, and getting it wrong puts
    every fret number on the wrong line while the tablature still reads as
    music — which is why it is a named function with its own test rather than
    an expression inline.

    An index the instrument has no string for raises rather than wrapping: a
    negative index would address the tuning from the top and engrave plausible
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
# Notes and voices
# --------------------------------------------------------------------------


def _quoted(text: str) -> str:
    """A LilyPond string literal. Backslash first, or it escapes the escapes."""
    escaped = text.replace("\\", r"\\").replace('"', r"\"")
    return f'"{escaped}"'


def _note_name(letter: str, alteration: int) -> str:
    """A letter and its alteration in LilyPond's default (Dutch) note names.

    One `-is` per sharp and one `-es` per flat: F♯ is `fis`, C𝄪 is `cisis`,
    B𝄫 is `beses`. The two repetitions are deliberately unguarded — an
    alteration cannot be positive and negative at once, so exactly one of them
    is ever non-empty, and a natural produces neither.
    """
    return letter.lower() + "is" * alteration + "es" * -alteration


def _pitch_token(spelled: theory.SpelledPitch) -> str:
    """One spelled pitch as a LilyPond note name with its octave marks.

    `octave` is used exactly as `theory` reports it, because it is the
    **letter's** octave and that is what a staff position means. C♭5 sounds a
    B4 and is written a letter higher than the pitch it sounds; recomputing the
    octave from the sounding pitch would engrave it, and 41 other notes across
    the 12x27 sweep, an octave low. See the module docstring.
    """
    distance = spelled.octave - _REFERENCE_OCTAVE
    return _note_name(spelled.letter, spelled.alteration) + "'" * distance + "," * -distance


def _written_pitch(pitch: int, key: theory.Key | None) -> theory.SpelledPitch:
    """One IR pitch spelled for `key`, at written pitch (an octave up).

    Transposing before spelling rather than after is what keeps the octave
    honest: `spell` decides the letter from the pitch class, which the octave
    does not change, and then reports the octave that letter sits in. There is
    no octave arithmetic left to get wrong here.
    """
    return theory.spell(key, [pitch + _WRITTEN_OCTAVE])[0]


def _note_token(note: Note, string_count: int, key: theory.Key | None) -> str:
    r"""One note: pitch, duration, string, fingering, accent — in that order.

    The string indication is emitted even in `notation` mode: both staves are
    built from the same `Note`, and the notation staff omits the `StringNumber`
    grob rather than being given different music.
    """
    token = _pitch_token(_written_pitch(note.pitch, key)) + duration_token(note.duration)
    token += f"\\{lily_string_number(note.string, string_count)}"
    if note.finger is not None:
        token += f"-{note.finger}"
    if note.accent:
        token += "->"
    return token


def _voice_tokens(voice: Voice, string_count: int, key: theory.Key | None) -> list[str]:
    r"""One token per voice item; a tuplet is one item, braces and all.

    `Tuplet.ratio` maps straight onto `\tuplet 3/2 { ... }` with no arithmetic,
    which is exactly what the written-duration contract buys (decision #16).
    """
    tokens = []
    for item in voice:
        if isinstance(item, Tuplet):
            numerator, denominator = item.ratio
            inner = " ".join(_note_token(note, string_count, key) for note in item.notes)
            tokens.append(f"\\tuplet {numerator}/{denominator} {{ {inner} }}")
        else:
            tokens.append(_note_token(item, string_count, key))
    return tokens


def _music_lines(score: Score, indent: str, key: theory.Key | None) -> list[str]:
    r"""The music for one staff: accidental style, meter, the notes, final bar.

    `key` is the staff's spelling, not the score's: the notation staff passes
    `score.key` and the tab staff passes `None`, for the reason in the module
    docstring. Both then hold the same pitches.

    `\accidentalStyle forget` is here rather than on the notation staff so it
    is present in every staff mode, and it is what makes **both** of §10's
    settings correct (decision #27, superseding #9). Forgetting means every
    accidental is engraved against the key signature rather than against what
    came earlier in the bar: with a signature, a diatonic tone prints nothing
    and an altered one prints on every occurrence — which is how melodic and
    harmonic minor are written by hand; with no signature, every altered tone
    prints, which is what §10's `false` setting asks for. In a tab staff it is
    inert, which is the correct amount of effect.

    The final `\bar "|."` closes the short last measure §7 accepts. It is not
    padded with rests — a player would read rests as musical content.
    """
    beats, beat_value = score.time_signature
    lines = [
        f"{indent}\\accidentalStyle forget",
        f"{indent}\\time {beats}/{beat_value}",
    ]
    tokens = _voice_tokens(score.voice, len(score.instrument.tuning), key)
    for start in range(0, len(tokens), _ITEMS_PER_LINE):
        lines.append(indent + " ".join(tokens[start : start + _ITEMS_PER_LINE]))
    lines.append(f'{indent}\\bar "|."')
    return lines


def _tempo_line(score: Score, indent: str) -> str:
    """The metronome mark, in the beat unit the time signature names.

    §12 prints the tempo range on the cover page; this puts the same range over
    the exercise, which is the one annotation a player reads from the stand.
    """
    _, beat_value = score.time_signature
    slowest, fastest = score.tempo_range
    return f"{indent}\\tempo {beat_value} = {slowest} - {fastest}"


# --------------------------------------------------------------------------
# Staves
# --------------------------------------------------------------------------


def _key_lines(score: Score, indent: str, *, key_signatures: bool) -> list[str]:
    r"""`\key <tonic> <mode>`, or nothing at all (spec §10, §10a).

    Three cases print no signature, and each is a real answer rather than a
    fallback. `key_signatures` false is §10's second setting: no asserted tonal
    centre, and the notes still spelled for the key. `score.key` of `None` is an
    exercise with no tonal centre, which is what the chromatic family produces.
    A tier-3 scale has no parent to resolve through and no LilyPond keyword of
    its own, so the lookup misses — six notes have no key signature.

    Tiers 1 and 2 are one expression because tier 2 *is* "print the parent's":
    a parented scale resolves to ionian or aeolian, a tier-1 mode resolves to
    itself, and the same table answers both.
    """
    if not key_signatures or score.key is None:
        return []

    mode = _LILYPOND_MODES.get(theory.parent_scale(score.key.scale_type) or score.key.scale_type)
    if mode is None:
        return []

    letter, alteration = theory.tonic_spelling(score.key)
    return [f"{indent}\\key {_note_name(letter, alteration)} \\{mode}"]


def _staff_position(spelled: theory.SpelledPitch) -> int:
    """Where one written pitch sits on a staff, in diatonic steps.

    Built from the **letter and the letter's octave**, exactly as `_pitch_token`
    is and for the same reason: a notehead's height is a property of its name,
    not of the pitch it sounds. Deriving it from `Note.pitch` would place the 42
    spellings that cross the C boundary a step wrong and could tip a clef
    decision — silently, since the tablature would still be right.
    """
    return len(_STAFF_LETTERS) * spelled.octave + _STAFF_LETTERS.index(spelled.letter)


def _ledger_lines(clef: _Clef, position: int) -> int:
    """How many ledger lines one note needs on `clef`.

    Ledger lines are a third apart, so a note two diatonic steps past the
    outermost line needs one and the note between them is drawn on a space
    above or below without adding another. Integer division is that rule.
    """
    if position > clef.top_line:
        return (position - clef.top_line) // 2
    if position < clef.bottom_line:
        return (clef.bottom_line - position) // 2
    return 0


def _clef(score: Score, key: theory.Key | None) -> _Clef:
    """The clef this exercise reads better in (spec §10, issue #58).

    Bass unless treble needs **strictly fewer** ledger lines across the whole
    exercise. The comparison is the engraver's own criterion and needs no
    threshold; preferring bass on a tie is what keeps the instrument's home clef
    in place for anything that does not clearly deserve otherwise.

    `key` is the staff's spelling, so the positions counted here are the
    positions the reader will actually see.
    """
    positions = [_staff_position(_written_pitch(note.pitch, key)) for note in notes(score.voice)]
    counts = {clef: sum(_ledger_lines(clef, at) for at in positions) for clef in (_BASS, _TREBLE)}
    return _TREBLE if counts[_TREBLE] < counts[_BASS] else _BASS


def _notation_staff(score: Score, indent: str, *, key_signatures: bool) -> list[str]:
    r"""The standard-notation staff, always the top staff when it is present.

    The key signature belongs to this staff alone. A `TabStaff` prints no
    signature, and putting one in the tab music would make the tab source vary
    with a change that cannot move a fret — the boundary §10a draws.

    `\omit StringNumber` because the string indications on every note exist for
    the tab staff; printed here they would be circled numerals over music that
    already says where to play.

    The clef is chosen here and nowhere else, which is what keeps it off the tab
    staff: a fret is a function of pitch, and no clef can move one (§14).
    """
    return [
        f"{indent}\\new Staff \\with {{",
        f"{indent}  \\omit StringNumber",
        f"{indent}}} {{",
        f"{indent}  \\clef {_quoted(_clef(score, score.key).name)}",
        *_key_lines(score, f"{indent}  ", key_signatures=key_signatures),
        _tempo_line(score, f"{indent}  "),
        *_music_lines(score, f"{indent}  ", score.key),
        f"{indent}}}",
    ]


def _string_tuning(score: Score) -> str:
    """The instrument's tuning as a LilyPond chord, low string first.

    Written an octave up to match the notes, for the reason in the module
    docstring: LilyPond derives every fret number from pitch against this.

    Spelled keylessly, because a tuning has no key: it is a property of the
    instrument, and an open string does not change its name when the exercise
    changes mode.
    """
    written = (_pitch_token(_written_pitch(pitch, None)) for pitch in score.instrument.tuning)
    return f"\\stringTuning <{' '.join(written)}>"


def _tab_staff(score: Score, indent: str, *, alone: bool) -> list[str]:
    r"""The tablature staff. `alone` is the §10 branch, not a flag.

    With no notation staff above, three things follow from the same fact:
    `TabStaff` must be asked for stems and beams explicitly or the rhythm is
    unreadable, the fingerings have nowhere else to be printed, and the tempo
    mark has no other staff to sit over.

    What does *not* follow from the staff mode is the spelling: the tab staff
    passes no key in either mode, so its body is byte-identical across a change
    of key (§10a, §14). Tablature never consults a spelling and never did — that
    is why the original defect was silent.
    """
    settings = [f"{indent}  stringTunings = {_string_tuning(score)}"]
    if not alone:
        settings.append(f"{indent}  \\omit Fingering")

    prelude = []
    if alone:
        prelude.append(f"{indent}  \\tabFullNotation")
        prelude.append(_tempo_line(score, f"{indent}  "))

    return [
        f"{indent}\\new TabStaff \\with {{",
        *settings,
        f"{indent}}} {{",
        *prelude,
        *_music_lines(score, f"{indent}  ", None),
        f"{indent}}}",
    ]


def _check_staves(staves: str) -> None:
    """Reject an unknown staff mode by name (§13: never a silent fallback)."""
    if staves not in STAVES:
        msg = f"unknown staff mode {staves!r}; accepted: {list(STAVES)}"
        raise ValueError(msg)


def _score_block(
    score: Score, staves: str, indent: str, *, piece: str | None, key_signatures: bool
) -> list[str]:
    r"""One `\score { }`: the staves §10 asks for, and nothing else.

    `piece` titles the score from inside a book, where a `\header` `title`
    belongs to the bookpart rather than to one exercise.
    """
    lines = [f"{indent}\\score {{"]
    if piece is not None:
        lines += [
            f"{indent}  \\header {{",
            f"{indent}    piece = {_quoted(piece)}",
            f"{indent}  }}",
        ]

    lines.append(f"{indent}  <<")
    inner = f"{indent}    "
    if staves in ("both", "notation"):
        lines += _notation_staff(score, inner, key_signatures=key_signatures)
    if staves in ("both", "tab"):
        lines += _tab_staff(score, inner, alone=staves == "tab")

    lines += [f"{indent}  >>", f"{indent}  \\layout {{ }}", f"{indent}}}"]
    return lines


# --------------------------------------------------------------------------
# The cover page (spec §12)
# --------------------------------------------------------------------------


def _pitch_class_name(value: object, key: theory.Key | None) -> str:
    """A `root` parameter as a note name, spelled for the exercise's key.

    Spelled through `theory.spell` — the same entry point the staff goes
    through, which for the tonic is `theory.tonic_spelling` — so the cover page
    cannot call an exercise G♭ Dorian while the staff engraves F♯ Dorian. That
    disagreement is the original defect in miniature, and deriving both names
    from one function is what makes it unreachable rather than merely unlikely.

    A key of `None` spells by direction, exactly as the staff does for the same
    score. A non-integer `root` raises (§13): there is no fallback name.

    **The root arrives as an absolute pitch, not as a pitch class.** §7's axis
    is a pitch class and the pool is written in pitch classes, but
    `selection._realized` places it on the instrument before the family — and
    therefore the log and this page — ever see it, because a family needs the
    pitch the strings can actually reach. Only the letter is printed, and a
    letter is a property of the pitch class, so A1 and A4 name the same "A"
    here; the octave is on the staff, where it belongs.
    """
    if not isinstance(value, int):
        msg = f"cover entry: root must be a pitch integer, got {value!r}"
        raise TypeError(msg)

    spelled = theory.spell(key, [value])[0]
    return spelled.letter + "#" * spelled.alteration + "b" * -spelled.alteration


def _tonal_phrase(params: dict[str, object], key: theory.Key | None) -> str:
    """The tonal axes as §12's single phrase: "F# Dorian", or "D minor 7th".

    Emitted ahead of the rest regardless of the order `params` happens to
    carry, because "D, Dorian" is not what a player reads.
    """
    words = []
    if "root" in params:
        words.append(_pitch_class_name(params["root"], key))
    for axis in _TONAL_AXES:
        if axis in params:
            words.append(vocabulary.display(axis, str(params[axis])))
    return " ".join(words)


def _phrase(axis: str, value: object) -> str:
    """One parameter in plain language.

    Axes in the registry are rendered through it, and an identifier it does not
    know raises there (§13, decision #19). The rest are the range axes
    `vocabulary` deliberately does not enumerate — fret numbers, octave counts,
    string sets — which are printed as themselves rather than dropped.
    """
    if axis in vocabulary.AXES:
        return vocabulary.display(axis, str(value))
    return f"{axis.replace('_', ' ')} {value}"


def _cover_entry(number: int, score: Score) -> list[str]:
    """One numbered cover entry, plus the focus cue when the family gave one."""
    phrases = []
    tonal = _tonal_phrase(score.params, score.key)
    if tonal:
        phrases.append(tonal)
    phrases += [
        _phrase(axis, value)
        for axis, value in score.params.items()
        if axis != "root" and axis not in _TONAL_AXES
    ]
    slowest, fastest = score.tempo_range
    phrases.append(f"{slowest}-{fastest} bpm")

    lines = [f"    \\markup \\wordwrap-string #{_quoted(f'{number}. ' + ', '.join(phrases))}"]
    if score.instruction:
        lines.append(f"    \\markup \\italic \\wordwrap-string #{_quoted(score.instruction)}")
    lines.append("    \\markup \\vspace #1")
    return lines


def _cover_bookpart(scores: Sequence[Score], cover: Cover) -> list[str]:
    r"""The cover page as a markup bookpart in the same book (spec §12).

    A bookpart rather than a separate document so the day's output stays one
    PDF from one render call, with no text-to-PDF dependency anywhere.
    """
    lines = [
        "  \\bookpart {",
        "    \\markup \\vspace #3",
        f"    \\markup \\fill-line {{ \\fontsize #6 \\bold {_quoted('Practice session')} }}",
        "    \\markup \\vspace #1",
        f"    \\markup \\fill-line {{ {_quoted(f'{cover.date} — {cover.instrument}')} }}",
        "    \\markup \\vspace #3",
    ]
    for number, score in enumerate(scores, start=1):
        lines += _cover_entry(number, score)
    lines.append("  }")
    return lines


# --------------------------------------------------------------------------
# The two entry points
# --------------------------------------------------------------------------


def emit_score(score: Score, staves: str = "both", *, key_signatures: bool = True) -> str:
    """One exercise as a standalone LilyPond document.

    §12 keeps the generated source per exercise as well as for the book, so
    this is a complete file rather than a fragment. `score.instruction` is not
    read here and never appears in the result.

    `key_signatures` is §10's notation convention and selects between two
    correct notations (decision #27): print the signature and spell
    diatonically, or print no signature and give every altered tone an explicit
    accidental. It never touches the spelling — F♯ is spelled F♯ either way,
    and the setting that used to spell it G♭ is the defect §10a exists to fix.
    """
    _check_staves(staves)
    lines = [
        _PREAMBLE,
        f'\\version "{LILYPOND_VERSION}"',
        "",
        "\\header {",
        f"  title = {_quoted(score.title)}",
        "  tagline = ##f",
        "}",
        "",
        *_score_block(score, staves, "", piece=None, key_signatures=key_signatures),
    ]
    return "\n".join(lines) + "\n"


def emit_book(
    scores: Sequence[Score], cover: Cover, staves: str = "both", *, key_signatures: bool = True
) -> str:
    """A day's session as one LilyPond book: the cover page, then the exercises.

    One document from one render call (§12, decision #11). The cover carries
    the instructional prose; the exercise pages carry a title and the tempo and
    nothing else (decision #10).
    """
    _check_staves(staves)
    if not scores:
        msg = "a book needs at least one exercise; a cover page with no exercises is not a session"
        raise ValueError(msg)

    lines = [
        _PREAMBLE,
        f'\\version "{LILYPOND_VERSION}"',
        "",
        "\\header {",
        "  tagline = ##f",
        "}",
        "",
        "\\book {",
        *_cover_bookpart(scores, cover),
        "",
        "  \\bookpart {",
    ]
    for number, score in enumerate(scores, start=1):
        if number > 1:
            lines.append("")
        lines += _score_block(
            score,
            staves,
            "    ",
            piece=f"{number}. {score.title}",
            key_signatures=key_signatures,
        )
    lines += ["  }", "}"]
    return "\n".join(lines) + "\n"
