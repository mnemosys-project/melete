"""The two-hand tapped-journey path and the shared legato pass (Task B3, epic #67).

`arpeggios.generate` grows a second placement path: a *triad* quality
(`maj`/`min`/`dim`/`aug`) is walked as a two-hand tapped journey — the universal
`TAP_BOX` tiled up the chord tones and back — while a *seventh* keeps the
one-hand `shape_places` journey unchanged. Every tapped note is `TAPPED` and
carries a `hand`/`finger`; the pitch content is still the triad's own chord
tones.

The shared legato pass (`_shared.derive_legato`) is tested here in isolation:
within one hand's same-string run a follower becomes `SLURRED` only when the
fret changes — a real hammer-on/pull-off (corpus R12, `melete#205`) — while a
same-fret repeat re-taps and stays `TAPPED`; a string or a hand change forces a
fresh `TAPPED`. It is a no-op for the all-tapped triad default (the only
same-string+hand consecutive notes there are the same-fret doubled apex, which
R12 keeps tapped) but must re-derive a correct first-`TAPPED`-per-run for any
voice — even one a fitter lever repeated or dropped, so no `SLURRED` is ever
stranded without a `TAPPED` ahead of it on the same string and hand.
"""

from __future__ import annotations

from fractions import Fraction

import pytest
from conftest import assert_central_invariant, assert_spelling_sounds_correctly, notes_of

from melete import theory
from melete.families._shared import derive_legato
from melete.families.arpeggios import generate as _generate
from melete.instrument import PROFILES
from melete.score import Attack, Hand, Note, Voice

BASS6 = PROFILES["bass6"]  # tuning B0 E1 A1 D2 G2 C3 = 23 28 33 38 43 48; span 4
_OCTAVE = 12
_TRIADS = ("maj", "min", "dim", "aug")

#: R2 — the left-hand root finger mirrors the third's fret gap: middle (2) for a
#: major/augmented third, ring (3) for a minor/diminished third.
_ROOT_FINGER = {"maj": 2, "aug": 2, "min": 3, "dim": 3}

#: E on the low B string (fret 5): a root with room for the box below it (the
#: minor/diminished third sits two frets down) and headroom for the climb.
ROOT = 28

LEFT, RIGHT = Hand.LEFT, Hand.RIGHT
TAPPED, PLUCKED, SLURRED = Attack.TAPPED, Attack.PLUCKED, Attack.SLURRED


def params(quality: str, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "root": ROOT,
        "quality": quality,
        "inversion": "root",
        "pattern": "straight",
    }
    return {**base, **overrides}


def generate(quality: str, **overrides: object):
    return _generate(BASS6, params(quality, **overrides))


