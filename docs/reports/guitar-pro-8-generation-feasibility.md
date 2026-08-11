# Feasibility of Auto-Generating Guitar Pro 8 Files

**Status:** research finding (reference). **Date:** 2026-08-11.
**Tracking issue:** mnemosys-project/melete#67.
**Method:** parallel web-research passes plus a live GitHub/PyPI viability
sweep (metrics as of 2026-08-11). Every URL is real and checkable. Claims that
could not be confirmed from a clean primary source are flagged **UNVERIFIED**.
Throughout, **DATA** = "a cited source states this"; **JUDGMENT** = "our
inference on top of the data."

## Why this exists

melete engraves through LilyPond, but the annotation gap analysis
(mnemosys-project/melete#65) confirmed LilyPond has **no semantic support** for
several techniques the maintainer relies on — above all **two-handed tapping**.
Guitar Pro's data model *does* represent these. This report asks whether melete
could emit a Guitar Pro file directly from its internal model, as an additional
(or alternative) output to LilyPond PDF, and how feasible each generation path
is. No code is written here.

## Summary — the headline

The premise that "writing Guitar Pro files is rare, and PyGuitarPro (GP3–GP5
binary) is the only real writer" is **out of date**. **alphaTab ships a working
native `.gp` (GP7/8) writer — `Gp7Exporter` — since v1.2.0**, present and tested
in an actively-developed repo. That is a genuine high-fidelity path to the
modern `.gp` format that does not require hand-rolling the gpif XML. The catch:
alphaTab is TypeScript/C#/Kotlin, not Python, so using it from melete means a
Node.js (or .NET) sidecar process.

The pure-Python option, **PyGuitarPro**, is alive but **permanently capped at
GP5** — community PRs adding GP6/7/8 were closed unmerged — so it is a
functional dead-end for modern-format fidelity even though it is maintained.

## 1. The Guitar Pro file formats

