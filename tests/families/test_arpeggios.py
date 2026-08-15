"""Tests for the `arpeggios` family (spec §6, §7).

The shape follows `test_scales.py`, because every family makes the same promise
and §14 tests them the same way: one complete journey, the central invariant,
the key the notes are spelled against, the exact parameters travelling inside
the Score, a family-declared tempo, and a wide parameter sweep over the axes.

After epic #72 the geometry is *computed*, not sampled: the arpeggio is the
chord's up-and-down journey from the root on the lowest string out to the
opposite outer string, laid out by the quality's canonical seed shape
(`arpeggio_shapes`). There is one layout in v1, so the `traversal`, `string_set`,
`range_octaves` and `direction` axes are gone — the *journey* tests below replace
the old traversal/direction ones. The *content* tests still assert the chord
tones come from `theory.chord_pitches` and that `inversion` rotates them. The
*error* tests assert an unrealizable specification raises and names what could
not be satisfied — §9 resamples that case and §13 forbids clamping it.
"""

from __future__ import annotations

from fractions import Fraction
from typing import TYPE_CHECKING

import pytest
from conftest import assert_central_invariant, assert_spelling_sounds_correctly, notes_of

from melete import theory, vocabulary
from melete.families import arpeggio_shapes
from melete.families.arpeggios import DEFAULT_TEMPO_RANGE, INSTRUCTION, INVERSIONS
from melete.families.arpeggios import generate as _generate
from melete.instrument import PROFILES
from melete.layout import Lever

if TYPE_CHECKING:
    from collections.abc import Mapping

    from melete.instrument import InstrumentProfile
    from melete.layout import LayoutHints
    from melete.score import Score


def generate(profile: InstrumentProfile, params: Mapping[str, object]) -> Score:
    """Unpack the family's `(Score, LayoutHints)`; these tests assert on the Score.

    §4.2 widened every family to return its layout hints alongside the Score.
    The hint contract is covered in `test_registry`; here the Score is the
    subject, so a single wrapper unpacks it rather than every call site.
    """
    score, _hints = _generate(profile, params)
    return score


BASS6 = PROFILES["bass6"]  # tuning B0 E1 A1 D2 G2 C3 = 23 28 33 38 43 48

#: A high-enough root that every seeded quality reaches the top string without
#: the seed shape running off the low end of the neck. A1 = 33 sits at fret 10
#: on the low B string, so the worked example is A major 7 in root position — the
#: same root `test_scales.py` uses, so the two families' examples sit in one key.
ROOT = 33

#: The qualities the pool drills, and the only ones the seed shapes cover (v1).
#: A quality without a seed shape is unrealizable — the family no longer laid
#: every chord type out from `theory` alone.
QUALITIES = sorted(arpeggio_shapes.SEED_SHAPES)
PATTERNS = ["straight", "numeric_1353", "broken", "sweep_ordered"]

PARAMS: dict[str, object] = {
    "root": ROOT,
    "quality": "maj7",
    "inversion": "root",
    "pattern": "straight",
}


def params(**overrides: object) -> dict[str, object]:
    """`PARAMS` with one or more axes replaced."""
    return {**PARAMS, **overrides}


def pitches_of(score: Score) -> list[int]:
    """The pitch of every note, in playing order."""
    return [note.pitch for note in notes_of(score)]


def strings_of(score: Score) -> list[int]:
    """The string index of every note, in playing order."""
    return [note.string for note in notes_of(score)]


def ascending_of(score: Score, hints: LayoutHints) -> list[int]:
    """The strings of the ascending half, up to and including the apex.

    The hints name the apex seam — the last note of the ascending pass — so the
    ascending half is everything up to it, whatever the pattern.
    """
    assert hints.seam is not None
    return strings_of(score)[: hints.seam + 1]


# --------------------------------------------------------------------------
# The family contract
# --------------------------------------------------------------------------


def test_obeys_the_central_invariant() -> None:
    assert_central_invariant(generate(BASS6, PARAMS))


def test_spells_every_note_as_it_sounds() -> None:
    assert_spelling_sounds_correctly(generate(BASS6, PARAMS))


def test_the_key_is_the_root_and_the_quality_s_implied_parent() -> None:
    # §10a: a chord is spelled by function, and the implied parent is what
    # turns that into the one `Key` mechanism the scales already use.
    assert generate(BASS6, PARAMS).key == theory.Key(9, "ionian")


@pytest.mark.parametrize("quality", QUALITIES)
def test_every_quality_is_spelled_against_its_implied_parent(quality: str) -> None:
    score = generate(BASS6, params(quality=quality))
    assert score.key == theory.Key(9, theory.IMPLIED_PARENT[quality])
    assert_spelling_sounds_correctly(score)


