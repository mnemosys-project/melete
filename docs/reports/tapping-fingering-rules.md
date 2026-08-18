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
| 2 | `build/e1-reference/tapped-corrected.gp` | Full-fretboard runs (rev. 2026-08-16): the four **standard** triad shapes — E maj, E min, E dim — plus E aug in **two** fingerings (standard box + a symmetry-driven **alternate**, both supplied ascending *and* descending). Clean 8-note lines. The realistic reference. |
| 3 | `build/e1-reference/tapped-triads-groups-of-3.gp` | The four triads played as **rolling triplets** — overlapping 3-note groups advancing by one (a "sixes" pattern) up and back. Shows the *fold*: a pitch is re-handed as the window advances. All tapped. |
| 4 | `build/e1-reference/tapped-3nps-scales.gp` | **E harmonic-minor, 3 notes per string** — the first **scale** example. Ascending uses left-tap→hammer→right-tap per string; descending uses a **pre-fretted pluck-cascade** (tap the top, pull-off down). Legato (hammer/pull) is central here. |
| 5 | `build/Tapping_Arpeggios_7th_Chords.gp` | **Seventh-chord** shapes on a **5-string bass** (B E A D G): the compact two-string grid for maj7/dom7/min7/m7♭5/dim7, plus an alternate four-string diagonal voicing. All tapped, pitch-preserving. |

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
This is the **standard-shape** split; the augmented **alternate** (R6) breaks it —
the one documented exception so far, and it is driven by interval symmetry.

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

### R6 — Augmented's symmetry admits an alternate diagonal fingering, both directions  · **high confidence**