- **GP6/GP7/GP8 `.gp`** — a **ZIP container** wrapping `Content/score.gpif`, an
  XML document ("gpif"), alongside `Content/Preferences.json` and binary
  `BinaryStylesheet` / `PartConfiguration` / `LayoutConfiguration` members
  (display/layout). DATA: community write-up and MuseScore discussion
  (<https://musescore.org/en/node/247546>; GP7 format doc
  <https://musescore.org/sites/musescore.org/files/2017-08/the_guitarpro_7_file%20format.doc>).
- **`.gpx` (GP6)** — an older container that also wraps `score.gpif`, but inside
  a custom "BCFZ/BCFS" compressed filesystem rather than a plain ZIP. DATA:
  alphaTab GP6 format page (<https://alphatab.net/docs/formats/guitar-pro-6>).
- **Legacy binary `.gp3/.gp4/.gp5`** — proprietary binary formats, extensively
  reverse-engineered and well-supported by open tooling (PyGuitarPro,
  TuxGuitar).
- **GP8 specifics** — same ZIP+gpif design as GP7, with extras (e.g. audio
  tracks) and an extended `score.gpif`. GP8 can **encrypt** `score.gpif` when a
  file is "locked for editing" (AES-256-CBC, PBKDF2-HMAC-SHA1). DATA:
  reverse-engineering write-up
  (<https://wangyi.ai/blog/2026/01/16/unlocking-guitar-pro-8/>). **JUDGMENT:**
  locking is opt-in and concerns *reading* locked files; ordinary generated
  files are unencrypted plain gpif, so encryption is not a blocker for
  *generating* files.
- **Schema status** — **there is no official public gpif schema** from Arobas
  Music. The format is "documented" primarily as running code in alphaTab,
  TuxGuitar, and MuseScore importers/exporters. **JUDGMENT:** every tool in this
  space reverse-engineers the format; that is an accepted, shared risk.

## 2. Libraries that can WRITE Guitar Pro files

The read-vs-write distinction is decisive: many libraries *read* GP8 but cannot
*write* it. Writers are rare.

- **alphaTab** (TypeScript / C# / Kotlin, **MPL-2.0**) — **writes native `.gp`
  (GP7/8)**. DATA: the exporter guide documents `Gp7Exporter` (since v1.2.0) and
  `AlphaTexExporter` (since v1.7.0):
  <https://alphatab.net/docs/guides/exporter>;
  `Gp7Exporter` reference "can write Guitar Pro 7+ (gp) files"
  (<https://alphatab.net/docs/reference/types/exporter/gp7exporter/>). It
  **reads** GP3–8, MusicXML, Capella, and alphaTex; it **writes** only GP7+
  (`.gp`) and alphaTex (no `.gpx` or MusicXML exporter). Source presence
  confirmed in-repo: `packages/alphatab/src/exporter/Gp7Exporter.ts` with a
  matching `test/exporter/Gp7Exporter.test.ts` (verified via the repo tree). A
  minimal call:

  ```js
  const exporter = new alphaTab.exporter.Gp7Exporter();
  const data = exporter.export(api.score, api.settings); // Uint8Array -> write .gp
  ```

  **UNVERIFIED:** the docs guarantee full technique fidelity explicitly only for
  the *alphaTex* exporter, not `Gp7Exporter`; a round-trip smoke test (export,
  reopen in Guitar Pro 8) is needed to confirm every subtype survives.
- **PyGuitarPro** (Python, **LGPL-3.0**) — writes **GP3/GP4/GP5 only**, via
  `guitarpro.write()`. DATA: <https://pyguitarpro.readthedocs.io/>,
  <https://github.com/Perlence/PyGuitarPro>. It **cannot** write `.gp`/`.gpx`
  (GP6–8). Community PRs adding GP6/7/8 (#58, #62, #63) were **closed unmerged**
  — so the GP5 ceiling is persistent, not incidental.
- **TuxGuitar** (Java, LGPL) — writes GP3/GP4/GP5; **read-only** for `.gpx`
  (GP6); does **not** export gpif/GP7. DATA:
  <https://en.wikipedia.org/wiki/TuxGuitar>,
  <https://sourceforge.net/p/tuxguitar/bugs/105/>. **JUDGMENT:** same writable
  ceiling as PyGuitarPro (GP5) but a much heavier Java/SWT dependency.
- **MuseScore** — **imports GP, does not export it**; its recommended
  interchange out is MusicXML. DATA: <https://musescore.org/en/node/72676>,
  <https://musescore.org/en/node/306915>.
- **Other writers** — `slundi/guitarpro` (Rust) claims GP3–5 plus *early* GP6/7
  write support (maturity **UNVERIFIED**): <https://github.com/slundi/guitarpro>.
  `Sheetmusic4J`, `libgp`, `parsegp`, DGuitar, gp2tab are readers, not writers.

## 3. Fidelity for advanced notation (tapping et al.)

- **alphaTab GP7 path (highest fidelity).** DATA: the alphaTab GP7 feature table
  marks Left-Hand Tapping, LH/RH fingering, natural & artificial harmonics,
  slides, and bends as fully supported
  (<https://alphatab.net/docs/formats/guitar-pro-7>). Because the exporter
  writes the same gpif the importer reads, these should round-trip — subject to
  the smoke-test caveat above.
- **PyGuitarPro GP5 path (legacy, but techniques ARE encoded).** DATA (model
  source
  <https://pyguitarpro.readthedocs.io/en/stable/_modules/guitarpro/models.html>):
  `NoteEffect` carries `bend`, `grace`, `hammer`, `harmonic`, `leftHandFinger`,
  `rightHandFinger`, `slides`, `tremoloPicking`, `trill`; `SlapEffect =
  none/tapping/slapping/popping` (tapping lives here); `HarmonicEffect` subtypes
  Natural/Artificial/Tapped/Pinch/Semi; full `SlideType` enum; `Fingering` enum
  for both hands. **JUDGMENT:** GP5 genuinely encodes tapping, harmonic and
  slide sub-types, bends, and fingering — but tapping is a **single flag** with
  **no two-handed vs left-hand distinction**, which the modern gpif model does
  carry. For a maintainer whose repertoire leans on two-handed tapping, that is
  the decisive shortfall of the GP5 path.

## 4. Candidate generation strategies, ranked

| Rank | Strategy | Writes | Fidelity | Effort from Python | Verdict |
|---|---|---|---|---|---|
| **1** | **alphaTab `Gp7Exporter` via a Node.js sidecar** (ideally fed **alphaTex** text that melete emits) | native `.gp` (GP7/8) | **Highest** — LH tapping, fingering, harmonics, slides, bends | Medium — Node bridge | **Recommended** for modern-format fidelity |
| 2 | **PyGuitarPro → `.gp5`** | `.gp5` binary | High-ish; **coarse tapping** (single flag) | **Lowest** — pure Python | Pragmatic but format-frozen; tapping shortfall |
| 3 | Hand-write gpif XML + zip it | `.gp` | Potentially high; you own a reverse-engineered, unspecified schema | High | Not worth it — alphaTab already does this |
| 4 | Emit MusicXML → import into Guitar Pro | via GP importer | **Lowest** for tab technique (lossy) | Low | Last resort only |

**JUDGMENT — recommended path.** For melete's stated priority (two-handed
tapping), the target is **melete → alphaTex text → alphaTab → `Gp7Exporter` →
`.gp`**. alphaTex is a compact, LaTeX-like text format that is a natural
string-generation target from Python and avoids constructing alphaTab's object
graph across a process boundary. PyGuitarPro `.gp5` remains a viable
dependency-light fallback **only if** the two-handed-tapping distinction is not
required. Avoid hand-writing gpif and treat MusicXML as last-resort interchange.

## 5. Generation-library viability (metrics as of 2026-08-11)

Live GitHub/PyPI data; commit windows counted via the commits API. See the
sibling report (melete#68) for the full multi-product viability sweep.

| Library | License | ★ | Latest release | Rel/24mo | Commits/12mo | Contributors (bus factor) | Class |
|---|---|---|---|---|---|---|---|
| **alphaTab** (`CoderLine/alphaTab`) | MPL-2.0 | 1,790 | v1.8.4 · 2026-07-05 | 14 | **378** | 30 (**~1**, D. Kuschny) | **actively-developed** |
| PyGuitarPro (`Perlence/PyGuitarPro`) | LGPL-3.0 | 363 | 0.11 · 2026-05-03 (PyPI) | 4 | 48 (1 in last 3mo) | 5 (1) | **stable-plateaued, GP5-capped** |

Sources: <https://api.github.com/repos/CoderLine/alphaTab>,
<https://github.com/CoderLine/alphaTab/releases>,
<https://pypi.org/pypi/PyGuitarPro/json>,
<https://github.com/Perlence/PyGuitarPro>.

**JUDGMENT.** alphaTab leads every activity metric (378 commits/12mo, a release
roughly every 6–8 weeks, PRs merged the day the metrics were pulled) and is the
only candidate that is *both* actively developed *and* a writer of the modern
`.gp` format. Its one real risk is **bus factor ~1** (essentially Daniel
Kuschny). Mitigations: MPL-2.0 licence, a pinned version, and the fact that a
library — unlike a hosted service — keeps working from a pinned copy even if
upstream stalls. PyGuitarPro is genuinely maintained but the closed GP6/7/8 PRs
make its GP5 ceiling a hard functional blocker for this use case.

## 6. Legal / licensing posture

- **gpif is reverse-engineered, not officially open** — no published schema or
  license grant from Arobas Music. **JUDGMENT:** no evidence of any restriction
  on *generating* unlocked `.gp` files; multiple open-source projects produce
  them. GP8's file-locking encryption governs *reading locked files*, not
  *creating* files (<https://wangyi.ai/blog/2026/01/16/unlocking-guitar-pro-8/>).
- **Library licences (DATA):** alphaTab **MPL-2.0** (file-level copyleft; easy
  to satisfy when shelling out to it as a separate process); PyGuitarPro
  **LGPL-3.0** (fine as a `pip` dependency); TuxGuitar LGPL/GPL.

## 7. Verification caveats

- alphaTab `Gp7Exporter` per-subtype fidelity (two-handed vs LH tapping, pinch/
  semi harmonics) — **UNVERIFIED**; needs a round-trip smoke test in Guitar Pro
  8.
- alphaTab npm package name (likely `@coderline/alphatab`) — confirm on npm.
- `slundi/guitarpro` GP6/7 write maturity, and DGuitar/gp2tab exact scope —
  **UNVERIFIED**.
- GP8 build/version dates cited elsewhere derive from third-party mirrors in
  places — treat precise dates as indicative.

## References

- alphaTab exporter: <https://alphatab.net/docs/guides/exporter> ·
  <https://alphatab.net/docs/reference/types/exporter/gp7exporter/> ·
  GP7 features <https://alphatab.net/docs/formats/guitar-pro-7> ·
  formats overview <https://alphatab.net/docs/formats/overview> ·
  repo <https://github.com/CoderLine/alphaTab>
- PyGuitarPro: <https://pyguitarpro.readthedocs.io/> ·
  <https://github.com/Perlence/PyGuitarPro> ·
  model <https://pyguitarpro.readthedocs.io/en/stable/_modules/guitarpro/models.html>
- GP `.gp`/gpif structure: <https://musescore.org/en/node/247546> ·
  GP7 format doc
  <https://musescore.org/sites/musescore.org/files/2017-08/the_guitarpro_7_file%20format.doc>
- GP8 encryption / reverse-engineering:
  <https://wangyi.ai/blog/2026/01/16/unlocking-guitar-pro-8/>
- TuxGuitar: <https://en.wikipedia.org/wiki/TuxGuitar> ·
  <https://sourceforge.net/p/tuxguitar/bugs/105/>
- MuseScore import-only: <https://musescore.org/en/node/72676> ·
  <https://musescore.org/en/node/306915>
- Other writers: <https://github.com/slundi/guitarpro>
- Viability data: <https://api.github.com/repos/CoderLine/alphaTab> ·
  <https://pypi.org/pypi/PyGuitarPro/json>