@pytest.mark.parametrize(("root", "tonic"), [(33, 9), (30, 6), (29, 5)])
def test_the_tonic_is_a_pitch_class_and_not_the_root_pitch(root: int, tonic: int) -> None:
    # A1 and A2 are the same key. `root` stays an absolute pitch everywhere
    # else (§10a), which is exactly why the reduction has to happen here.
    assert generate(BASS6, params(root=root)).key == theory.Key(tonic, "ionian")


def test_params_travel_inside_the_score() -> None:
    assert generate(BASS6, PARAMS).params == PARAMS


def test_default_tempo_range_is_declared_by_the_family() -> None:
    # Spec §7: the family declares the range and the selector never samples it.
    assert DEFAULT_TEMPO_RANGE == (80, 140)
    assert generate(BASS6, PARAMS).tempo_range == (80, 140)


def test_the_notes_are_plain_and_unaccented() -> None:
    # §8's rhythm modifier owns subdivision and accents; this family states the
    # un-modified reading and nothing more.
    score = generate(BASS6, PARAMS)
    assert score.time_signature == (4, 4)
    assert {(note.duration, note.accent) for note in notes_of(score)} == {(Fraction(1, 4), False)}


def test_the_fingering_is_left_unspecified() -> None:
    # §6 makes `finger` first class because in *chromatic* work the fingering is
    # the exercise. Here the position is, and prescribing a finger would engrave
    # a fingering the caller never asked for.
    assert {note.finger for note in notes_of(generate(BASS6, PARAMS))} == {None}


def test_the_score_carries_a_title_and_a_focus_cue() -> None:
    # The journey is always up-and-down, so the title states no direction — just
    # the chord (and, when there is one, the pattern figure).
    score = generate(BASS6, PARAMS)
    assert score.title == "A major 7th"
    assert score.instruction == INSTRUCTION


def test_the_title_names_an_inversion_and_a_pattern_only_when_there_is_one() -> None:
    score = generate(BASS6, params(inversion="first", pattern="broken"))
    assert score.title == "A major 7th, first inversion, broken"


def test_generate_is_pure() -> None:
    given = params()
    first, second = generate(BASS6, given), generate(BASS6, given)
    assert first == second
    assert given == PARAMS

    # The Score owns its parameters: a caller reusing the dictionary it passed
    # in must not be able to rewrite the record of what was generated.
    first.params["root"] = 99
    assert given["root"] == ROOT


# --------------------------------------------------------------------------
# The journey: outer string to opposite outer string, up and down (spec §5)
# --------------------------------------------------------------------------


def test_arpeggio_journey_uses_all_needed_strings_and_is_up_and_down() -> None:
    # The plan's acceptance test: from the root on the low string out to the top
    # string and back, not the one-string collapse the old `_across` could fall
    # into. No `traversal`/`direction`/`string_set`/`range_octaves`: one layout.
    score = generate(BASS6, params(root=BASS6.tuning[0] + 10, quality="min7", inversion="root"))
    strings = strings_of(score)
    assert strings[0] == 0
    assert max(strings) == len(BASS6.tuning) - 1  # reaches the opposite outer string
    assert strings[0] == strings[-1]  # returns to the low string
    for note in notes_of(score):
        assert BASS6.tuning[note.string] + note.fret == note.pitch


def test_the_journey_starts_on_the_low_string_and_reaches_the_top() -> None:
    _score, hints = _generate(BASS6, PARAMS)
    score = generate(BASS6, PARAMS)
    ascent = ascending_of(score, hints)
    assert ascent[0] == 0  # anchored on the lowest instrument string
    assert ascent[-1] == len(BASS6.tuning) - 1  # the ascent ends on the top string


def test_the_journey_returns_without_replaying_the_apex() -> None:
    # up-and-down: the sequence is its ascent followed by the retrograde of the
    # ascent minus the apex, so it comes back to where it started.
    score = generate(BASS6, PARAMS)
    pitches = pitches_of(score)
    apex = max(pitches)
    assert pitches.count(apex) == 1  # the turnaround note plays once
    assert pitches[0] == pitches[-1]  # back to the opening note


def test_the_apex_is_the_single_highest_note() -> None:
    _score, hints = _generate(BASS6, PARAMS)
    pitches = pitches_of(generate(BASS6, PARAMS))
    assert hints.seam is not None
    assert pitches[hints.seam] == max(pitches)


# --------------------------------------------------------------------------
# Chord content comes from `theory`
# --------------------------------------------------------------------------


