r"""Tests for the tapping note-effects the emitter adds (epic #67, Task D1).

`_note_token` translates a note's `hand` and `attack` (epic #67, spec §4) into
alphaTex note effects, using the tokens Task A1's spike confirmed against
`@coderline/alphatab` 1.8.4 (`docs/reports/alphatex-tapping-effects.md`):

* a right-hand tap `(RIGHT, TAPPED)` -> `tt`;
* a left-hand tap `(LEFT, TAPPED)` -> `lht`;
* a hammer-on/pull-off -> a single `h` on the **origin** note (the note before a
  `SLURRED` note on the same string and hand), alphaTab inferring the direction
  from the next note's pitch; and
* per-hand fingering — a right-hand note takes `rf <n>` where a left-hand note
  takes `lf <n>`, both carrying the same `+1` finger offset.

A default `(LEFT, PLUCKED)` note must emit exactly as before — the golden emitter
tests (`test_alphatex_emit.py`) are that guard; the assertions here pin the new
tokens.
"""

from __future__ import annotations

from fractions import Fraction

from melete.alphatab.emit import emit_score
from melete.instrument import resolve_profile
from melete.score import Attack, Hand, Note, Score

_BASS6 = resolve_profile("bass6")
_HALF = Fraction(1, 2)


def _note(
    pitch: int,
    string: int,
    duration: Fraction = _HALF,
    finger: int | None = None,
    *,
    hand: Hand = Hand.LEFT,
    attack: Attack = Attack.PLUCKED,
    accent: bool = False,
) -> Note:
    """A `Note` whose fret satisfies `pitch == tuning[string] + fret`."""
    return Note(
        pitch=pitch,
        string=string,
        fret=pitch - _BASS6.tuning[string],
        duration=duration,
        finger=finger,
        accent=accent,
        hand=hand,
        attack=attack,
    )


def _score(*voice: Note) -> Score:
    """One 4/4 exercise wrapping the given notes; keyless so no `acc` intrudes."""
    return Score(
        title="tapping",
        instruction="",
        instrument=_BASS6,
        time_signature=(4, 4),
        tempo_range=(80, 100),
        voice=list(voice),
        key=None,
    )


def _tokens(score: Score) -> list[str]:
    """The beat tokens of the single emitted bar, directives stripped.

    The bar body is split on spaces *at brace depth 0* so a multi-field effect
    (`{lf 2}`) stays inside its beat; the leading `\\...` directives (and their
    plain-word arguments, e.g. the `4 4` of `\\ts 4 4`) carry no `.` separating a
    fret from a string, so keeping only the tokens that contain a `.` leaves
    exactly the beats.
    """
    body = emit_score(score).splitlines()[-1]
    fields: list[str] = []
    depth = 0
    current = ""
    for char in body:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        if char == " " and depth == 0:
            if current:
                fields.append(current)
            current = ""
        else:
            current += char
    if current:
        fields.append(current)
    return [field for field in fields if "." in field]


def _effects(token: str) -> list[str]:
    """The whitespace-separated fields of a beat token's note-effect brace.

    A beat is `<fret>.<string>{note-effects}.<dur>{beat-effects}`; this returns
    the fields of the *first* brace (the note effects) so membership tests are
    exact — `"h" in _effects(tok)` is true for a bare `h` token but not for the
    `h` inside `lht`.
    """
    open_brace = token.find("{")
    if open_brace == -1:
        return []
    close_brace = token.find("}", open_brace)
    return token[open_brace + 1 : close_brace].split()


def test_right_hand_tap_emits_tt_and_right_fingering() -> None:
    effects = _effects(
        _tokens(
            _score(
                _note(45, 3, finger=2, hand=Hand.RIGHT, attack=Attack.TAPPED),
                _note(33, 2),
            )
        )[0]
    )
    assert "tt" in effects
    assert "rf" in effects
    assert effects[effects.index("rf") + 1] == "3"  # melete finger 2 -> alphaTab 3
    assert "lht" not in effects
    assert "lf" not in effects


def test_left_hand_tap_emits_lht_and_keeps_left_fingering() -> None:
    effects = _effects(
        _tokens(
            _score(
                _note(45, 3, finger=2, hand=Hand.LEFT, attack=Attack.TAPPED),
                _note(33, 2),
            )
        )[0]
    )
    assert "lht" in effects
    assert "lf" in effects
    assert effects[effects.index("lf") + 1] == "3"
    assert "tt" not in effects
    assert "rf" not in effects


def test_hammer_pull_emits_h_on_origin_only() -> None:
    # Same string, same hand: note 0 is the origin, note 1 is SLURRED.
    tokens = _tokens(
        _score(
            _note(38, 3, finger=1, hand=Hand.LEFT, attack=Attack.TAPPED),
            _note(40, 3, finger=3, hand=Hand.LEFT, attack=Attack.SLURRED),
        )
    )
    assert "h" in _effects(tokens[0])  # origin carries the hammer/pull marker
    assert "h" not in _effects(tokens[1])  # the slurred destination does not
    # The slurred destination is neither a fresh tap nor left-tapped.
    assert "tt" not in _effects(tokens[1])
    assert "lht" not in _effects(tokens[1])


def test_no_h_when_next_note_changes_string() -> None:
    tokens = _tokens(
        _score(
            _note(38, 3, finger=1, hand=Hand.LEFT, attack=Attack.TAPPED),
            _note(43, 4, finger=3, hand=Hand.LEFT, attack=Attack.SLURRED),
        )
    )
    assert "h" not in _effects(tokens[0])


def test_no_h_when_next_note_changes_hand() -> None:
    tokens = _tokens(
        _score(
            _note(38, 3, finger=1, hand=Hand.LEFT, attack=Attack.TAPPED),
            _note(40, 3, finger=1, hand=Hand.RIGHT, attack=Attack.SLURRED),
        )
    )
    assert "h" not in _effects(tokens[0])


def test_right_hand_plucked_note_uses_rf_not_lf() -> None:
    effects = _effects(
        _tokens(
            _score(
                _note(45, 3, finger=1, hand=Hand.RIGHT, attack=Attack.PLUCKED),
                _note(33, 2),
            )
        )[0]
    )
    assert "rf" in effects
    assert effects[effects.index("rf") + 1] == "2"
    assert "lf" not in effects


def test_default_plucked_note_carries_no_tapping_tokens() -> None:
    effects = _effects(_tokens(_score(_note(45, 3, finger=2), _note(33, 2)))[0])
    assert "tt" not in effects
    assert "lht" not in effects
    assert "rf" not in effects
    assert "h" not in effects
    # A default note keeps left-hand fingering exactly as before.
    assert "lf" in effects
    assert effects[effects.index("lf") + 1] == "3"


def test_run_marks_h_on_every_note_but_the_last() -> None:
    # A tapped-then-slurred run on one string: T S S -> h on notes 0 and 1.
    tokens = _tokens(
        _score(
            _note(40, 3, Fraction(1, 4), finger=1, hand=Hand.LEFT, attack=Attack.TAPPED),
            _note(42, 3, Fraction(1, 4), finger=2, hand=Hand.LEFT, attack=Attack.SLURRED),
            _note(44, 3, Fraction(1, 4), finger=3, hand=Hand.LEFT, attack=Attack.SLURRED),
            _note(33, 2, Fraction(1, 4)),
        )
    )
    assert "h" in _effects(tokens[0])
    assert "h" in _effects(tokens[1])
    assert "h" not in _effects(tokens[2])  # last note of the run: nothing to hammer into
    assert "h" not in _effects(tokens[3])
