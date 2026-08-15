# Two-hand tapped triad choreography — captured

**Task:** B0 (`melete#188`), epic `mnemosys-project/.github#67`.
**Status:** PROVISIONAL — captured from the instructor's own playing; confirmed by
Task E1 before generated sheets are trusted.
**Source:** `build/argeggio-tapping-examples.gp` — a hand-authored Guitar Pro file
by the instructor, "how I play the straight triad arpeggios two-handed" (the
default fingering; not the only way).

## What the source contains

Four triads, all rooted on **E**, on a **6-string bass tuned B E A D G C**
(all perfect fourths). Each triad is a full **up-and-down two-hand tapped journey
up the neck** (2 bars each): **E minor, E major, E diminished, E augmented**.

- **Every note is tapped** — right hand (`Tapped`) or left hand
  (`LeftHandTapped`); **no plucked notes and no hammer-on/pull-off** (`h`) at all.
  This default is *pure tapping, no legato*.
- **Fingering:** left hand uses **ring (3)** and **index (1)**; right hand uses
  **index (1)** and **middle (2)**.

## The core finding: one universal box, not per-quality shapes

The hand-and-finger cascade is **byte-for-byte identical across all four
qualities**. The quality changes only *which frets* the third and fifth land on;
the choreography does not change. So the vocabulary is **one universal two-hand
"box"**, tiled up the arpeggio's chord tones.

### The box (one octave, root → octave-root)

Relative to the box's root at `(string S, fret F)`, with the instrument in
perfect fourths:

| # | Chord tone | String | Hand | Finger | Fret |
|---|---|---|---|---|---|
| 1 | root | `S` | LEFT | ring (3) | `F` |
| 2 | third | `S+1` | LEFT | index (1) | `F + (third_interval − 5)` |
| 3 | fifth | `S+1` | RIGHT | index (1) | `F + (fifth_interval − 5)` |
| 4 | octave-root | `S+2` | RIGHT | middle (2) | `F + 2` |

**Strings, hands, and fingers are fixed and universal.** Only the fret offsets of
the third and fifth vary, and they are **derived**, not tabulated: a chord tone
of interval `i` semitones, placed on a string tuned a fourth (5 semitones) above
the previous, sits at `F + i − 5`; the octave-root (12 semitones) two fourths up
(10 semitones) sits at `F + 2`. This is the two-hand analogue of the one-hand
`arpeggio_shapes._seed` derivation, and it preserves pitch by construction.

Verified fret offsets against the source (all four qualities):

| Quality | third interval → fret off | fifth interval → fret off |
|---|---|---|
| minor (0,3,7) | 3 → **−2** | 7 → **+2** |
| major (0,4,7) | 4 → **−1** | 7 → **+2** |
| diminished (0,3,6) | 3 → **−2** | 6 → **+1** |
| augmented (0,4,8) | 4 → **−1** | 8 → **+3** |

The chord intervals come straight from `theory.CHORDS`
(`maj`/`min`/`dim`/`aug`); nothing here is quality-specific code.

### Tiling up the neck

Boxes tile by octave: box *N*'s **octave-root** (at `S+2`, `F+2`) **is** box
*N+1*'s **root**, retapped by the **left ring** finger. So each successive box
climbs `+2 strings, +2 frets`, and the journey ascends outer-string-to-opposite
and back down the same boxes. On this 6-string bass a triad spans ~2–3 octave
boxes before the top string runs out.

### The leapfrog, explained

Because consecutive boxes overlap by their shared root, **a single pitch is
tapped by different hands at different points**: it is the *octave-root* of one
box (right middle) and the *root* of the next (left ring). Within any one box the
lower pair (root, third) is the left hand and the upper pair (fifth, octave-root)
is the right — the "low left, high right" intuition holds *per box* — but across
box boundaries the hands fold across each other. That overlap is the leapfrog.

## The cascade rhythm

The source plays each box as a **rolling four-note cascade** that overlaps its
neighbour (each chord tone sounds two–three times as the window advances). That
repetition is the *exercise rhythm*, an overlay on top of the placement above; it
is a matter for the layout/rhythm stages, not the tap-shape data. The
tap-shape data is the **box placement** (strings, hands, fingers, derived frets)
and the **tiling rule**.

## Scope and provisos

- **Triads only.** This captures `maj`/`min`/`dim`/`aug`. The common **seventh-
  chord** arpeggios are a **next iteration** and need their own captured examples
  (they add a chord tone and change the box).
- **One default fingering.** This is the instructor's default. Alternate
  augmented voicings exist and are deliberately deferred.
- **No legato.** The default taps every note; the derived hammer/pull pass stays
  in the pipeline for future slur-based styles but is a no-op here.
- **PROVISIONAL.** Task E1 is the instructor's formal sign-off on the encoded
  result.
