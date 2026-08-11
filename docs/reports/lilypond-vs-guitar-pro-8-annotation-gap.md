# LilyPond vs Guitar Pro 8 — Guitar-Technique Annotation Gap Analysis

**Status:** research finding (reference). **Date:** 2026-08-10.
**Tracking issue:** mnemosys-project/melete#65.
**Method:** three parallel web-research passes (Guitar Pro 8 inventory,
LilyPond capability, MusicXML interchange), synthesized here. Every URL below
is real and checkable. Where a claim could not be confirmed from a clean
primary source it is flagged **UNVERIFIED**.

## Why this exists

melete engraves through LilyPond and is guitar/bass-focused. To plan which
guitar-technique annotations melete should eventually support in its **own
generated** practice sheets — and to understand how much could ever be
imported from Guitar Pro 8 files — we need an accurate picture of what each
tool can express and where the gaps are. This report is that picture. It is a
reference, not a spec; the authoritative spec lives in
`mnemosys-project/.github`.

## How to read this

Throughout, **DATA** means "a cited source states this" and **JUDGMENT** means
"this is our inference on top of the data." This separation is deliberate: the
distinctions LilyPond does and does not model are load-bearing for roadmap
decisions, and a reader should be able to re-verify any DATA claim from the
linked source.

## Summary — the headline finding

