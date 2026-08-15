# alphaTex tapping-effect feasibility (spike, epic #67 Task A1)

**Verdict: `expressible in alphaTex`.**

melete's only render path — families emit alphaTex, the vendored `melete-render/`
tool parses it with `@coderline/alphatab` 1.8.4 and exports a Guitar Pro `.gp` —
**can express every articulation and per-hand fingering the two-hand tapping epic
needs**, using first-class alphaTex note/beat effect tokens. No lower-level
channel is required; the emitter task (D1) proceeds as planned.

This settles spec [§8](../../..) outcome 1 ("alphaTex expresses them — proceed as
planned"). The go/no-go is **go**.

## The tokens

Every effect has a direct token that the alphaTex parser accepts and that
round-trips to the expected `Content/score.gpif` property. Note effects go inside
the note's `{…}` brace (`<fret>.<string>{…}.<duration>`), exactly where the
emitter already writes `acc` / `lf` / `ac`.

| Effect (spec §4 vocabulary) | alphaTex token | Level | Sets on the alphaTab model | GPIF property (how the R&D survey detects it) |
|---|---|---|---|---|
| **Right-hand tap** — `(RIGHT, TAPPED)` | `tt` | beat | `beat.tap = true` | Note `Tapped` (`<Enable/>`) |
| **Left-hand tap** — `(LEFT, TAPPED)` | `lht` | note | `note.isLeftHandTapped = true` | Note `LeftHandTapped` |
| **Hammer-on** — `SLURRED`, ascending | `h` on the **origin** note | note | `note.isHammerPullOrigin = true` | `HopoOrigin` on origin, `HopoDestination` on the next note |
| **Pull-off** — `SLURRED`, descending | `h` on the **origin** note (same token) | note | `note.isHammerPullOrigin = true` | `HopoOrigin` / `HopoDestination` (identical to hammer-on) |
| **Right-hand fingering** | `rf <1–5>` | note | `note.rightHandFinger` | Note `RightFingering` (letter code) |
| Left-hand fingering (already emitted) | `lf <1–5>` | note | `note.leftHandFinger` | Note `LeftFingering` (letter code) |

Source of truth for the tokens: the alphaTex parser's own effect switch in the
vendored dist (`/usr/lib/node_modules/@coderline/alphatab/dist/alphaTab.js`,
in-container). `lht`, `h`, `lf`, `rf`, `acc`, … are cases in the **note**-effect
switch (`AlphaTex1LanguageHandler.applyNoteProperty`); `tt`, `s`, `p`, `v`, … are
cases in the **beat**-effect switch (`applyBeatProperty`). The host does not carry
the dist; the container does (melete#85), so this was read in-container.

## Method and evidence

Two independent confirmations, per the plan's Steps 1 and 2.

**Step 1 — render a probe and inspect the GPIF.** A throwaway alphaTex exercising
all five effects was rendered in-container and the resulting `.gp`'s
`Content/score.gpif` unzipped and grepped the way the R&D survey detected tapping.
The probe (standard-tuned, 6-string, two 4/4 bars):

```
\ts 4 4 \tempo 120 3.3{h}.4 5.3.4 5.3{h}.4 3.3.4 |
7.2{lht}.4 5.1{tt rf 2}.4 3.1{lf 2}.4 10.1{lht lf 3}.4
```

Render exited 0 with no lexer/parser/semantic diagnostics. The eight emitted notes
carried exactly the expected properties:

| Probe note | Token(s) | GPIF result |
|---|---|---|
| `3.3{h}` → `5.3` (fret 3→5, ascending) | `h` | `HopoOrigin` on note 0, `HopoDestination` on note 1 — hammer-on |
| `5.3{h}` → `3.3` (fret 5→3, descending) | `h` | `HopoOrigin` / `HopoDestination` — pull-off, **same encoding** |
| `7.2{lht}` | `lht` | `LeftHandTapped` |
| `5.1{tt rf 2}` | `tt` + `rf 2` | Note `Tapped` **and** `RightFingering>I` (index) |
| `3.1{lf 2}` | `lf 2` | `LeftFingering>I` (index) |
| `10.1{lht lf 3}` | `lht` + `lf 3` | `LeftHandTapped` **and** `LeftFingering>M` (middle) |

`RightFingering` and `LeftFingering` are **separate** GPIF elements, so per-hand
fingering is fully and independently expressible — a right-hand `finger=1` and a
left-hand `finger=1` produce distinct output, which is the concern spec §4/§8
raised.

**Step 2 — cross-check the parser source.** Reading the effect switches in the
vendored dist confirmed the tokens above are the accepted keywords (not merely
tolerated), and that `tt` is a beat-level marker. Because the note-effect switch
falls through unrecognized markers to `applyBeatProperty`, `tt` is accepted
**inside** a note's `{…}` brace and applies to that note's beat — so the emitter
can keep emitting all effects in the one note-effect brace it already builds.

## Notes the emitter task (D1) must carry

- **Hammer-on and pull-off share one token, `h`, placed on the _origin_ note.**
  There is no separate pull-off token; alphaTab infers hammer-vs-pull direction
  and the destination automatically from the following note's pitch. This matches
  the spec's derived-legato model (§6: first note of a same-string run is
  attacked, the rest are `SLURRED`) — the emitter marks the run's first sustained
  note `h` and must guarantee a following note exists on that string. Emitting `h`
  on the destination, or on a run's last note, would strand the marker.
- **Fingering is 1–5, thumb-first; melete fingers are 1–4, index-first.** The
  parser maps `1=thumb, 2=index, 3=middle, 4=annular/ring, 5=little`. The emitter
  already offsets left-hand fingering by one (`lf {note.finger + 1}`, turning
  melete's index=1 into alphaTab's index=2); the **same `+1` offset applies to
  `rf`**. GPIF serializes the finger as a letter (`P I M A C`).
- **`tt` taps the whole beat, not one note of a chord.** Tap is a beat property in
  alphaTab's model, so it cannot tap a single note of a multi-note beat
  independently. The tapped journey is one note per beat (§6), so this is a
  non-issue here; it is only a constraint a future chorded-tap feature would meet.
- **Detection for the §10 end-to-end test.** The success-criterion grep is
  `Tapped` in `Content/score.gpif`; the probe confirms a `tt`-tapped note produces
  exactly that property.

## Reproduction

In-container, from the repo root (`vrg-container-run` does **not** forward host
stdin — no `-i` — so the redirect must run _inside_ the container against the
mounted worktree, not as a host-side `… < probe.alphatex`):

```bash
vrg-container-run -- bash -c 'node melete-render/render.js < probe.alphatex > probe.gp'
unzip -p probe.gp Content/score.gpif | grep -oE 'Tapped|LeftHandTapped|Hopo(Origin|Destination)|(Left|Right)Fingering'
```