def test_chord_tone_content_is_root_third_fifth_and_seventh() -> None:
    score = generate(BASS6, PARAMS)
    assert {note.pitch % 12 for note in notes_of(score)} == {
        (ROOT + offset) % 12 for offset in (0, 4, 7, 11)
    }


def test_the_ascending_tones_are_theory_s_pitch_classes_and_climb() -> None:
    _score, hints = _generate(BASS6, PARAMS)
    assert hints.seam is not None
    score = generate(BASS6, PARAMS)
    ascent_pitches = pitches_of(score)[: hints.seam + 1]
    assert ascent_pitches == sorted(ascent_pitches)  # the ascent only climbs
    assert {pitch % 12 for pitch in ascent_pitches} == {
        pitch % 12 for pitch in theory.chord_pitches(ROOT, "maj7")
    }


def test_min7_flattens_the_third_and_the_seventh() -> None:
    major = sorted(set(pitches_of(generate(BASS6, PARAMS))))
    minor = sorted(set(pitches_of(generate(BASS6, params(quality="min7")))))
    # Both start on the same root; the minor third and seventh sit a semitone
    # below the major ones.
    assert (major[0] + 3) % 12 in {pitch % 12 for pitch in minor}
    assert (major[0] + 10) % 12 in {pitch % 12 for pitch in minor}


@pytest.mark.parametrize("quality", QUALITIES)
def test_every_seeded_quality_takes_its_pitch_classes_from_theory(quality: str) -> None:
    played = {pitch % 12 for pitch in pitches_of(generate(BASS6, params(quality=quality)))}
    assert played == {pitch % 12 for pitch in theory.chord_pitches(ROOT, quality)}


# --------------------------------------------------------------------------
# `inversion` rotates the chord tones (spec §7)
# --------------------------------------------------------------------------


def test_the_inversion_identifiers_are_the_registry_s() -> None:
    # §7 writes the axis as root/first/second/third and `config` samples it as
    # a registry identifier, so the family reads an identifier and never the
    # bare rotation count it hands to `theory`.
    assert set(INVERSIONS) == set(vocabulary.accepted("inversion"))


def test_each_inversion_starts_on_the_next_chord_tone() -> None:
    # The journey still anchors the root on the low string; the inversion sets
    # which chord tone the ascent opens on.
    starts = [pitches_of(generate(BASS6, params(inversion=name)))[0] for name in INVERSIONS]
    assert starts == [33, 37, 40, 44]  # root, third, fifth, seventh of A maj7


def test_an_inversion_keeps_the_pitch_classes() -> None:
    for name in INVERSIONS:
        played = {pitch % 12 for pitch in pitches_of(generate(BASS6, params(inversion=name)))}
        assert played == {pitch % 12 for pitch in theory.chord_pitches(ROOT, "maj7")}


def test_a_triad_defers_every_non_root_inversion() -> None:
    # A triad now routes to the two-hand tapped journey (epic #67), and the
    # captured tap box is a root-position shape (spec §2). So a triad supports
    # only root position; every other inversion — including the third a triad
    # has no chord tone for — is deferred and raises rather than silently
    # tapping the root-position shape (§13). The one-hand journey (a seventh)
    # keeps supporting all four inversions, so the theory-level rejection of an
    # unsupported inversion is covered where it now lives, in `test_theory`.
    for inversion in ("first", "second", "third"):
        with pytest.raises(ValueError, match="root-position"):
            generate(BASS6, params(quality="maj", inversion=inversion))


# --------------------------------------------------------------------------
# `pattern` reorders the chord tones before the journey orders them
# --------------------------------------------------------------------------


def test_a_pattern_reorders_without_changing_the_pitch_classes() -> None:
    straight = {pitch % 12 for pitch in pitches_of(generate(BASS6, PARAMS))}
    for pattern in PATTERNS:
        other = {pitch % 12 for pitch in pitches_of(generate(BASS6, params(pattern=pattern)))}
        assert other == straight


def test_broken_skips_a_tone_and_comes_back_for_it() -> None:
    # `broken` is the window (0, 2): tone, skip one, then the skipped one.
    _score, hints = _generate(BASS6, params(pattern="broken"))
    assert hints.seam is not None
    ascent = pitches_of(generate(BASS6, params(pattern="broken")))[: hints.seam + 1]
    straight_ascent = pitches_of(generate(BASS6, PARAMS))[: _straight_seam() + 1]
    assert ascent[:3] == [straight_ascent[0], straight_ascent[2], straight_ascent[1]]


def _straight_seam() -> int:
    _score, hints = _generate(BASS6, PARAMS)
    assert hints.seam is not None
    return hints.seam


# --------------------------------------------------------------------------
# Unrealizable specifications raise, naming what could not be satisfied (§13)
# --------------------------------------------------------------------------