The natural framing of the question ("what can Guitar Pro 8 annotate that
LilyPond cannot render?") is slightly misleading, because **LilyPond's
rendering is largely not the bottleneck.** LilyPond can draw the great majority
of these techniques natively. The real gaps are of two narrower kinds, plus one
large gap that is not about rendering at all:

1. **Distinctions LilyPond does not model.** It renders the thing but collapses
   a sub-classification Guitar Pro 8 keeps: hammer-on vs pull-off (both are
   plain slurs), the six GP8 slide types (one `\glissando`), and the finer
   harmonic types (natural + artificial only).
2. **Techniques with no semantic command.** Renderable only via manual text or
   notehead markup: vibrato, tapping, slap/pop, rasgueado, golpe.
3. **The import pipeline (the big one).** Getting GP8's authored data *into*
   LilyPond means GP8 → MusicXML → `musicxml2ly`, which is lossy at two hops.
   This — not LilyPond's drawing ability — is the true constraint on ever
   reproducing a Guitar Pro 8 score automatically.

And the annotation the maintainer uses most heavily — **left- and right-hand
fingering** — is a **strong yes in both tools, natively.** LilyPond prints
p/i/m/a for the right hand by default and 1–4 for the left.

## 1. Guitar Pro 8 annotation inventory

In Guitar Pro's data model these are **true structured note/beat attributes**
that the audio engine interprets and that persist in the `.gp`/`.gpx` file —
not free-text overlays. Evidence for the structured model comes from the
documented file-format enums (PyGuitarPro:
<https://pyguitarpro.readthedocs.io/en/stable/pyguitarpro/format.html>,
<https://pyguitarpro.readthedocs.io/en/stable/_modules/guitarpro/models.html>).

> **Sourcing caveat.** The GP8 user-guide PDF
> (<https://static.guitar-pro.com/gp8/manual/Guitar-Pro-8-user-guide.pdf>)
> stores its text with subsetted fonts that did not extract to clean machine
> text. Verbatim wording below is therefore taken from the **GP7** user guide
> (<https://blog.guitar-pro.com/wp-content/uploads/2018/10/GuitarPro7-user-guide.pdf>),
> whose effects/fingering terminology GP8 inherited. GP8-specific details are
> confirmed against GP8-era secondary sources cited inline and flagged where
> not re-confirmed from a clean primary copy.

### Articulations / techniques (DATA unless noted)

- **Hammer-on / pull-off (legato).** HO = second note higher, PO = second note
  lower; series can be linked. Semantic `isHammer` flag.
- **Slides — six distinct types.** From the format enum `SlideType`:
  `intoFromAbove = -2`, `intoFromBelow = -1`, `shiftSlideTo = 1`,
  `legatoSlideTo = 2`, `outDownwards = 3`, `outUpwards = 4`
  (<https://pyguitarpro.readthedocs.io/en/stable/_modules/guitarpro/models.html>).
  So: shift slide (re-picked), legato slide (not re-picked, drawn with a slur),
  slide-in from above/below, slide-out down/up.
- **Harmonics — five–six types.** GP7 names Natural plus artificial family
  **A.H.** (artificial), **T.H.** (tapped), **P.H.** (pinch), **S.H.** (semi);
  GP8 additionally exposes **feedback**, giving "5 of them, including
  artificial, pinch, tap, semi, and feedback"
  (<https://travelingguitarist.com/guide-to-pinch-tap-semi-natural-harmonics-in-guitar-pro/>).
  Natural is entered separately (the `Y` key); the artificial family via a
  dialog choosing harmonic type + sounding note.
- **Bends and sub-types.** Edited in a graphical Bend window; preset shapes
  bend / bend-and-release / bend-release-bend / prebend / prebend-release plus
  a freely editable curve. **JUDGMENT/UNVERIFIED:** the exact GP8 preset labels
  were not lifted from the GP8 PDF (high confidence, standard across GP6/7/8).
  The format models a bend as a type + point curve (`BendType`, `BendEffect`).
- **Whammy / tremolo bar (dive/dip).** A beat-level effect distinct from string
  bends, edited in a Bend-window-like dialog; wide vibrato via the bar is a
  chord-level effect. Discrete whammy shapes are enumerated in the format
  lineage; **UNVERIFIED:** GP8's exact on-screen shape labels.
- **Vibrato — two kinds.** Normal vibrato (little wave) vs **wide vibrato
  (tremolo bar)** (big wave). GP distinguishes depth.
- **Tapping.** **Left-hand tapping** (hit a fret with a fretting finger) and
  two-hand **tapping** (whole-chord effect) are separate.
- **Slap / pop (bass) and relatives.** Slap (thumb), pop (forefinger), dead
  slapped, pick scrape up/down. Format `SlapEffect` = tap/slap/pop.
- **Palm mute.** Per-string attribute over bar ranges (Tools > Palm Mute
  Options), adjustable level.
- **Let ring.** Per-string attribute over bar ranges (Tools > Let Ring
  Options).
- **Dead notes / ghost notes.** Dead = short/muted (X); ghost = played in round
  brackets.
- **Rasgueado.** Flamenco right-hand strum; "Guitar Pro offers **18 rasgueado
  motifs** … interpreted by the audio engine." **UNVERIFIED:** GP8 parity on
  the count of 18 (GP7 figure).
- **Golpe.** Percussion on the guitar body — finger and thumb variants.
- **Tremolo picking.** Repeat a note as fast as possible, with a subdivision;
  a named beat effect (`tremoloPicking`). **UNVERIFIED:** exact GP8 UI label.
- **Trill.** Choose the second-note fret and speed.
- **Grace notes — two kinds.** Before-the-beat and on-the-beat; transition can
  be none/slide/bend/hammer (`GraceEffectTransition`).
- **Staccato.** Dot below; shortens played duration.
- **Accent — two levels.** Accented and heavily accented (`Accentuation`).

### Fingering (DATA)

- **Left-hand fingering.** Shown before the note in standard notation, or under
  the tab if there is no standard staff; label style set in Stylesheet >
  Notation > Fingerings. Format `Fingering` enum (shared by both hands):
  `open/muted = -1`, `thumb = 0`, `index = 1`, `middle = 2`, `ring = 3`,
  `little = 4`. **JUDGMENT:** printed classical LH is conventionally 1–4 with
  0/open and T for thumb; the enum integers are the internal model, not the
  printed glyph.
- **Right-hand fingering — yes, GP8 supports it.** Same placement options; GP8
  lets you pick the lettering scheme under Stylesheet > Notation > Fingerings,
  reportedly `pimac` / `pimax` / `pimae` / `timao` (p = thumb, i = index,
  m = middle, a = ring; the fifth finger written c/x/e by scheme)
  (<https://www.guitar-pro.com/blog/p/17044-tuto-10-tips-to-give-a-professional-look-to-your-scores-in-guitar-pro>).
  **UNVERIFIED:** the four scheme strings are secondary-sourced, not
  re-confirmed from a clean GP8 primary copy — confirm in-app if it matters.

Both fingerings are structured attributes (not free text) but are
**notation-only** and do not affect playback.

## 2. LilyPond capability inventory

Scope: **stable LilyPond 2.24** (`/doc/stable/` 302-redirects to `/doc/v2.24/`).
Primary sources: "Common notation for fretted strings"
(<https://lilypond.org/doc/v2.24/Documentation/notation/common-notation-for-fretted-strings.html>),
"Guitar" (<https://lilypond.org/doc/v2.24/Documentation/notation/guitar>),
StrokeFinger grob
(<https://lilypond.org/doc/v2.24/Documentation/internals/strokefinger>).

- **Hammer-on / pull-off.** Native only as generic slurs `( )`
  (`doubleSlurs = ##t` for both-side arcs). **CONFIRMED limitation:** no
  `\hammerOn`/`\pullOff`, no HO-vs-PO semantics, no automatic "H"/"P". Handled
  by manual markup or left to context. Thread:
  <https://listengine.tuxfamily.org/lilynet.net/tablatures/2009/08/msg00016.html>.
- **Slides.** `\glissando` after a note; on a `TabStaff` it draws a line
  between fret numbers. **One primitive** — no legato/shift/in/out slide types;
  slide-in/out "from nowhere" needs grace-note hacks. Line style is cosmetic
  (`\override Glissando.style`), not slide semantics.
- **Harmonics.** Natural: `\harmonic` (diamond notehead; really open-string /
  12th-fret) and `\flageolet` (small circle articulation). Artificial:
  `\harmonicByFret #N note` (touched fret; LilyPond computes the sounding
  pitch) and `\harmonicByRatio #ratio note`. **No semantic command** for
  tap / harp / pinch / feedback harmonics → text markup.
- **Bends — native in stable 2.24** (contradicts older knowledge). A bend is
  `\^` appended to a note/chord, terminating at the next; requires the bend
  engraver in the tab voice:
  `\context { \TabVoice \consists "Bend_spanner_engraver" }`. Modifiers:
  `\preBend`, `\bendHold`, `\preBendHold`; stacking via `bendStartLevel`;
  note-column skipping via `\skipNC` / `\skipNCs` / `\endSkipNCs`. **CONFIRMED
  limitation:** renders on **TabStaff only**, not a normal 5-line staff.
  **`\bendAfter` is NOT a guitar bend** — it is the jazz fall/doit (grob
  `BendAfter`, `Bend_engraver`), unrelated to the `\^` spanner. History: the
  `\^` machinery grew from the openLilyLib guitar-string-bending snippet
  (<https://github.com/openlilylib/openlilylib/tree/master/notation-snippets/guitar-string-bending>)
  and is now first-class.
- **Dead / ghost notes.** `\deadNote`, `\deadNotesOn`/`\deadNotesOff`; X
  notehead (X in place of the fret on tab).
- **Palm mute.** `\palmMute`, `\palmMuteOn`/`\palmMuteOff`; triangle notehead.
  No automatic "P.M. ----" bracket (add a text spanner).
- **Let ring.** `\laissezVibrer` — an l.v. tie (general, not guitar-specific).
- **Tremolo.** `c4:32` (stem tremolo) or `\repeat tremolo N { … }`. General.
- **Trill.** `\trill`, or `\startTrillSpan`/`\stopTrillSpan`. General.
- **Grace notes.** `\grace`, `\acciaccatura`, `\appoggiatura`. General.
- **Staccato / accents.** `-.`, `->`, `-^`, `--`, `-!`. General.
- **Vibrato.** **No dedicated command** — markup / wiggle line.
- **Tapping.** **No dedicated command** — markup / notehead.
- **Slap / pop.** **Confirmed does not exist** in core LilyPond — markup only.
- **Rasgueado.** **No command** — arpeggio/strum arrows plus "rasg." markup.
- **Golpe.** **No command** in LilyPond — markup.

### Tablature specifics

- **String numbers:** `\N` (e.g. `c4\5`); `\romanStringNumbers` /
  `\arabicStringNumbers`.
- **Full notation on tab:** `\tabFullNotation` (durations, stems, expressive
  marks a bare tab suppresses).
- **Tie/repeat helpers:** `\hideSplitTiedTabNotes`, `\tabChordRepeats`.

### Fingering — the p/i/m/a detail (CONFIRMED, precise)

- **Left-hand:** `-1 -2 -3 -4` after a note (or `\finger`); `0`/`\open` for
  open string. General Fingering grob, reused for the fretting hand.
- **Right-hand (classical p/i/m/a):** `\rightHandFinger #N` (abbreviatable,
  e.g. `\RH`). **You type the number; LilyPond prints the letter** — the
  `StrokeFinger` grob's `digit-names` defaults to `#("p" "i" "m" "a" "x")`, so
  `#1→p`, `#2→i`, `#3→m`, `#4→a`, `#5→x`. Placement via
  `strokeFingerOrientations`. **Gotcha (DATA):** in Scheme note-form, append a
  space before a closing `>` (`<c\rightHandFinger #1 >`) or parsing breaks.

### Capability table

| Technique | Native in stable 2.24? | Command | Main limitation |
|---|---|---|---|
| Hammer-on / pull-off | Partial | slur `( )` | No HO/PO distinction; add "H"/"P" |
| Slide | Yes | `\glissando` | One primitive; no slide sub-types |
| Natural harmonic | Yes | `\harmonic`, `\flageolet` | Really open-string / 12th fret |
| Artificial harmonic | Yes | `\harmonicByFret #N`, `\harmonicByRatio #r` | Not tap/pinch/semi/feedback |
| String bend | **Yes** | `\^` + `Bend_spanner_engraver`; `\preBend`, `\bendHold` | **TabStaff only** |
| Fall/doit (NOT a bend) | Yes | `\bendAfter #±N` | Jazz articulation, unrelated |
| Dead / ghost note | Yes | `\deadNote`, `\deadNotesOn/Off` | X notehead only |
| Palm mute | Yes | `\palmMute`, `\palmMuteOn/Off` | Triangle notehead; no auto bracket |
| Let ring | Yes | `\laissezVibrer` | Generic l.v. tie |
| Tremolo | Yes | `c:32`, `\repeat tremolo` | Generic |
| Trill | Yes | `\trill`, trill spanner | Generic |
| Grace notes | Yes | `\grace`, `\acciaccatura` | Generic |
| Staccato / accent | Yes | `-.`, `->`, `-^`, `--` | Generic |
| Vibrato | **No** | markup / wiggle | No `\vibrato` |
| Tapping | **No** | markup / notehead | No `\tap` |
| Slap / pop | **No** | markup | Does not exist in LilyPond |
| Rasgueado | **No** | arpeggio + "rasg." | No `\rasgueado` |
| Golpe | **No** | markup | No command |
| String number | Yes | `\N`, `\roman/\arabicStringNumbers` | — |
| Left-hand fingering | Yes | `-N`, `\finger` | — |
| Right-hand p/i/m/a | Yes | `\rightHandFinger #N` (1=p…5=x) | Space-before-`>` caveat |
| Tab full notation | Yes | `\tabFullNotation` | — |

## 3. Side-by-side gap (the direct answer)

| GP8 annotation | GP8 model | LilyPond | Nature of the gap |
|---|---|---|---|
| Hammer-on vs pull-off | Distinct flags | Both = one slur | **Distinction lost** |
| Slides | 6 types (enum) | 1 `\glissando` line | **Sub-types lost** |
| Harmonics | 5–6 types | Natural + artificial (fret/ratio) | **Pinch/tap/semi/feedback lost** |
| Bends | Full editable curve | Native `\^` (tab only) | Smaller than expected; less freeform |
| Whammy bar | Beat effect, shapes | Partial (bend machinery) | Shape vocabulary thinner |
| Vibrato (normal/wide) | Depth distinction | No command (markup) | **No semantic support** |
| Tapping (LH / two-hand) | Distinct effects | No command (markup) | **No semantic support** |
| Slap / pop | Distinct effects | No command (markup) | **No semantic support** |
| Rasgueado (18 motifs) | Structured motif | No command (markup) | **No semantic support** |
| Golpe (finger/thumb) | Structured effect | No command (markup) | **No semantic support** |
| Palm mute / let ring | Per-string ranges | `\palmMute` / `\laissezVibrer` | Renderable; presentation differs |
| Dead / ghost notes | Flags | `\deadNote` | Parity |
| Left-hand fingering | 0–4 + thumb | `-1…-4`, `\finger` | **Parity** |
| Right-hand fingering | p i m a + c/x/e | `\rightHandFinger` → p i m a x | **Parity** |

## 4. Fingering deep-dive (the maintainer's heavy-use case)

Both hands are fully supported, natively, in both tools — this is the area with
essentially **no gap**:

- **Left hand:** classical 1–4 (index→little), with 0/open and T (thumb).
  LilyPond `-1 -2 -3 -4`; GP8 enum thumb=0 / index=1 … little=4, open=-1.
  (Note: the convention is 1–4 fretting fingers, not 1–5.)
- **Right hand:** classical p/i/m/a (+ the fifth finger as c/x/e). LilyPond
  prints these letters by default from `\rightHandFinger #1..#5` →
  `p i m a x`; GP8 offers selectable letter schemes (`pimac`/`pimax`/`pimae`/
  `timao`). If melete emits right-hand fingering it should expose the same
  letter-scheme choice, since `x` vs `c` vs `e` for the little finger is a real
  editorial preference.

## 5. The interchange pipeline: GP8 → MusicXML → LilyPond

If the goal is to author in GP8 and reproduce in melete's LilyPond output, the
bottleneck is not LilyPond — it is the interchange, which loses data twice.

### GP8 export formats (DATA)

GP8 exports: native `.gp`, plus GPX/GP5, MIDI, ASCII tab, **MusicXML**, PDF,
PNG, audio (MP3/WAV/FLAC/AIFF/Ogg); 8.1 added SVG
(<https://www.guitar-pro.com/blog/p/38236-new-free-updade-guitar-pro-8-1-is-available>,
<https://www.guitar-pro.com/c/10-guitar-pro-new-features>). **JUDGMENT:** MIDI
discards all notation/technique; PDF/PNG/SVG are final-form graphics; ASCII is
unstructured. **MusicXML is the only structured export LilyPond can consume**,
so it is the sole viable bridge despite being lossy.

### What MusicXML itself can and cannot carry (DATA)

Guitar techniques live in `<notations><technical>`. The MusicXML 4.0
`<technical>` children include: `bend, fret, string, fingering, pluck,
hammer-on, pull-off, harmonic, tap, open-string, stopped, golpe, smear,
snap-pizzicato, …`
(<https://www.w3.org/2021/06/musicxml40/musicxml-reference/element-tree>), with
`<slide>`/`<glissando>` as notations siblings.

- **Can represent:** string/fret; hammer-on/pull-off (dedicated elements);
  bends with `<pre-bend>`/`<release>`/`<with-bar>` and a `shape` attribute;
  harmonics as `<natural>`/`<artificial>` with optional touching pitch; slide
  vs glissando; `<tap>` with a `hand` attribute; `<fingering>` (LH) and
  `<pluck>` (RH p-i-m-a). Sources: bend
  <https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/bend/>,
  harmonic
  <https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/harmonic/>,
  slide
  <https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/slide/>,
  tap <https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/tap/>,
  tablature tutorial
  <https://www.w3.org/2021/06/musicxml40/tutorial/tablature/>.
- **Cannot (or weakly):** no dedicated guitar-vibrato element (maps to generic
  `wavy-line`; MuseScore issue
  <https://github.com/musescore/MuseScore/issues/26474>); no encoding for GP8's
  slide **sub-types**; harmonic **sub-types collapse** to natural/artificial;
  palm-mute / let-ring / rake / tremolo-picking are not first-class. The
  tablature tutorial itself flags "sporadic support" for `<bend>`/`<harmonic>`
  across applications.

### Hop A — GP8 → MusicXML (DATA + JUDGMENT)

GP's own 8.1.3/8.1.4 changelog lists as *recent fixes*: "Fingerings are now
correctly exported" (8.1.4) and "Transitions (bend/slide/hammer) are now
correctly exported on grace notes" (8.1.4) — i.e. these were previously broken
(<https://www.guitar-pro.com/c/10-guitar-pro-new-features>). Soundslice (which
imports both formats) advises **not** routing tab through MusicXML because it
"tends to lose information about guitaristic things like bends and harmonics"
(<https://www.soundslice.com/help/en/creating/importing/63/musicxml/>).
**Expect:** harmonic-type collapse, slide sub-type loss, vibrato-depth loss,
and fragile grace-note transitions before 8.1.4. Export from the newest 8.1.x.

### Hop B — MusicXML → LilyPond via `musicxml2ly` (DATA + JUDGMENT)

`musicxml2ly` "extracts notes, articulations, score structure, and lyrics" and
warns some elements are "non-trivial (and sometimes even impossible)" to
convert, with no guarantee list for guitar `<technical>` elements
(<https://lilypond.org/doc/v2.25/Documentation/usage/invoking-musicxml2ly>).
Its author, Reinhold Kainhofer, said it "supports bend" but was unsure about
slides/hammer-ons/pull-offs
(<https://lists.gnu.org/archive/html/lilypond-user/2008-07/msg00095.html>).
LilyPond's older bend machinery also hijacks the slur engraver, so a pull-off
cannot immediately follow a bend release
(<https://lists.libreplanet.org/archive/html/lilypond-user/2014-08/msg00015.html>).
Regression corpus:
<http://lilypond.org/doc/v2.24/input/regression/musicxml/collated-files.html>.
**JUDGMENT:** this is the tighter bottleneck. Fingering, string/fret, and basic
articulations survive best; **hammer-on/pull-off/slide marks and
harmonic/vibrato types are the most likely casualties.**

### Better paths?

There is **no mature direct `.gp` → LilyPond importer.** Soundslice's native GP
importer is higher-fidelity but is not LilyPond. TuxGuitar opens GP files and
exports MusicXML, but its current documented export list omits LilyPond
(<https://tuxguitar.org/can-i-export-my-tuxguitar-projects-to-other-formats/>);
an old LilyPond-export plugin existed historically (**UNVERIFIED** for current
builds). MuseScore 4 imports GP natively then exports MusicXML, but adds a
*third* lossy hop (its own vibrato gap above). **MusicXML remains the best
available bridge and simultaneously the binding constraint.**

## 6. Roadmap implications for melete

Because melete **generates** its own sheets from an internal model (rather than
importing GP8 files), the practical picture is encouraging — LilyPond rendering
is rarely the limiter:

- **Cheap to add** (LilyPond renders natively — needs emitter + model support):
  both-hand fingering (p/i/m/a + 1–4), string bends, natural/artificial
  harmonics, dead/ghost notes, palm mute, let ring, slides-as-glissando,
  HO/PO-as-slur, staccato/accent, grace notes, trills, string numbers.
- **Needs a markup layer** (no semantic LilyPond command): vibrato, tapping,
  slap/pop, rasgueado, golpe, and the finer harmonic types (pinch/tap/semi/
  feedback). melete would define its own model element and emit LilyPond markup
  (or notehead overrides) for these.
- **Won't come for free from a GP8 import** even if such an importer is built:
  HO-vs-PO, slide sub-types, and harmonic sub-types are dropped by the
  pipeline, so melete's own model would have to re-derive them regardless.

**Design steer.** If melete owns the annotation model itself, the LilyPond gap
is small and mostly about adding a markup fallback for five or six techniques.
The GP8-import dream is the constrained path; treat MusicXML import as a
best-effort seed that always needs hand-repair, not a faithful round trip.

## 7. Verification caveats

- The GP8 user-guide PDF resisted clean text extraction; GP8-exact wording is
  GP7-sourced (terminology carried forward).
- Secondary-sourced / **UNVERIFIED**: the RH letter-scheme strings
  (`pimac`/`pimax`/`pimae`/`timao`); "5–6 harmonic types" and the feedback
  abbreviation; the "18 rasgueado motifs" count for GP8; exact GP8 bend/whammy
  preset labels; TuxGuitar's current LilyPond-export availability.
- All LilyPond command claims are confirmed against the 2.24 Notation/Internals
  Reference. Items marked "No command" were not found in those references and
  are reported as absent in stable, not as verified commands.

## References

**Guitar Pro 8**

- User guide (PDF, primary):
  <https://static.guitar-pro.com/gp8/manual/Guitar-Pro-8-user-guide.pdf>
- User-guide support page:
  <https://support.guitar-pro.com/hc/en-us/articles/5018404823069-GP8-Guitar-Pro-8-User-Guide>
- GP7 user guide (verbatim-quote source):
  <https://blog.guitar-pro.com/wp-content/uploads/2018/10/GuitarPro7-user-guide.pdf>
- Features: <https://www.guitar-pro.com/c/14-guitar-pro-features>
- What's new / changelog: <https://www.guitar-pro.com/c/10-guitar-pro-new-features>
- 8.1 release: <https://www.guitar-pro.com/blog/p/38236-new-free-updade-guitar-pro-8-1-is-available>
- Starter guide: <https://www.guitar-pro.com/blog/p/35844-guitar-pro-8-new-features-explained-starter-guide>
- Harmonics types/entry:
  <https://travelingguitarist.com/guide-to-pinch-tap-semi-natural-harmonics-in-guitar-pro/>
- Slides/slurs semantics:
  <https://jpirie23.wordpress.com/2014/07/06/slurs-slides-tags-in-guitar-pro-6-and-empty-segments/>
- RH fingering scheme tip:
  <https://www.guitar-pro.com/blog/p/17044-tuto-10-tips-to-give-a-professional-look-to-your-scores-in-guitar-pro>
- File-format enums (PyGuitarPro):
  <https://pyguitarpro.readthedocs.io/en/stable/pyguitarpro/format.html>,
  <https://pyguitarpro.readthedocs.io/en/stable/_modules/guitarpro/models.html>

**LilyPond**

- Common notation for fretted strings:
  <https://lilypond.org/doc/v2.24/Documentation/notation/common-notation-for-fretted-strings.html>
- Guitar: <https://lilypond.org/doc/v2.24/Documentation/notation/guitar>
- StrokeFinger grob (p/i/m/a defaults):
  <https://lilypond.org/doc/v2.24/Documentation/internals/strokefinger>
- List of articulations:
  <https://lilypond.org/doc/v2.23/Documentation/notation/list-of-articulations>
- BendAfter (fall/doit):
  <https://lilypond.org/doc/v2.23/Documentation/internals/bendafter>
- Right-hand fingerings (dev):
  <https://lilypond.org/doc/v2.25/Documentation/notation/right_002dhand-fingerings>
- HO/PO thread:
  <https://listengine.tuxfamily.org/lilynet.net/tablatures/2009/08/msg00016.html>
- openLilyLib guitar-string-bending:
  <https://github.com/openlilylib/openlilylib/tree/master/notation-snippets/guitar-string-bending>
- musicxml2ly regression corpus:
  <http://lilypond.org/doc/v2.24/input/regression/musicxml/collated-files.html>

**MusicXML & interchange**

- Element tree:
  <https://www.w3.org/2021/06/musicxml40/musicxml-reference/element-tree>
- bend: <https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/bend/>
- harmonic:
  <https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/harmonic/>
- slide: <https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/slide/>
- tap: <https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/tap/>
- hammer-on:
  <https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/hammer-on>
- Tablature tutorial:
  <https://www.w3.org/2021/06/musicxml40/tutorial/tablature/>
- musicxml2ly invocation:
  <https://lilypond.org/doc/v2.25/Documentation/usage/invoking-musicxml2ly>
- musicxml2ly author on technique support:
  <https://lists.gnu.org/archive/html/lilypond-user/2008-07/msg00095.html>
- Bend/slur engraver conflict:
  <https://lists.libreplanet.org/archive/html/lilypond-user/2014-08/msg00015.html>
- Soundslice on MusicXML tab loss:
  <https://www.soundslice.com/help/en/creating/importing/63/musicxml/>
- MuseScore guitar-vibrato export gap:
  <https://github.com/musescore/MuseScore/issues/26474>
- TuxGuitar export formats:
  <https://tuxguitar.org/can-i-export-my-tuxguitar-projects-to-other-formats/>
