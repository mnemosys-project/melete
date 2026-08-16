# Two-hand tapping — derived fingering rules

**Task:** research `melete#200`, epic `mnemosys-project/.github#67`.
**Status:** LIVING DOCUMENT — grows and sharpens as the instructor adds examples.
Each rule carries a **confidence** and the evidence behind it; open questions name
the example that would resolve them.

## Purpose

Move two-hand tapping from a single hand-authored *box* (B0/B1) toward a
**rule-based** fingering model: capture the ergonomic logic by which the two hands
fold to play a passage, so melete can *derive* the fingering rather than look it
up. The long game is the passage → hand-fitting *solve* the instructor described.

## Corpus

| # | File | Contents |
|---|---|---|
| 1 | `build/argeggio-tapping-examples.gp` | First example — E min/maj/dim/aug, played as a rolling **cascade** (notes repeat as the window advances). A special case. |
| 2 | `build/e1-reference/tapped-corrected.gp` | Corrected full-fretboard runs — E aug (two descents), E maj, E min, E dim; clean 8-note ascending + symmetric descending lines. The realistic reference. |

## Conventions

- Instrument: 6-string bass, **B E A D G C** (all perfect fourths), string 0 =
  lowest (B). Fingers **1 = index, 2 = middle, 3 = ring, 4 = little**; thumb
  unused. `L`/`R` = left/right hand.
- The arpeggio ascends **root → third → fifth** repeating up the octaves; each
  octave is a "box" of root, third, fifth, then the octave-root (= next box's
  root).

## Rules

### R1 — Hand split: left takes root+third, right takes fifth+octave-root  · **high confidence**

Within each octave box the two lower chord tones (root, third) are **left**-hand
tapped and the two upper (fifth, octave-root) are **right**-hand tapped.
*Evidence:* both examples, all qualities. This is the box's core partition (spec §5).

### R2 — Left-hand finger pair mirrors the third's fret gap  · **high confidence**

Which two left fingers play root+third is set by how far the third sits below the
root (on the next string, a fourth up, the third lands at `fret + interval − 5`):

| Quality | third interval | third fret offset | left fingers (root, third) |
|---|---|---|---|
| minor | 3 | −2 | **ring (3), index (1)** — 2 fingers apart |
| major | 4 | −1 | **middle (2), index (1)** — 1 finger apart |
| augmented | 4 | −1 | **middle (2), index (1)** — 1 finger apart |
| diminished | 3 | −2 | **ring (3), index (1)** — 2 fingers apart |

**Finger spacing = fret spacing.** *Evidence:* corrected example — E min root L3,
E maj/aug root L2, all with third L1. This is an ergonomic *derivation*, not a
table. (It also explains why the first example's uniform L3 root was a special
case: it forced one fingering across qualities where the ergonomic choice differs.)

### R3 — Right-hand fingering is fixed: fifth = index, octave-root = middle  · **high confidence**

The right hand always taps the fifth with **index (1)** and the octave-root with
**middle (2)**, regardless of quality — the fifth's fret varies (dim +1, perfect
+2, aug +3 from the string's open-fourth baseline) but stays within the right
hand's reach. *Evidence:* both examples, all qualities.

### R4 — At the octave seam the shared note is right-hand; the next third is left ring  · **medium confidence**

Box N's octave-root and box N+1's root are the **same note**, played **once** by
the **right hand (middle)** at the seam. Because the left hand is then *not*
anchored on that octave's root, it reaches the next third with the **ring (3)**
finger (a stretch up), not the index. *Evidence:* corrected example — the higher
thirds (G♯2, G2) are L3 while the lowest third (G♯1/G1) is L1. *Confirm with:* an
example spanning more octaves / a different string region.

### R5 — Ascending and descending fingerings differ  · **medium confidence**

The same note can take a different finger coming down than going up (e.g. the
third G♯2 is **ring** ascending, **index** descending), because the hand's anchor
and approach flip with direction. *Evidence:* corrected example, maj and min
descents (bars 6, 8). *Confirm with:* more descents across qualities.

### R6 — Augmented's symmetry gives two valid descents; the entry point picks one  · **medium confidence**

Because the augmented tones are evenly spaced (a **fret-diagonal**), descending
admits **two** ergonomic fingerings; the one used is fixed by where in the 3-note
diagonal the pattern is entered (you start mid-diagonal). *Evidence:* corrected
example, E aug bars 2 vs 4 — same ascent, two different descents. *Implication:* a
rule engine must *choose* here, not derive a unique answer — the first genuine
branch point.

### R7 — Exercise shape: full-fretboard ascent, symmetric descent, clean line  · **high confidence**

A triad run ascends the fretboard and descends **symmetrically** (8 notes up, 8
down on this 6-string bass), one note per chord tone — **no cascade repeats** in
the realistic form. *Evidence:* corrected example. *Note:* melete's current driver
descends asymmetrically (7 up / 5 down) — a bug this rule pins.

## Open questions (need more examples)

- Do the rules hold for **other roots** (expected: yes, root-relative)?
- **Seventh-chord** arpeggios add a fourth chord tone — a different box; how does
  the finger logic extend?
- The **advanced folding** exercises (the ones tapping really exists for): do R1–R7
  survive, or does the passage-specific hand-fitting override them?
- R6's two-descent choice — is the entry-point rule the whole story, or are there
  cases where neither diagonal fingering is preferred?

## Relationship to the current implementation

The merged v1 encodes **one symmetric box** (`arpeggio_tap_shapes.TAP_BOX`, B1)
with derived frets. These rules show the *realistic* fingering is
quality-, octave-, and direction-dependent (R2, R4, R5) and that the descent
should be symmetric (R7). When the rules stabilize, they replace the fixed box's
fingering with a derivation — the box mechanics (placement, two-anchor `box`,
emit) stay; only the finger/hand assignment becomes rule-driven.

## Changelog

- 2026-08-16 — Seeded from corpus #1–#2; R1–R7 drafted.