def test_a_missing_axis_names_the_axis_and_the_family_s_axes() -> None:
    spec = params()
    del spec["pattern"]
    with pytest.raises(ValueError, match=r"parameter 'pattern' is required.*'quality'"):
        generate(BASS6, spec)


def test_an_unknown_identifier_lists_the_accepted_values() -> None:
    with pytest.raises(ValueError, match=r"unknown quality 'maj9'.*m7b5"):
        generate(BASS6, params(quality="maj9"))


def test_an_integer_inversion_is_not_an_identifier() -> None:
    # §7's inversion column is a registry axis like every other identifier, so
    # the bare rotation count `theory` takes is not accepted here.
    with pytest.raises(ValueError, match=r"unknown inversion 1"):
        generate(BASS6, params(inversion=1))


def test_a_pattern_this_family_cannot_realize_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"pattern 'thirds'.*arpeggios realizes"):
        generate(BASS6, params(pattern="thirds"))


def test_a_non_integer_root_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"root must be an integer, got '33'"):
        generate(BASS6, params(root="33"))


def test_a_quality_without_a_seed_shape_is_unrealizable() -> None:
    # v1 has one layout — the seed shape — so a chord type the seeds do not cover
    # cannot be laid out. `min_maj7` is a valid quality but is not drilled here.
    with pytest.raises(ValueError, match=r"arpeggios: no seed shape for quality 'min_maj7'"):
        generate(BASS6, params(quality="min_maj7"))


def test_a_root_too_low_to_lay_out_the_shape_raises() -> None:
    # C1 = 24 anchors at fret 1 on the low B string, so the maj7 seed puts its
    # fifth (G = 31) below the open A string — fret -2. The shape is derived,
    # never clamped (spec §10); §9 resamples a root the shape can carry.
    with pytest.raises(ValueError, match=r"arpeggios:.*needs fret -2 on string 2"):
        generate(BASS6, params(root=24))


# --------------------------------------------------------------------------
# The sweeps (spec §14: families are tested over a wide parameter sweep)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("quality", QUALITIES)
@pytest.mark.parametrize("inversion", INVERSIONS)
def test_invariant_holds_across_qualities_and_inversions(quality: str, inversion: str) -> None:
    score = generate(BASS6, params(quality=quality, inversion=inversion))
    assert_central_invariant(score)
    assert_spelling_sounds_correctly(score)
    assert score.key == theory.Key(ROOT % 12, theory.IMPLIED_PARENT[quality])
    strings = strings_of(score)
    assert strings[0] == 0  # anchored on the lowest string
    assert max(strings) == len(BASS6.tuning) - 1  # reaches the top string
    assert strings[0] == strings[-1]  # up-and-down returns


@pytest.mark.parametrize("pattern", PATTERNS)
def test_invariant_holds_across_patterns(pattern: str) -> None:
    score = generate(BASS6, params(pattern=pattern))
    assert_central_invariant(score)
    assert_spelling_sounds_correctly(score)


@pytest.mark.parametrize("profile_name", sorted(PROFILES))
def test_invariant_holds_across_the_profiles(profile_name: str) -> None:
    # A1 = 33 sits on the low string of every profile (bass4 starts on E1, so it
    # is fret 5 there), and the seed shape climbs to whatever top string the
    # profile provides.
    profile = PROFILES[profile_name]
    score, _hints = _generate(profile, PARAMS)
    assert_central_invariant(score)
    assert strings_of(score)[0] == 0
    assert max(strings_of(score)) == len(profile.tuning) - 1


# --------------------------------------------------------------------------
# The layout hints (spec §4.2)
# --------------------------------------------------------------------------


def test_layout_hints_report_the_pattern_window_as_the_cell() -> None:
    # §4.2's cell is one turn of the `pattern` window. `straight` is `(0,)`, so
    # its cell is a single note; `numeric_1353` is a four-note window.
    _score, straight = _generate(BASS6, PARAMS)
    assert straight.cell == 1
    _score, numeric = _generate(BASS6, params(pattern="numeric_1353"))
    assert numeric.cell == 4


def test_the_journey_names_its_apex_seam_and_offers_apex_levers() -> None:
    # The journey is always up-and-down now, so it always names the apex — the
    # last note of the ascending pass — which is what lets the fitter's apex
    # levers act (§4.6).
    score, hints = _generate(BASS6, PARAMS)
    assert hints.seam is not None
    pitches = pitches_of(score)
    assert pitches[hints.seam] == max(pitches)
    assert {Lever.APEX_REPEAT, Lever.APEX_OMIT} <= set(hints.levers)
