import pytest

from melete import theory
from melete.families import journey
from melete.instrument import PROFILES, hand_span

BASS6 = PROFILES["bass6"]  # 6 strings, tuning B0 E1 A1 D2 G2 C3


def test_per_string_reaches_the_top_string():
    # Enough ascending C major pitches to cover 3 notes on all 6 strings.
    pitches = theory.scale_pitches(root=BASS6.tuning[0] + 3, scale_type="ionian", octaves=4)
    used, places = journey.per_string(
        BASS6, pitches, notes_per_string=3, family="scales", axes="root"
    )
    strings = [s for s, _f in places]
    assert strings[0] == 0 and strings[-1] == len(BASS6.tuning) - 1  # outer to outer
    assert sorted(set(strings)) == list(range(len(BASS6.tuning)))  # every string, no gap
    for pitch, (s, f) in zip(used, places, strict=True):
        assert BASS6.tuning[s] + f == pitch  # invariant


def test_per_string_raises_when_a_pitch_falls_off_the_neck():
    # A pitch far above the top fret cannot be truncated to fit (spec §5, §10).
    with pytest.raises(ValueError, match="scales"):
        journey.per_string(
            BASS6,
            [BASS6.tuning[0] + BASS6.fret_count + 1],
            notes_per_string=1,
            family="scales",
            axes="root",
        )


def test_boxed_span_stays_in_one_position_and_uses_the_outer_strings():
    pitches = theory.scale_pitches(root=BASS6.tuning[0] + 3, scale_type="ionian", octaves=4)
    used, places = journey.boxed_span(BASS6, pitches, family="scales", axes="root")
    assert hand_span(f for _s, f in places) <= BASS6.position_span
    assert places[0][0] == 0 and places[-1][0] == len(BASS6.tuning) - 1
    assert used  # the leading run that fit is non-empty


def test_boxed_span_consumes_pitches_that_all_fit_one_hand():
    # A short run entirely inside one position exhausts the loop without breaking.
    pitches = [BASS6.tuning[0] + 3, BASS6.tuning[0] + 5]
    used, places = journey.boxed_span(BASS6, pitches, family="scales", axes="root")
    assert used == list(pitches)
    assert hand_span(f for _s, f in places) <= BASS6.position_span


def test_updown_is_always_up_and_down():
    # cell 1: ascend 0..3 then back down without replaying the apex.
    assert journey.updown([0, 1, 2, 3], cell=1) == [0, 1, 2, 3, 2, 1, 0]