Because the augmented tones are evenly spaced (every interval a major third — a
uniform **fret-diagonal**), augmented admits a second, equally legitimate fingering
the other triads do not. It is a **3-note repeating cell** climbing the diagonal —
**left middle (root), left index (third), right index (#5)** — applied identically
ascending and descending:

```
L2 L1 R1 · L2 L1 R1 · …
```

Unlike the standard box (R1), the **right hand taps only the #5**; the left hand
walks root + third + octave-root up the diagonal. *Evidence:* revised corrected
example, E aug bars 3–4 (alternate) vs 1–2 (standard). This is the first
**quality-specific alternate driven by interval symmetry** — a documented
exception to R1, and a preview of how the *structure of the passage* (not the chord
label) selects the fingering. The instructor notes it is legitimate but
less-frequently used.

### R7 — Exercise shape: full-fretboard ascent, symmetric descent, clean line  · **high confidence**

A triad run ascends the fretboard and descends **symmetrically** (8 notes up, 8
down on this 6-string bass), one note per chord tone — **no cascade repeats** in
the realistic form. *Evidence:* corrected example. *Note:* melete's current driver
descends asymmetrically (7 up / 5 down) — a bug this rule pins.

### R8 — In rolling/overlapping groupings, a pitch is re-handed by its role in the local window  · **high confidence**

When the same notes are played in **overlapping groups** — rolling triplets, three
notes advancing by one — a given pitch takes a **different hand/finger in each group
it appears in**, chosen by its *role in that group*, not by the pitch. *Evidence:*
groups-of-three example — E2 is **right-middle** as the top of `[G♯1, C2, E2]`, then
**left-middle** as the anchor of `[C2, E2, G♯2]`. The hand follows the flow: a note
reached as a group's *arrival* is right-hand; the same note serving as the next
group's *low anchor* is left-hand, freeing the right to reach up. This is the
**fold**, and it generalises R5 from direction-dependence to
**local-window-dependence**. (All notes tapped — no legato.)

**Implication — the load-bearing one.** Fingering is not a per-pitch or per-shape
lookup. It is a function of **local context** as the pattern folds up the passage,
so a rule engine must *walk* the passage and assign each note's hand/finger from its
neighbourhood — what hand is free, what is arriving, what comes next. That is a small
solver / state machine: precisely the passage → hand-fitting **solve** the instructor
described. R1–R7 are the *constraints and preferences* that solve feeds on; R8 is why
it must be a solve and not a table.

### R9 — Scales tap per **string** (3-note groups); ascending and descending articulate differently  · **high confidence (new domain: scales)**

A 3-notes-per-string scale taps in **per-string groups of three** — a different
unit from the arpeggio's per-octave box:

- **Ascending:** on each string, **left-tap** the first note, **hammer-on** (left)
  to the second, **right-tap** the third — `Ltap · hammer · Rtap`. Two left fingers
  + right index, the same hand economy as R1 but organised by string.
- **Descending:** the group is **pre-fretted** (all three fingers set at once) and
  sounded top-down — **right-tap** the top, then **pull-off · pull-off** to the two
  lower notes — `Rtap · pull · pull`.

*Evidence:* corpus #4, E harmonic-minor 3nps (bar 1 ascending, bar 2 descending).
*Note:* unlike the arpeggios (all tapped), **scales lean on hammer/pull legato** —
so the derived-legato pass (dormant for the triad boxes, R7/§6) is **load-bearing**
here.

### R10 — The "pre-fretted pluck-cascade" is a *technique identity*, not a new note-attack  · **discussion / design**

The descending scale technique the instructor flags — pre-fret the whole group as a
grip, sound the top by tapping, then *pluck/pull* down through the held notes — is
musically distinct (a different feel, a flourish at speed) but at the **note level
renders identically to tap + pull-offs**: the struck note is `TAPPED`, the cascaded
notes are `SLURRED`, which the emitter already renders as `Tapped` + `Hopo`. So
melete's existing `attack` model *can render it*; what it does not capture is the
**grip/pluck technique identity** (fret-all-first; active pluck vs passive pull).

**Recommendation:** carry that identity as a **phrase/exercise-level technique tag**
(driving instruction text, and possibly future notation), **not** a new `attack`
value that would not change the render. The execution *choice* it implies — a
pull-off cascade vs re-tapping each note — is a real note-level difference the model
already expresses (`SLURRED` vs `TAPPED`); the tag records which the exercise intends.

### R11 — Seventh chords use a compact two-string grid — simpler than the triads  · **high confidence (new domain: 7ths)**

A seventh chord's four tones tap as a **2-string × 2-hand grid** — each string
carries two chord tones, the **lower-fret note left-hand-tapped, the higher-fret
note right-hand-tapped**:

- string N: **root** (left) + **third** (right)
- string N+1: **fifth** (left) + **seventh** (right)

So **left = root + fifth, right = third + seventh** — the "1–5 left, 3–7 right"
split. There is **no octave-tiling overlap or leapfrog** (the four tones fill the
grid), which is why sevenths are *simpler* than the triads. *Evidence:* corpus #5
(5-string bass), all five qualities — **maj7, dom7, min7, m7♭5, dim7** — the
third/fifth/seventh frets shifting per quality; pitch-preserving (one octave). An
**alternate** four-string diagonal voicing also appears (one note per string;
right = root+third on the low strings, left = fifth+seventh on the high strings).

*Unifies with the triads (medium confidence):* the constant across both is
**on each string, lower fret → left hand, higher fret → right hand**; only the
chord-tone-to-string *voicing* differs (a triad packs root+third low; a seventh
spreads root+third / fifth+seventh across two strings). R1's "left = root+third" is
a triad-voicing consequence of this deeper per-string rule.

*Corrects a spec guess:* spec §12 assumed sevenths would "lean stretched"
(pitch-changing). They do **not** — the natural seventh shape is compact and
pitch-preserving; the octave-displaced stretched voicings remain a separate
deferred item.

### R12 — At a turnaround the apex is re-tapped; legato requires a fret change  · **high confidence (first "solve" rule)**

At a direction reversal — the top of an up-and-back run — the apex note is
**re-tapped** (played twice), not sounded once. The articulation consequence:
**a slur (hammer/pull) requires a fret change.** Two consecutive notes on the same
string and hand at the **same fret** are a **re-tap** (`TAPPED`), not a slur — you
cannot hammer or pull to the same fret; a same-fret repeat is a re-articulation.
*Evidence:* the corrected examples double the apex across the turnaround
(re-tapped, not tied); and system-side, the doubled apex gives an **even** note
count that tiles into whole bars, whereas the apex-*once* (odd) count forces the
layout fitter's `DROP_ONE` to strip the closing root and break the symmetry (found
via the E1 sheets, corpus #2). This is the **first implicit real-world adaptation
captured as a deterministic rule** — a refinement of legato derivation (R7/R9):
legato is **fret-change-gated**.

## Open questions (need more examples)

- Do the rules hold for **other roots** (expected: yes, root-relative)?
- **Seventh-chord** arpeggios add a fourth chord tone — a different box; how does
  the finger logic extend?
- The **advanced folding** exercises (the ones tapping really exists for): do R1–R7
  survive, or does the passage-specific hand-fitting override them?
- Do other **symmetric** structures (diminished-seventh, whole-tone fragments)
  admit similar diagonal alternates the way augmented does (R6)? Symmetry may be
  the general trigger for an alternate fingering.
- When *is* the augmented alternate (R6) chosen over the standard (R1) — purely
  the player's preference, or does the surrounding passage select it?

## Relationship to the current implementation

The merged v1 encodes **one symmetric box** (`arpeggio_tap_shapes.TAP_BOX`, B1)
with derived frets. These rules show the *realistic* fingering is
quality-, octave-, and direction-dependent (R2, R4, R5) and that the descent
should be symmetric (R7). When the rules stabilize, they replace the fixed box's
fingering with a derivation — the box mechanics (placement, two-anchor `box`,
emit) stay; only the finger/hand assignment becomes rule-driven.

## Changelog

- 2026-08-16 — Seeded from corpus #1–#2; R1–R7 drafted.
- 2026-08-16 (rev) — corpus #2 revised: augmented reworked to standard + a
  symmetry-driven **diagonal alternate** (both directions); R6 rewritten and
  promoted to high confidence; R1 noted as the standard-shape split with the aug
  alternate as its exception; dim top-note slip corrected (G3).
- 2026-08-16 (corpus #3) — added the rolling groups-of-three example; new rule
  **R8** (local-window re-handing / the fold), generalising R5, and the finding
  that fingering is a **local-context solve**, not a table. R1–R7 reframed as the
  constraints that solve consumes.
- 2026-08-16 (corpus #4) — added E harmonic-minor 3nps scales, opening the
  **scales** domain: **R9** (per-string 3-note groups; ascending tap→hammer→tap,
  descending pre-fretted pull-cascade) makes legato load-bearing; **R10** records
  the pre-fretted pluck-cascade as a *technique identity* that renders as tap+slur
  — a phrase-level tag, not a new `attack`.
- 2026-08-17 (corpus #5) — added seventh-chord shapes (5-string bass): **R11** —
  sevenths tap as a compact **two-string grid** (left root+fifth, right
  third+seventh), simpler than the triads, all five qualities, pitch-preserving;
  plus an alternate four-string diagonal voicing. Surfaced the unifying per-string
  **low = left / high = right** principle, and corrected the spec's "sevenths lean
  stretched" guess.
- 2026-08-18 — **R12** (first "solve" rule): turnaround apex re-tap; **legato
  requires a fret change** (same-fret repeat = re-tap, not slur). The first
  implicit real-world adaptation turned deterministic; also the fix for the
  symmetric-descent gap (apex-once's odd count let the fitter's `DROP_ONE` strip
  the closing root). Implemented in F3 (`melete#205`).
