# Notation/Tab Display Targets and Open-Source Viability

**Status:** research finding (reference). **Date:** 2026-08-11.
**Tracking issue:** mnemosys-project/melete#68.
**Method:** web-research on the product landscape plus a live GitHub/GitLab
viability sweep (all metrics **as of 2026-08-11**, pulled from the REST APIs and
vendor changelogs). Every URL is real and checkable. **DATA** = a cited source
states it; **JUDGMENT** = our inference. Unconfirmed items are flagged
**UNVERIFIED**.

## Why this exists

LilyPond gives melete a pure open-source, code-only pipeline, already proven in
v1. But for advanced guitar technique — especially two-handed tapping — a
purpose-built guitar product renders far better. This report surveys
alternatives to Guitar Pro 8 as **display targets** for melete-generated
scores, identifies which formats reach the most high-fidelity displays, and
scores each open-source option for **project viability** using the criteria the
maintainer set: rate of change, contributor base, release recency/cadence, and
community activity — with a maturity adjustment so that a stable, still-
responsive project is not mistaken for a dead one. No code is written here.

## Summary — the headline

Two independent questions (how to *generate* Guitar Pro files, and what to use
to *display* generated scores) **converge on one tool: alphaTab.** It is the
only open-source engine that is *both* actively developed *and* renders
two-handed tapping well, and it also writes native `.gp` (see the sibling
report, melete#67). The elegant architecture is: **melete emits alphaTex text**,
and alphaTab produces **both** an image (SVG/PNG for people who don't use Guitar
Pro) **and** a `.gp` file (for the Guitar Pro / TablEdit / MuseScore / TuxGuitar
/ Soundslice ecosystem). Emit **Guitar Pro `.gp`**, not MusicXML — `.gp` is both
the highest-fidelity path for tapping and the widest-imported guitar format.

## 1. The "Tablatures" product: TablEdit (confirmed)

DATA: the product the maintainer refers to as "Tablatures" is **TablEdit**
(extension `.tef`), a long-standing fretted-instrument tablature/notation editor
(<https://tabledit.com/>).

- **Imports:** ASCII, MIDI, ABC, **Guitar Pro**, PowerTab, Bucket O' Tab,
  TabRite, Wayne Cripps, **MusicXML**, score images/PDF.
- **Exports:** native `.tef`, ASCII, HTML, ABC, RTF, MIDI, NIFF, **LilyPond**,
  audio, images. (<https://tabledit.com/help/english_m/file_menu.shtml>)
- **Technique depth:** hammer-on, pull-off, bends, chokes, slides, vibrato,
  grace notes, muted notes, rasgueado, fingerings and pick strokes; a dedicated
  **two-handed tapping** primitive is **UNVERIFIED** (not found in docs).
- **Platform / price:** Windows and macOS (sold separately) plus lite mobile
  viewers; **$59.97 USD** each edition (**€50** in Europe) with free upgrades
  (<https://tabledit.com/reg/upgradepolicy.shtml>).
- **Automation:** no documented CLI/API — a desktop GUI app.

**JUDGMENT.** TablEdit is a credible interoperability hub (reads GP + MusicXML,
writes LilyPond/MIDI/MusicXML), but as a *code-pipeline display target* it is
weak: proprietary, paid, GUI-only, no API, no confirmed tapping primitive. Its
value to melete is as a **`.gp` consumer a human opens**, which we get for free
by emitting `.gp` — not as an automatable renderer.

## 2. Display-target landscape

| Product | OSS/proprietary | Imports melete could emit | Tapping / technique depth | Headless / programmatic |
|---|---|---|---|---|
| **alphaTab** (library) | OSS (MPL-2.0) | **alphaTex** text, or its data-model API; reads `.gp`, MusicXML | **Two-handed tapping** explicit (`{tt}` beat + `{lht}` note), full harmonic family | **Yes** — Node low-level API → SVG; PNG via alphaSkia; PDF downstream |
| **MuseScore 4** | OSS (GPL-3.0) | **MusicXML**, Guitar Pro, `.mscz` | Good via GP import; MusicXML import loses guitar articulations | CLI (`mscore -o`/`-j`); often needs `xvfb` |
| **TuxGuitar** | OSS (LGPL) | **Guitar Pro**, MusicXML, PowerTab, TablEdit, MIDI | Strong (GP-lineage model) | Java; no first-class CLI documented |
| **TablEdit** | Proprietary ($59.97) | Guitar Pro, MusicXML, MIDI, ASCII | Bends/slides/HO-PO/harmonics; tapping UNVERIFIED | None |
| **Soundslice** | Proprietary (web) | **Guitar Pro (native)**, MusicXML, PowerTab, TuxGuitar | High-fidelity display; recommends GP over MusicXML | **Data API** (paid + permission-gated) |
| **VexFlow/VexTab** | OSS (MIT*) | **VexTab** text | Single-note tap `t`; two-handed distinction UNVERIFIED/limited | JS, browser-first; SVG via DOM shim |
| **Verovio** | OSS (LGPL-3.0) | MEI / MusicXML | **No** modern guitar tab (lute/historical tab only) | **Yes** — JS *and* Python toolkits |
| **abcjs** | OSS (MIT*) | ABC | Folk-oriented; no tapping | JS |
| Sibelius / Dorico / Finale | Proprietary | MusicXML | Full TAB (Dorico best); MusicXML import lossy for guitar | Not automation-friendly |
| Power Tab Editor | OSS (GPL-3.0) | PowerTab, Guitar Pro | Bends/harmonics/slides; tapping UNVERIFIED | Desktop app |
| Songsterr | Proprietary (web) | — (read-only public API) | Interactive playback | No self-ingest |

\* SPDX unconfirmed — GitHub reports `NOASSERTION` for VexFlow/VexTab/abcjs; MIT
is documented but not independently verified here.

Sources: alphaTab <https://github.com/CoderLine/alphaTab>,
<https://alphatab.net/docs/alphatex/introduction>; MuseScore CLI
<https://handbook.musescore.org/appendix/command-line-usage>; TuxGuitar formats
<https://tuxguitar.org/which-file-formats-does-tuxguitar-support/>; TablEdit
<https://tabledit.com/>; Soundslice data API
<https://www.soundslice.com/help/data-api/> and GP-over-MusicXML advice
<https://www.soundslice.com/help/en/creating/importing/64/guitar-pro/>; VexTab
<https://vexflow.com/vextab/>; Verovio <https://www.verovio.org/>; abcjs
<https://docs.abcjs.net/visual/tablature>.

## 3. Interoperability hubs — which format reaches the most high-fidelity displays

DATA/JUDGMENT: **Guitar Pro `.gp` is the dominant interoperability hub for
guitar technique.** It is imported natively by MuseScore, TuxGuitar, TablEdit,
Power Tab, Soundslice, Songsterr, and alphaTab. Multiple independent sources
state MusicXML *loses* guitar-specific information (bends, harmonics) and that a
native GP importer is "much higher-fidelity" (Soundslice:
<https://www.soundslice.com/help/en/creating/importing/64/guitar-pro/>).
MusicXML is the widest-reaching *general-notation* hub (Finale/Sibelius/Dorico/
MuseScore import it — <https://blog.dorico.com/musicxml-export-and-import/>) but
is the **lossy** path for guitar articulations. MIDI carries no tab/technique
semantics.

**JUDGMENT:** for melete's tapping priority, **emit `.gp`, not MusicXML.** GP is
both the highest-fidelity path *and* the most widely imported guitar format.

## 4. Open-source viability sweep (metrics as of 2026-08-11)

Live data from the GitHub REST API (and the GitLab API for LilyPond, whose
authoritative repo is on GitLab). Commit windows counted via the commits API
with `since=`/`until=` and `Link`-header pagination. "Bus factor" = concentration
of recent substantive commits.

### The rubric

Score each project on **release recency** (age of last release), **release
cadence** (releases/24mo), **rate of change** (commits/12mo), **contributor base
+ bus factor**, and **community/adoption** (stars, issue responsiveness) — with
a **maturity adjustment**: a feature-complete project that still ships and
answers issues is *not* penalized for low churn; a year of silence is.

### Code-side render/generate libraries

| Project | License | ★ | Latest release | Rel/24mo | Commits/12mo | Contributors (bus factor) | Class |
|---|---|---|---|---|---|---|---|
| **alphaTab** | MPL-2.0 | 1,790 | v1.8.4 · 2026-07-05 | 14 | **378** | 30 (**~1**) | **actively-developed** |
| Verovio | LGPL-3.0 | 909 | 6.2.1 · 2026-05-22 | ~12 | **669** | ~91 (3–4) | **actively-developed** (wrong domain: no guitar tab) |
| abcjs | MIT* | 2,320 | 6.7.0 · 2026-08-07 | ~10 | 128 | ~55 (1) | actively-developed (poor fit) |
| VexFlow | MIT* | 4,362 | 4.2.6 · 2024-08-26 | ~2 | **0** | ~106 (low) | **dormant** |
| VexTab | MIT* | 650 | v4.0.4 tag · 2026-01 | 0 (no releases) | 16 | ~12 (1) | dormant/sporadic |

### Human-facing editors (reached by emitting `.gp`)

| Product | License | ★ | Latest release | Commits/12mo | Contributors | Class |
|---|---|---|---|---|---|---|
| **MuseScore 4** | GPL-3.0 | 14,965 | v4.7.4 · 2026-07-07 | **6,160** | 352 | **actively-developed** (corporate-backed; single-vendor governance) |
| **TuxGuitar** | LGPL | 1,432 | 2.1.0 · 2026-07-22 | 385 | 33 (bus factor ~2) | **actively-developed** (revived fork; old SourceForge dormant) |
| Power Tab Editor | GPL-3.0 | 626 | 2.0.22 · 2025-06-29 | 31 | 49 | stable-plateaued/slowing; desktop app not a library |

### The incumbent, for comparison

| Project | License | Latest release | Commits/12mo | Contributors | Class |
|---|---|---|---|---|---|
| **LilyPond** (GitLab) | GPL-3.0 | v2.27.2 · 2026-08-02 (dev); stable 2.26.0 · 2026-04-21 | **841** | 35 | **actively-developed** (mature, GNU) |

**LilyPond is not a migration candidate on activity grounds** — last commit
2026-08-07, 38 merge requests merged in ~60 days, monthly releases. Any move
away from it must rest on *fit and multi-output*, not on it being unmaintained.
(GitLab stars, 101, understate reach; popularity lives at lilypond.org and the
GitHub mirror.)

### Proprietary products (viability by vendor activity)

| Product | Latest | Class | Note |
|---|---|---|---|
| **Guitar Pro 8** (Arobas Music) | 8.1.5 · 2025-10-27 | mature-steady | ~30-yr vendor; still the strongest advanced-notation tool; no GP9 announced |
| **TablEdit** | 3.06a4 · 2026-03-21 | mature-steady | ~29 yr, niche, GUI-only, no API; reads `.gp` |
| **Soundslice** | rolling · 2026-05-22 | **actively-developed** | SaaS, GP-ingesting API; ~3-person team (continuity risk) |

Sources: <https://api.github.com/repos/CoderLine/alphaTab>,
<https://api.github.com/repos/musescore/MuseScore>,
<https://api.github.com/repos/helge17/tuxguitar>,
<https://gitlab.com/api/v4/projects/lilypond%2Flilypond>,
<https://api.github.com/repos/rism-digital/verovio>,
<https://api.github.com/repos/0xfe/vexflow>,
<https://api.github.com/repos/0xfe/vextab>,
<https://api.github.com/repos/paulrosen/abcjs>,
<https://api.github.com/repos/powertab/powertabeditor>;
Guitar Pro <https://en.wikipedia.org/wiki/Guitar_Pro>;
TablEdit <https://tabledit.com/full.txt>;
Soundslice <https://www.soundslice.com/changelog/>.

## 5. Recommendations

1. **Primary display target: alphaTab (OSS, MPL-2.0).** The only OSS engine that
   is both actively developed and renders two-handed tapping (`{tt}` + `{lht}`),
   with a documented headless Node path (→ SVG, alphaSkia → PNG). melete emits
   **alphaTex**; alphaTab renders images *and* exports `.gp`.
2. **Secondary (human-facing, reached via `.gp`): MuseScore 4 and TuxGuitar** —
   both free, cross-platform, actively developed, and import `.gp` with good
   technique fidelity. TablEdit joins this set for users who own it.
3. **Best proprietary hosted option: Soundslice** — GP-ingesting data API, high
   fidelity, but paid + permission-gated and a small-team continuity risk.
4. **Not recommended as primary targets:** VexFlow/VexTab (dormant), Verovio and
   abcjs (active but no modern guitar-technique tab), Sibelius/Dorico/Finale
   (paid, MusicXML-only interchange = the lossy guitar path), Songsterr
   (read-only).

**The one risk to weigh:** alphaTab is **bus-factor ~1** (essentially Daniel
Kuschny). Mitigations: MPL-2.0, pin a version, and — being a library rather than
a hosted service — a pinned copy keeps working even if upstream stalls.

## 6. Verification caveats

- SPDX license IDs for VexFlow/VexTab/abcjs (GitHub `NOASSERTION`; MIT documented
  but not independently confirmed).
- "Active-in-last-12-months" contributor head-counts were estimated from commit
  volume and top-contributor concentration, not exhaustively enumerated.
- TablEdit two-handed-tapping primitive; TablEdit pre-2026 version dates and
  vendor legal name; all proprietary pricing; Guitar Pro 8.1.x build dates
  (third-party mirrors); Soundslice user base — **UNVERIFIED**.
- MuseScore tapping fidelity *from MusicXML import* — **UNVERIFIED**; test on a
  real tapping sample before relying on it.

## References

Grouped source list (all real, checkable):

- **alphaTab:** <https://github.com/CoderLine/alphaTab> ·
  <https://alphatab.net/docs/alphatex/introduction> ·
  <https://alphatab.net/docs/guides/nodejs> ·
  <https://alphatab.net/docs/formats/guitar-pro-8>
- **MuseScore:** <https://musescore.org> ·
  <https://handbook.musescore.org/appendix/command-line-usage> ·
  <https://github.com/musescore/MuseScore>
- **TuxGuitar:** <https://tuxguitar.org/which-file-formats-does-tuxguitar-support/> ·
  <https://github.com/helge17/tuxguitar> · <https://en.wikipedia.org/wiki/TuxGuitar>
- **LilyPond:** <https://gitlab.com/lilypond/lilypond> · <https://lilypond.org>
- **TablEdit:** <https://tabledit.com/> ·
  <https://tabledit.com/help/english_m/file_menu.shtml> ·
  <https://tabledit.com/reg/upgradepolicy.shtml>
- **Soundslice:** <https://www.soundslice.com/help/data-api/> ·
  <https://www.soundslice.com/help/en/creating/importing/64/guitar-pro/> ·
  <https://www.soundslice.com/changelog/>
- **VexFlow / VexTab:** <https://github.com/0xfe/vexflow> ·
  <https://vexflow.com/vextab/> · <https://github.com/0xfe/vextab>
- **Verovio:** <https://www.verovio.org/> · <https://github.com/rism-digital/verovio>
- **abcjs:** <https://docs.abcjs.net/visual/tablature> ·
  <https://github.com/paulrosen/abcjs>
- **Power Tab:** <https://powertab.github.io/> ·
  <https://github.com/powertab/powertabeditor>
- **Guitar Pro:** <https://www.guitar-pro.com> · <https://en.wikipedia.org/wiki/Guitar_Pro>
- **MusicXML interchange:** <https://blog.dorico.com/musicxml-export-and-import/>