def _tiled_chord_tones(quality: str, top: int) -> set[int]:
    """Every chord-tone pitch from the root up to `top`, tiled by the octave."""
    tones = set()
    for octave in range(0, (top - ROOT) // _OCTAVE + 1):
        for pitch in theory.chord_pitches(ROOT, quality):
            tones.add(pitch + _OCTAVE * octave)
    return {pitch for pitch in tones if pitch <= top}


# --------------------------------------------------------------------------
# The tapped journey (in `generate`)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("quality", _TRIADS)
def test_a_triad_taps_every_note_with_both_hands(quality: str) -> None:
    score, _hints = generate(quality)
    notes = notes_of(score)

    assert all(note.attack is TAPPED for note in notes)  # no PLUCKED, no SLURRED
    hands = {note.hand for note in notes}
    assert hands == {LEFT, RIGHT}  # a genuine two-hand shape


@pytest.mark.parametrize("quality", _TRIADS)
def test_a_triad_obeys_the_central_invariant_and_spelling(quality: str) -> None:
    score, _hints = generate(quality)
    assert_central_invariant(score)
    assert_spelling_sounds_correctly(score)


@pytest.mark.parametrize("quality", _TRIADS)
def test_the_tapped_pitch_content_is_the_triad_chord_tones(quality: str) -> None:
    # Spec §10: every emitted pitch is a chord tone, and the whole set of chord
    # tones across the journey's register is covered — the two-hand layout still
    # sounds exactly the triad it names.
    score, _hints = generate(quality)
    pitches = [note.pitch for note in notes_of(score)]

    top = max(pitches)
    assert set(pitches) == _tiled_chord_tones(quality, top)


@pytest.mark.parametrize("quality", _TRIADS)
def test_the_ascending_pass_is_the_clean_tiling_each_pitch_once(quality: str) -> None:
    # The MERGE decision, pinned: the box overlaps by one pitch (box N's
    # octave-root == box N+1's root). The ascending journey emits that shared
    # pitch ONCE, so the ascending pitch sequence is exactly `chord_pitches`
    # tiled — each octave's tones once — a clean multiset with no seam duplicate.
    score, hints = generate(quality)
    assert hints.seam is not None
    ascending = [note.pitch for note in notes_of(score)][: hints.seam + 1]

    # Strictly increasing: no pitch repeats on the way up (the seam is merged,
    # not doubled), and the sequence rises monotonically through the register.
    assert ascending == sorted(ascending)
    assert len(ascending) == len(set(ascending))

    # And it is precisely the chord tones tiled up to the apex.
    top = ascending[-1]
    assert set(ascending) == _tiled_chord_tones(quality, top)


def test_the_shared_octave_pitch_is_one_note_the_upper_box_root() -> None:
    # The deliberate overlap decision, made concrete on E minor. The pitch an
    # octave above the root (root+12) is box N's octave-root (right middle) and
    # box N+1's root (left ring). We realize it as ONE note, stamped as the upper
    # box's root: left hand, ring finger (3) — faithful to B0's tiling rule
    # ("the octave-root becomes the next box's root, retapped by the left ring").
    score, hints = generate("min")
    assert hints.seam is not None
    ascending = notes_of(score)[: hints.seam + 1]

    shared = [note for note in ascending if note.pitch == ROOT + _OCTAVE]
    assert len(shared) == 1  # one note, not two: the seam is merged
    assert shared[0].hand is LEFT
    assert shared[0].finger == 3  # the ring-finger root of the upper box


@pytest.mark.parametrize("quality", _TRIADS)
def test_the_box_stamps_the_quality_aware_left_hand_root_finger(quality: str) -> None:
    # Every box's first note (its root) is left-handed, its finger set by R2 —
    # ring (3) for a min/dim third, middle (2) for a maj/aug third — and the
    # whole journey uses only the box's fingers (index/middle/ring).
    score, _hints = generate(quality)
    notes = notes_of(score)
    assert notes[0].hand is LEFT
    assert notes[0].finger == _ROOT_FINGER[quality]
    assert {note.finger for note in notes} <= {1, 2, 3}


def test_the_journey_strings_and_hands_are_identical_across_the_four_triads() -> None:
    # Quality-agnostic: dim/aug are data, not code paths. Strings and hands are
    # the same for every triad; only the frets (pitches) and the R2 root finger
    # move with the quality.
    structures = {
        quality: [(note.string, note.hand) for note in notes_of(generate(quality)[0])]
        for quality in _TRIADS
    }
    reference = structures["maj"]
    for quality in _TRIADS:
        assert structures[quality] == reference


def test_a_triad_climbs_up_and_back_down() -> None:
    # The journey is up-and-down: the descending half re-taps the apex at the turn
    # and then reverses the ascent, so it returns to where it started (the low root).
    score, hints = generate("maj")
    pitches = [note.pitch for note in notes_of(score)]
    assert hints.seam is not None
    assert pitches[0] == pitches[-1] == ROOT  # starts and ends on the low root
    assert pitches[hints.seam] == max(pitches)  # turns around at the apex
    assert pitches[hints.seam] == pitches[hints.seam + 1]  # the apex is re-tapped (doubled)


_PATTERNS = ("straight", "numeric_1353", "broken", "sweep_ordered")


@pytest.mark.parametrize("quality", _TRIADS)
@pytest.mark.parametrize("pattern", _PATTERNS)
def test_the_tapped_descent_mirrors_the_ascent_symmetrically(quality: str, pattern: str) -> None:
    # R7/R12 (corpus, `melete#205`) / spec §6: the tapped triad journey is an
    # apex-DOUBLED symmetric up-and-back. The apex is re-tapped at the turn, so the
    # full pitch sequence is an even-length palindrome that reads the same forwards
    # and backwards and returns to the low root. Unlike the one-hand journey's
    # cell-aligned turnaround (`journey.updown`, which drops the whole apex cell),
    # the tapped line drops nothing. The even count is load-bearing: it lets the
    # symmetric descent survive the fitter (proven post-fitter in test_pipeline),
    # where the old apex-once (odd) count let `DROP_ONE` strip the closing root.
    score, hints = generate(quality, pattern=pattern)
    pitches = [note.pitch for note in notes_of(score)]
    assert hints.seam is not None

    # An even-length palindrome: the whole journey mirrors about the doubled apex.
    assert len(pitches) % 2 == 0
    assert pitches == pitches[::-1]

    # The apex is re-tapped at the fold, and the two halves are exact reverses.
    half = len(pitches) // 2
    assert pitches[half - 1] == pitches[half]  # the doubled apex
    assert pitches[:half] == pitches[half:][::-1]

    # Begins and ends on the low root — the closing root is present.
    assert pitches[0] == pitches[-1] == ROOT


@pytest.mark.parametrize("quality", _TRIADS)
@pytest.mark.parametrize("pattern", _PATTERNS)
def test_the_tapped_journey_stays_two_handed_and_all_tapped_under_every_pattern(
    quality: str, pattern: str
) -> None:
    # The symmetric descent preserves everything B3 established, for every pattern:
    # both hands are used, every note is TAPPED (the pure-tapping default — no
    # legato is introduced at the turn), and the pitch content is the triad's own
    # chord tones tiled across the register.
    score, _hints = generate(quality, pattern=pattern)
    notes = notes_of(score)
    assert all(note.attack is TAPPED for note in notes)
    assert {note.hand for note in notes} == {LEFT, RIGHT}
    top = max(note.pitch for note in notes)
    assert {note.pitch for note in notes} == _tiled_chord_tones(quality, top)


# --------------------------------------------------------------------------
# The seventh path is untouched (one-hand)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("quality", ["maj7", "min7", "dom7"])
def test_a_seventh_keeps_the_one_hand_plucked_journey(quality: str) -> None:
    # A seventh routes to the existing `shape_places` journey: every note is
    # plucked by the left hand, exactly as before this task.
    seventh = {"root": 33, "quality": quality, "inversion": "root", "pattern": "straight"}
    score, _hints = _generate(BASS6, seventh)
    notes = notes_of(score)
    assert all(note.attack is PLUCKED for note in notes)
    assert all(note.hand is LEFT for note in notes)


def test_a_non_root_inversion_triad_is_deferred_and_raises() -> None:
    # The captured box is a root-position shape (spec §2). A first/second
    # inversion triad is not in v1 scope, so it raises rather than silently
    # tapping the root-position shape; §9's validity gate resamples.
    with pytest.raises(ValueError, match="root-position"):
        generate("maj", inversion="first")


# --------------------------------------------------------------------------
# The shared legato pass, in isolation
# --------------------------------------------------------------------------


def _tapped(string: int, hand: Hand, fret: int = 5, attack: Attack = TAPPED) -> Note:
    return Note(
        pitch=BASS6.tuning[string] + fret,
        string=string,
        fret=fret,
        duration=Fraction(1, 4),
        finger=1,
        accent=False,
        hand=hand,
        attack=attack,
    )


def _attacks(voice: Voice) -> list[Attack]:
    """The attack of every note in a derived voice, in order."""
    return [note.attack for note in voice if isinstance(note, Note)]


def test_legato_is_a_noop_for_the_all_tapped_triad_default() -> None:
    # Spec §6: the triad default taps every note — nothing is same-string+hand
    # consecutive — so the legato pass changes nothing.
    score, _hints = generate("min")
    before = notes_of(score)
    after = derive_legato(list(score.voice))
    assert after == before
    assert all(attack is TAPPED for attack in _attacks(after))


def test_a_same_string_same_hand_run_slurs_after_the_first() -> None:
    # A genuine hammer-on/pull-off run: same string and hand, the fret changing at
    # every step (R12 — a slur requires a fret change). First taps, the rest slur.
    run: Voice = [_tapped(2, LEFT, fret=5), _tapped(2, LEFT, fret=7), _tapped(2, LEFT, fret=9)]
    assert _attacks(derive_legato(run)) == [TAPPED, SLURRED, SLURRED]


def test_a_string_change_forces_a_fresh_tapped() -> None:
    voice: Voice = [
        _tapped(2, LEFT, fret=5),
        _tapped(2, LEFT, fret=7),
        _tapped(3, LEFT, fret=5),
        _tapped(3, LEFT, fret=7),
    ]
    assert _attacks(derive_legato(voice)) == [TAPPED, SLURRED, TAPPED, SLURRED]


def test_a_hand_change_on_the_same_string_forces_a_fresh_tapped() -> None:
    voice: Voice = [
        _tapped(2, LEFT, fret=5),
        _tapped(2, LEFT, fret=7),
        _tapped(2, RIGHT, fret=5),
        _tapped(2, RIGHT, fret=7),
    ]
    assert _attacks(derive_legato(voice)) == [TAPPED, SLURRED, TAPPED, SLURRED]


def test_r12_a_slur_needs_a_fret_change_a_same_fret_repeat_re_taps() -> None:
    # R12 (`melete#205`), the gate stated on one string and hand: a fret change is
    # a hammer-on/pull-off (SLURRED); a repeated fret is a re-tap (TAPPED). You
    # cannot hammer or pull to the same fret, so the fret is what decides.
    voice: Voice = [_tapped(2, LEFT, fret=5), _tapped(2, LEFT, fret=5), _tapped(2, LEFT, fret=8)]
    assert _attacks(derive_legato(voice)) == [TAPPED, TAPPED, SLURRED]


def test_plucked_notes_are_left_untouched() -> None:
    # A one-hand plucked voice is not a tapping voice: the pass never turns a
    # plucked note into a slur, so every existing family is unchanged.
    voice: Voice = [
        Note(pitch=40, string=2, fret=7, duration=Fraction(1, 4), finger=None, accent=False),
        Note(pitch=40, string=2, fret=7, duration=Fraction(1, 4), finger=None, accent=False),
    ]
    result = derive_legato(voice)
    assert result == voice
    assert all(attack is PLUCKED for attack in _attacks(result))


def test_a_dropped_leading_tapped_leaves_no_stranded_slur() -> None:
    # Post-fitter correctness (spec §3): a fret-changing run whose leading TAPPED
    # the fitter dropped arrives as SLURRED-first. Re-derived, its first note is
    # TAPPED again — a slur is never stranded without a tapped attack ahead of it.
    dropped: Voice = [
        _tapped(2, LEFT, fret=5, attack=SLURRED),
        _tapped(2, LEFT, fret=7, attack=SLURRED),
    ]
    assert _attacks(derive_legato(dropped)) == [TAPPED, SLURRED]


def test_a_re_tapped_apex_note_stays_tapped_r12() -> None:
    # R12 (`melete#205`): the re-tapped apex is two consecutive notes on the same
    # string and hand at the SAME fret. That is a re-articulation, not a slur — you
    # cannot hammer or pull to the same fret — so the doubled apex stays TAPPED.
    voice: Voice = [
        _tapped(1, RIGHT, fret=5),
        _tapped(4, RIGHT, fret=7),
        _tapped(4, RIGHT, fret=7),
        _tapped(1, RIGHT, fret=5),
    ]
    assert _attacks(derive_legato(voice)) == [TAPPED, TAPPED, TAPPED, TAPPED]


# --------------------------------------------------------------------------
# The neck bounds the climb (spec §6, §9)
# --------------------------------------------------------------------------


def test_the_journey_turns_around_when_the_next_box_leaves_the_neck() -> None:
    # A high root fits one box low on the neck but the next box's derived frets
    # run past the fretboard, so the climb stops there (turns around) rather than
    # clamping — a single-box up-and-down journey, still two-handed and tapped.
    high_root = BASS6.tuning[0] + 22  # box 0 tops out near fret 24; box 1 would overshoot
    score, _hints = generate("min", root=high_root)
    notes = notes_of(score)
    assert {note.hand for note in notes} == {LEFT, RIGHT}
    assert all(note.attack is TAPPED for note in notes)
    assert_central_invariant(score)


def test_a_triad_with_no_on_neck_box_is_unrealizable_and_raises() -> None:
    # Rooted at the open low string, the box's minor third would need a negative
    # fret: not even the first box fits, so the tapped journey is unrealizable
    # here and raises (spec §9 resamples) rather than clamping onto the nut.
    with pytest.raises(ValueError, match="unrealizable"):
        generate("min", root=BASS6.tuning[0])
