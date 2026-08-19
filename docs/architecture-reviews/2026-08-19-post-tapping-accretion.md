# Architecture Report — melete

**Date:** 2026-08-19
**Commit:** `af54d4c64fa981bea508cf55bfd11aa2c4632194`
**Languages:** Python 3.14 (zero runtime dependencies), JavaScript/Node (vendored `melete-render`, one pinned dependency)
**Key directories:** `src/melete/`, `src/melete/families/`, `src/melete/alphatab/`, `tests/`, `melete-render/`, `docs/`
**Scope:** Full repository, with forward-looking assessment against epic [`mnemosys-project/.github#87`](https://github.com/mnemosys-project/.github/issues/87) (Graded exercise ladders)

> Produced by `/paad:agentic-architecture` (paad v1.24.1): five specialist agents in
> parallel, then a verifier that settled findings by executing against CPython 3.14.
> No repository file was created, modified or deleted during the analysis. Landed
> under [`melete#239`](https://github.com/mnemosys-project/melete/issues/239).

---

## Repo Overview

Melete is a command-line tool that generates daily bass-guitar practice sheets. It reads a
`config.toml` describing an instrument and pools of exercise parameters, selects a small set of
parameterized exercises with deliberate variety, and renders them into one Guitar Pro `.gp` per day
containing both standard notation and tablature.

The pipeline runs left to right: `config` loads and validates → `selection` draws a recency-weighted
specification and gates it for validity → a *family* (`scales`, `arpeggios`, `intervals`,
`chromatic`) realizes a `Score` plus `LayoutHints` → the layout fitter derives a meter and
subdivision under which the notes tile into whole bars → `derive_legato` re-derives two-hand
articulation → `rhythm.restamp` stamps durations, tuplets and accents → `alphatab/emit` produces
alphaTex → `alphatab/render` drives the vendored Node tool to write the `.gp`. `session` records the
draw so `melete replay` can reproduce it.

**Size:** 24 source modules, 8,768 lines in `src/melete/` (of which a large fraction is docstring —
see the calibration note below). 33 test modules, 12,627 lines. 2,472 tests running in 3.83s at 100%
line and branch coverage with zero skips.

**Development velocity context.** 68 commits landed in the seven days preceding this review. Epic
#67 (two-hand tapping) touched 11 of 24 source modules (+1,627/−96). This review was commissioned
specifically to assess whether that accretion is collectively coherent, and whether epic #87 can be
built on top of it.

**A calibration note on size.** Raw line counts materially overstate this codebase. `arpeggios.py`,
the largest module at 788 lines, is 126 blank + 73 comment + 353 docstring + **236 lines of code**.
The god-object hypothesis was explicitly tested against it and rejected. Wherever this report cites
a module as problematic, the reason is structural, never volumetric.

---

## Strengths

### [S-01] The renderer boundary is real, not aspirational
- **Category:** S1 — Clear modular boundaries
- **Impact:** High
- **Explanation:** The boundary `CLAUDE.md` and `design.md` declare is enforced by the actual import graph, not by convention. `emit.py` knows nothing of families, axes or config; no family imports `alphatab`, `config` or `selection`.
- **Evidence:** `src/melete/alphatab/emit.py:94-95`, the module's entire internal import surface: `from melete import theory` / `from melete.score import Attack, Hand, Measure, Note, Tuplet, bar`. `grep -rn "import config|import selection|alphatab" src/melete/families/` → zero hits. `src/melete/alphatab/render.py` imports nothing internal.
- **Found by:** Structure & Boundaries, Coupling & Dependencies

### [S-02] Acyclic layering with a genuinely stable leaf core
- **Category:** S3 — Loose coupling / S4 — Dependency direction is stable
- **Impact:** High
- **Explanation:** No family imports another. `theory` and `instrument` import nothing internal; `score` and `vocabulary` import only `theory`; `layout` imports `score` only under `TYPE_CHECKING`. The most-depended-upon modules are the least dependent — which is why `design.md`'s claim that "everything else survives" a renderer swap is credible rather than hopeful.
- **Evidence:** `src/melete/theory.py`, `src/melete/instrument.py`, `src/melete/score.py`, `src/melete/layout.py`. The only back-edge in the entire tree is `families/intervals.py:105` (see F-45).
- **Found by:** Coupling & Dependencies

### [S-03] The renderer adapter is a complete no-silent-failure contract, built securely
- **Category:** S12 — Resilience patterns / S10 — Security built-in
- **Impact:** High
- **Explanation:** Four distinct named `RenderError` paths including the one most tools miss — exit 0 with zero bytes on stdout. Built as a list-argument `subprocess.run` with no shell, an absolute `node` path from `shutil.which`, and stdout captured as bytes so a text decode cannot corrupt the `.gp` ZIP.
- **Evidence:** `src/melete/alphatab/render.py:105-184` — raises at `:119` (`_failed`), `:123` (`_no_output`), `:132` (`MISSING_NODE`), `:139` (`_missing_render_js`). The single `# noqa: S603` at `:111` carries a five-line written justification. `_no_output`'s comment: "A tool that reports success while producing nothing is exactly the silent failure this guards against." Failure messages embed a literal reproduction command and the `.atex` is deliberately left on disk.
- **Found by:** Integration & Data, Error Handling & Observability, Security & Code Quality

### [S-04] Test suite: fast, complete, invariant-based, nothing skipped
- **Category:** S11 — Testability & coverage
- **Impact:** High
- **Explanation:** 2,472 tests in 3.83s with zero skips at 100% line *and* branch coverage. The design is invariant-based rather than example-based, includes a genuine combinatorial sweep with an explicit vacuity guard, and uses a real executable on `PATH` rather than mocking `subprocess.run`.
- **Evidence:** `junit.xml` (`errors="0" failures="0" skipped="0" tests="2472" time="3.825"`), `coverage.xml` (`lines-valid="2235" lines-covered="2235" branches-valid="592" branches-covered="592"`). `tests/families/conftest.py:49-99` — `assert_central_invariant` bounds-checks the string index *before* using it to index, so a negative index cannot satisfy the arithmetic against the wrong string. `tests/test_fit_sweep.py:36-165` guards "or the sweep is not exercising it and the 1.0 below is vacuous." `tests/alphatab/test_render.py:80-107` (`fake_node`).
- **Verification note:** artifacts are dated `Aug 18 15:55`; HEAD is `2026-08-18 15:54:59` on a clean tree. These numbers are current, not stale build residue.
- **Found by:** Security & Code Quality, Coupling & Dependencies

### [S-05] Executable drift guards bind the axis registries, one enforced at import time
- **Category:** S6 — Consistent API contracts
- **Impact:** High
- **Explanation:** Two tests assert that the config axis table matches the registry families and that each pool samples exactly the axes each family declares — derived from the family, never restated. `vocabulary._named()` raises at *import* if an identifier gains no display name, so the failure is loud and immediate rather than a blank word on a cover page.
- **Evidence:** `tests/test_config.py:823-843`, carrying the comment "This is the assertion `intervals` failed before this change — its pool omitted `root` and `scale_type`". `src/melete/vocabulary.py:54-56`: `msg = f"{axis} identifiers with no display name: {sorted(unnamed)}"; raise KeyError(msg)`.
- **Found by:** Integration & Data, Structure & Boundaries

### [S-06] No global mutable state; determinism by construction
- **Category:** S14 — Simple, pragmatic abstractions
- **Impact:** High
- **Explanation:** Every module-level container is written at import and never mutated at runtime. Randomness is an injected `random.Random` with no module-level `random.` anywhere, and `date.today()` appears exactly once in the entire source tree.
- **Evidence:** `src/melete/selection.py:351-376` (`_Slot.rng` injected). Grepping `global `, `.update(`, `.append(`, `.setdefault(` across `src/` returns only local-variable mutations. `src/melete/cli.py:264` is the sole `datetime.date.today()`.
- **Found by:** Structure & Boundaries, Coupling & Dependencies

### [S-07] Unknown-key rejection is structural, not per-key
- **Category:** S9 — Configuration discipline
- **Impact:** High
- **Explanation:** `_reject_unknown` is applied to every config section including the tap opt-in keys, and `_fail` always emits `key: problem; accepted: [...]`. No key is ever silently ignored and nothing falls back to a default for a misspelling.
- **Evidence:** `src/melete/config.py:210-228,423-446`. Verified live: adding `[output]` yields `ConfigError: config: unrecognized key(s) ['output']; accepted: ['instrument', 'pool', 'session']`.
- **Found by:** Error Handling & Observability

### [S-08] The `Family` record genuinely collapsed the drift it was built for
- **Category:** S9 — Configuration discipline
- **Impact:** High
- **Explanation:** Each family module owns exactly one `DEFAULT_TEMPO_RANGE` and one `AXES`, referenced by both its own `generate` and by `REGISTRY`; `config._pool` defaults tempo from the registry record. No second copy of either number exists anywhere. This repaired two real prior defects.
- **Evidence:** `src/melete/families/__init__.py:85-124`; `src/melete/config.py:607-612`. The docstring at `:19-25` records both prior drifts: `config.DEFAULT_TEMPO` disagreeing with three of four families, and the axis table omitting two of `intervals`' axes.
- **Found by:** Error Handling & Observability

### [S-09] The selector's weighting is reconstructable from the artifact
- **Category:** S8 — Observability present
- **Impact:** High
- **Explanation:** `WeightInputs.distances` records, per slot, every axis consulted and each candidate's recency distance, serialized into `session.json`. Of the pipeline's decision layers, the selector is the only one whose inputs survive into the artifact.
- **Evidence:** `src/melete/session.py:229-243`; `src/melete/selection.py:351-376`. `session.py:404-435` cross-checks that the count of weight-input sets equals the count of exercises.
- **Found by:** Error Handling & Observability

### [S-10] The tapping epic added a real renderer round-trip signal
- **Category:** S8 — Observability present / S11 — Testability & coverage
- **Impact:** High
- **Explanation:** Four tests render through the real alphaTab toolchain, unzip the `.gp` and assert on `Content/score.gpif`. These are the first checks in the repository of what the *renderer* did rather than what melete wrote — a materially better signal than the emitted-text assertions that passed over the Phase B octave defect.
- **Evidence:** `tests/test_tapping_end_to_end.py:167,171,236-237,281-283,350-351` — `name="Tapped"`, `name="LeftHandTapped"`, `name="HopoOrigin"`.
- **Found by:** Error Handling & Observability

### [S-11] One wiring point for the pipeline, deliberately placed below both callers
- **Category:** S1 — Clear modular boundaries
- **Impact:** High
- **Explanation:** `realize()` is the single composition of family → fitter → legato → restamp, imported by `cli._score` and `selection._rejected`. It imports neither, which is what prevents a `cli ↔ selection` cycle and stops the validity gate and the sheet from disagreeing about what an exercise is.
- **Evidence:** `src/melete/pipeline.py:49-85`; the module docstring at `:11-15` states the placement rationale explicitly.
- **Found by:** Structure & Boundaries

### [S-12] Write ordering makes `session.json`'s presence mean exactly one thing
- **Category:** S12 — Resilience patterns
- **Impact:** High
- **Explanation:** The log is written after the render, so a failed render leaves a directory that is explicitly *not* a session; a later date's history window hits it and stops loudly rather than drawing against a hole. `history(exclude=on)` drops the date being generated so a day is never weighted against its own record.
- **Evidence:** `src/melete/cli.py:288-290`; `src/melete/session.py:435,465-499`. `_recorded()` distinguishes "no directory" from "directory with no log" with different repairs.
- **Found by:** Integration & Data

### [S-13] Injection surface closed, supply chain pinned, on-disk input distrusted
- **Category:** S10 — Security built-in
- **Impact:** High
- **Explanation:** alphaTex escaping does backslash before quote — the only ordering that works. The config→alphaTex free-text surface is exactly one field wide because every other string is a closed-vocabulary identifier. `session.json` gets a full hand-written validating reader. The single Node dependency is exact-pinned with an SRI hash and zero transitive dependencies.
- **Evidence:** `src/melete/alphatab/emit.py:376-379`. Verified live: `_quoted()` turns an injected `meta\n\title "pwned"` into a neutralized `\\title \"pwned\"`. `src/melete/config.py:283-352`; `src/melete/session.py:278-441`; `melete-render/package-lock.json:14-22` (`"version": "1.8.4"`, `sha512-…`, lockfileVersion 3, MPL-2.0).
- **Found by:** Security & Code Quality

### [S-14] `MAX_ATTEMPTS` is measured twice, not guessed; constants are named and justified
- **Category:** S5 — Dependency management hygiene
- **Impact:** Medium
- **Explanation:** The retry budget carries two measured validity tables (20,000 draws per family, re-measured after the span bound landed in #57) plus explicit spurious-failure arithmetic — 46 lines of comment for one constant. This is the opposite of a magic number, and the re-measurement discipline is the model the project should reuse.
- **Evidence:** `src/melete/selection.py:129-175`. Independently re-measured during verification: a tapped-scales pool sits at **0.751** validity, comfortably above the 1-in-20 pool the constant was sized against, so the sizing survives the tapping epic.
- **Found by:** Coupling & Dependencies, Error Handling & Observability

### [S-15] `session.json` closes the JSON-tuple round-trip trap structurally
- **Category:** S12 — Resilience patterns
- **Impact:** Medium
- **Explanation:** `_axis_value` restores every JSON array to a tuple of ints rather than enumerating known tuple axes, so an axis added later cannot silently fall out of coverage accounting. `_integer` rejects `bool` and `float` rather than coercing.
- **Evidence:** `src/melete/session.py:26-42,300,325-336`. The module docstring names the exact failure mode it is closing: "It would not raise. The sheets would just get less varied."
- **Found by:** Integration & Data

### [S-16] `Parameters` disciplines the loose mapping; deferred shapes are pre-empted *and* raise
- **Category:** S6 — Consistent API contracts / S7 — Robust error handling
- **Impact:** Medium
- **Explanation:** `Parameters.value/.identifier/.integer` turn a deliberately loose `Params` mapping into named §13-shaped errors; `integer()` rejects `bool` explicitly ("`True` is not fret 1"). Deferred tap shapes get a two-layer defense: the `derive` hooks pin the axis so the selector never reaches the raise, and the raise exists anyway for hand-written specs.
- **Evidence:** `src/melete/families/_shared.py:76-141`; `src/melete/families/arpeggios.py:407-413`; `src/melete/families/scales.py:230-269`. `tests/test_selection.py:764-780` asserts the pinned axis never enters `inputs.distances`.
- **Found by:** Integration & Data, Error Handling & Observability, Security & Code Quality

### [S-17] Rules derived from data rather than tabulated per case
- **Category:** S13 — Domain modeling strength
- **Impact:** Medium
- **Explanation:** Two arithmetic lines replace a twelve-row per-quality fingering table, and several structural constants are computed from their own source of truth rather than restated. A quality respelled in `theory` respells the tap box with it.
- **Evidence:** `src/melete/families/arpeggio_tap_shapes.py:123,232` — `_root_finger` is `_LEFT_INDEX + (_FOURTH - third_interval)`. `arpeggios._is_triad` is `len(theory.CHORDS[quality]) == 3`; `chromatic.POSITION_FRETS = len(FINGERS)`; `score.TONICS = range(len(theory.PITCH_CLASSES))`.
- **Found by:** Structure & Boundaries

### [S-18] `LayoutHints`/`LayoutPlan` is a small, load-bearing abstraction
- **Category:** S14 — Simple, pragmatic abstractions
- **Impact:** Medium
- **Explanation:** Three fields in, five out. It absorbed the entire retirement of the sampled `subdivision` and `time_signature` axes (#118/#119) without any family learning what a meter is.
- **Evidence:** `src/melete/layout.py:28-45,68-82,116-131`. `_quality` and `_candidates` are ~10 lines each; the whole ranking policy is two comparable tuples.
- **Found by:** Structure & Boundaries

### [S-19] R-rule identifiers cited at the point of decision
- **Category:** S8 — Observability present
- **Impact:** Medium
- **Explanation:** Fingering and articulation decisions carry inline corpus-rule citations on the predicates themselves, not only in prose, and are traceable to `docs/reports/tapping-fingering-rules.md` in both directions for R2–R5, R7, R9–R12.
- **Evidence:** `src/melete/families/_shared.py:455-470` — `# R12: a slur needs a genuine hammer-on/pull-off …` and `# R9/R10: the descending scale group's cross-hand pull-off …` sit directly above the boolean expressions they explain.
- **Found by:** Error Handling & Observability

### [S-20] One acceptance golden pins config → select → realize → emit byte-for-byte
- **Category:** S6 — Consistent API contracts
- **Impact:** Medium
- **Explanation:** `_draw()` reproduces the real seed derivation and selection for a frozen day and asserts byte-identical alphaTex, plus repeat-bracket and whole-bar-meter structural properties. This is the strongest determinism guarantee the project has.
- **Evidence:** `tests/alphatab/test_practice_goldens.py:1-116`.
- **Caveat (verified):** it pins a *regeneration* with empty history, not a replay from a recorded `session.json`, and not the recency path. Its content gap is F-11.
- **Found by:** Integration & Data

### [S-21] The agent guard fails closed
- **Category:** S10 — Security built-in
- **Impact:** Medium
- **Explanation:** When `vrg-hook-guard` is absent the shim does not fall open — it hard-denies raw `git`/`gh` with an explanatory reason. Least privilege applied to the agent tooling itself, with the failure direction chosen correctly.
- **Evidence:** `.claude/hooks/guard.sh:8-30`.
- **Found by:** Security & Code Quality

### [S-22] `theory.py` and `instrument.py` are pure, stateless, and untouched by the epic
- **Category:** S2 — High cohesion
- **Impact:** Medium
- **Explanation:** Frozen data tables plus pure functions. Neither module was modified by the entire tapping epic, which is the practical test of whether a leaf is genuinely stable — and the strongest available evidence that the spelling and fretboard models are correctly factored out of the churn.
- **Evidence:** `src/melete/theory.py`, `src/melete/instrument.py`. `vrg-git diff --stat fc3cb00^..ce23501 -- src/` shows no change to either.
- **Found by:** Structure & Boundaries

---

## Flaws/Risks

### [F-01] Two-hand tapped triads compose into 2/4 × 7 bars — the fitter's declared last resort, with no lever to escape and no signal
- **Category:** 27 — Temporal coupling (+ 6 leaky abstractions, 21 no observability plan)
- **Impact:** High
- **Explanation:** The family declares `levers=()` on the tapped path and `apex_doubled` accepts "2/4 x L at worst" as the price of an even note count; the fitter's `_quality` ladder — rebuilt in #174/#178 specifically to demote 2/4 to a strict last resort — is handed a single candidate and has nothing to rank. Two individually-correct layers produce exactly the outcome the fitter was rebuilt to prevent.
- **Evidence:** `src/melete/families/arpeggios.py:783-785`: `hints = layout_hints(cell=1, seam=len(ascending) - 1, levers=())`. `src/melete/families/_shared.py:343-347`: "makes the count even, which always tiles into whole bars (2/4 x L at worst) with no note-count lever". `src/melete/layout.py:145-147` still asserts "Every family declares a lever, so every family always tiles" — no longer true.
- **Executed:** `pipeline.realize(PROFILES["bass6"], "arpeggios", {root:33, quality:"maj", inversion:"root", pattern:"straight", hands:2, …})` → `plan.trace == "14 notes / cell 1 = 14 beats; chose 2/4 x 7 (subdivision quarter); candidates [(2, 7)]; levers []"`. The single-candidate list is the decisive detail.
- **Reachability (verified end-to-end):** triads tap **unconditionally** — `arpeggios.derive:266` is `if _is_triad(drawn) or drawn in tapped_qualities`, so no config opt-in is required. A minimal legal config (`bass6`, `qualities = ["maj","min"]`, `patterns = ["straight"]`) through `config.load_string` → `selection.select` → `pipeline.realize` produced 2/4 × 7 for **every** exercise. Fires on `bass5` and `bass6` × {maj, min, dim, aug} × `straight` — 77 root/quality combinations swept. `bass4` is unaffected (8 notes → 4/4 × 2). `examples/config.toml` escapes only because its arpeggio pool contains no triad.
- **Compounding:** the trace names the problem exactly and is then discarded (F-15).
- **Found by:** Error Handling & Observability (traced), Coupling & Dependencies (corroborating rationale)

### [F-02] `config_hash` omits both tapping opt-in keys, breaking the seed⇔configuration contract
- **Category:** 19 — Lack of idempotency
- **Impact:** High
- **Explanation:** `_fingerprint`'s pool block emits only `tempo` and `values`; `FamilyPool.tapped_qualities` and `.tapped_scale_types` are absent despite demonstrably moving the draw. Two configurations that select entirely different exercises hash identically and derive the identical seed, so `cli._replay`'s `_CONFIG_MOVED` guard never fires.
- **Evidence:** `src/melete/session.py:157-166`. The docstring at `:132-134` claims "Everything in the configuration is here, because everything in it moves the draw" — now false.
- **Executed:** two `Config`s differing only in `tapped_qualities` both hash to `875ca273884b6c12254225cf597a06613a52e236002f8ff88156a97a85a38b06` and both derive seed `11598973406956100199`. Drawn against that shared seed they produce completely different sessions — `{root:33, maj7, hands:1}` + `{root:34, ionian, positional, hands:1}` versus `{root:23, maj7, hands:2}` + `{root:27, dorian, three_note_per_string, hands:2}`.
- **History:** `session.py` last changed `3e64da0` (2026-08-12); `tapped_qualities` landed `3b2252f` (#213) and `tapped_scale_types` `dcbfbcc` (#217), both after. `grep tapped tests/test_session.py` → empty. An omission, not a decision.
- **Found by:** Integration & Data, Structure & Boundaries

### [F-03] The same config file is valid or invalid depending on the day's seed
- **Category:** 22 — Configuration sprawl
- **Impact:** High
- **Explanation:** `_pool_values` includes an axis only `if axis.key in section`, so `config.load` accepts a `[pool.<family>]` section omitting an axis the family reads. The missing axis surfaces as a `SelectionError` only on a draw that happens to reach it, and reachability depends on three facts held in three different modules.
- **Evidence:** `src/melete/config.py:449-459`; `src/melete/selection.py:193-195,379-399`.
- **Executed:** a `[pool.intervals]` with `contexts = "all"` and no `scale_types` loads cleanly (pool axes `['context','interval','pattern','root','string_skip']`), then across 40 seeds **11 succeeded and 29 raised** `SelectionError: [pool.intervals] configures no candidate values for the 'scale_type' axis`.
- **Found by:** Error Handling & Observability

### [F-04] A genuine defect is retried 500 times, then reported to the user as an over-constrained pool
- **Category:** 34 — Inconsistent error conventions (+ 20 weak error handling strategy)
- **Impact:** High
- **Explanation:** `_rejected` catches bare `ValueError` from the whole of `pipeline.realize`, but `ValueError` is exactly what every defect path raises — and `ConfigError`, `SelectionError` and `SessionError` all subclass it, so no type carries the distinction the design assumes exists. Each real bug is counted into `reasons`, resampled up to 500 times, and then framed as user error.
- **Evidence:** `src/melete/selection.py:486-489`. The docstring at `:483-484` asserts "Anything else from a family is a bug in the family (§13) and resampling around it would hide it" — but the family's own bug paths raise `ValueError` too (`_shared.py:98-103,113-116,139`; `score.py:292-315`; `layout.py:41-45`). `selection.py:524-526` then advises: "Widen one of the axes that message names, or drop {family} from [session] shape".
- **Executed:** `ConfigError.__mro__[1] == ValueError`, likewise `SelectionError` and `SessionError`.
- **Found by:** Error Handling & Observability

### [F-05] `--force` deletes a completed session before a render that can fail
- **Category:** 26 — Poor transactional boundaries
- **Impact:** High
- **Explanation:** `shutil.rmtree(target)` runs before `_score` and before `_engrave`, which shells out to Node. A `RenderError` propagates, `session.write` never runs, and the previous day's `session.json` and `practice.gp` are already deleted and unrecoverable. The guarantee the code and docs state is scoped only to a failing *draw*.
- **Evidence:** `src/melete/cli.py:283-290`:
  ```python
  if target.exists():
      shutil.rmtree(target)
  scores = [_score(active, spec) for spec, _inputs in picks]
  _engrave(target, active, scores, on, split=args.split)
  session.write(root, session.record(on, active, picks, seed), force=True)
  ```
  Contradicted by `cli.py:44-45` and `docs/cli.md:159-160`, both: "The removal happens after the draw succeeds, so a configuration that no longer selects cannot destroy the record of the day it was going to replace." Damage compounds via `cli.py:33-36` — the emptied directory then reads as a corrupt history entry for every later date. `tests/test_cli_generate.py:430,454,466` have force tests; none combines `--force` with a failing renderer.
- **Found by:** Integration & Data

### [F-06] `hands` is a live, recorded, coverage-counted axis present in no registry
- **Category:** 17 — No clear ownership of data (+ 9 shotgun surgery)
- **Impact:** High
- **Explanation:** The `derive` hook can mint axes the registry machinery cannot see. `hands` travels in `params`, is written to `session.json`, is counted by `_uses`, and is printed by `cli._preview` — yet appears in no `Family.axes`, no `vocabulary.AXES` and no `config._AXES_BY_FAMILY`. Two families declare it independently with byte-identical duplicated validation.
- **Evidence:** `src/melete/families/arpeggios.py:221-223` and `scales.py:184-186` each declare `HANDS = "hands"`, `_ONE_HAND = 1`, `_TWO_HANDS = 2` verbatim, and each reimplements a message `_shared.Parameters.integer` already provides:
  ```
  _shared.py:122   msg = f"{self.family}: {axis} must be an integer, got {value!r}"
  arpeggios.py:642 msg = f"{_FAMILY}: {HANDS} must be an integer, got {value!r}"
  scales.py:224    msg = f"{_FAMILY}: {HANDS} must be an integer, got {value!r}"
  ```
  They cannot reuse it because `Parameters` validates against `self.axes`.
- **Executed:** `"hands" in REGISTRY["arpeggios"].axes` → `False`; `"hands" in vocabulary.AXES` → `False`; `cli._named("hands", 2)` → bare `2`. As drawn, params order is `[root, quality, inversion, pattern, hands, accent_pattern, note_value_pattern]`; `cli.ordered` returns `[root, quality, inversion, pattern, accent_pattern, note_value_pattern, hands]`.
- **Sharpest consequence:** that reordering is precisely the failure `cli.ordered`'s own docstring exists to prevent — `cli.py:466-469`: "without this a replayed sheet lists each exercise's axes in a different order than the sheet it reproduces — the one visible difference between the two, in the one place a reader compares them." For any tapped exercise, `melete show` does exactly that today. Separately `cli._unenumerated` (`cli.py:689-691`) derives from `family.axes ∪ rhythm.AXES`, so `melete vocabulary` cannot mention `hands` — and `_vocabulary`'s docstring is explicit that this is the failure it is trying to prevent. The drift guard carries an explicit carve-out at `tests/test_selection.py:308`: `assert set(spec.params) - expected <= {"hands"}`.
- **Found by:** Structure & Boundaries, Coupling & Dependencies, Integration & Data, Error Handling & Observability

### [F-07] Reference docs describe a CLI flag and a config section the code hard-rejects, and explicitly promise the opposite
- **Category:** 24 — Inconsistent API contracts
- **Impact:** Medium
- **Explanation:** `--staves` and the whole `[output]` section are documented across two reference pages; the parser exits 2 on the flag and the loader raises `ConfigError` on the section. `docs/configuration.md` then states the reassurance that is precisely false.
- **Executed:** `cli.main(["generate","--staves","tab"])` → `usage: … melete: error: unrecognized arguments: --staves tab`, `SystemExit code: 2`. `config.load_string(examples_config + '[output]\nstaves = "tab"\n')` → `ConfigError: config: unrecognized key(s) ['output']; accepted: ['instrument', 'pool', 'session']`.
- **Evidence:** Documented at `docs/cli.md:50,69,125-137,270,375` and `docs/configuration.md:21,104-125,420-425`. `docs/configuration.md:423-424`: "Both are still validated, so an existing `config.toml` keeps loading; they simply no longer change the output." A `config.toml` with `[output]` does not load at all. Removed at `3e64da0` (#107, 2026-08-12); docs swept three times since (`87fda5f`, `18fbdc1`, `ab0a892`) and the section survived every pass. Adjacent: `cli.py:12` says "`generate` takes seven flags (§11)" while `_generate_flags`' docstring at `:209` says six — there are six.
- **Found by:** Integration & Data, Error Handling & Observability

### [F-08] `layout._try` swallows four distinct `ValueError`s and `fit` then gives unachievable advice
- **Category:** 20 — Weak error handling strategy (+ 34)
- **Impact:** Medium
- **Explanation:** `_fit_fixed` raises four structurally different errors, one of which is a genuine family defect (a `cell` outside 1–6). All four collapse to `None`, and `fit` reports a single generic message advising a new lever — which cannot fix a bad cell. A direct violation of the project's stated "no swallowed exceptions" rule, and the swallowed text is the diagnostic.
- **Evidence:** `src/melete/layout.py:115-119`:
  ```python
  def _try(note_count, hints, applied) -> LayoutPlan | None:
      try:
          return _fit_fixed(note_count, hints, applied)
      except ValueError:
          return None
  ```
  `LayoutHints.__post_init__` (`layout.py:41-45`) validates only `cell >= 1`; the upper bound of 6 lives implicitly in `_SUBDIVISION_FOR_CELL`.
- **Executed:** `LayoutHints(cell=7, …)` constructs without complaint; `layout.fit(28, h)` reports "the pattern needs a new lever declared by its family" while `_fit_fixed` was actually saying "cell 7 has no subdivision mapping; expected 1-6".
- **Found by:** Error Handling & Observability

### [F-09] Two rhythm axes get silent defaults; a misspelled one escapes as a bare `KeyError` traceback
- **Category:** 34 — Inconsistent error conventions (+ 24)
- **Impact:** Medium
- **Explanation:** `params.get(..., "straight")` / `params.get(..., "none")` silently default two axes that every family axis treats as a loud error. A *present-but-misspelled* value is worse: it reaches `rhythm.restamp`'s bare dict index and raises `KeyError`, which is not in `cli._HANDLED` and is not caught by `selection._rejected` (which catches only `ValueError`), so it crashes a draw rather than being rejected.
- **Evidence:** `src/melete/pipeline.py:77-79`. `cli._HANDLED` (`cli.py:124-130`) lists `CliError, ConfigError, SelectionError, SessionError, RenderError` — `KeyError` absent.
- **Executed:** a spec with `accent_pattern="evry_3"` → `KeyError: 'evry_3'` from `rhythm.py:172`; a spec omitting both rhythm axes realizes 16 notes silently, and the defaults used are not recorded anywhere.
- **Found by:** Integration & Data

### [F-10] Identifier lookup in `rhythm` is a bare dict index where every family routes through a named error
- **Category:** 34 — Inconsistent error conventions
- **Impact:** Medium
- **Explanation:** `rhythm` indexes `SUBDIVISIONS`, `NOTE_VALUE_PATTERNS` and `ACCENTS` directly, producing a bare `KeyError`; families route the identical operation through `Parameters.identifier`, which raises a `ValueError` naming family, axis and accepted set. Same pattern at `pipeline`'s `REGISTRY[family]` and `_sample`'s `config.pool[family]`.
- **Evidence:** `src/melete/rhythm.py:164,172,174`; contrast `src/melete/families/_shared.py:105-116`.
- **Found by:** Error Handling & Observability

### [F-11] The frozen acceptance day contains zero tapped notes; no golden exercises the tapping epic
- **Category:** 32 — Missing or inadequate test coverage for critical paths
- **Impact:** Medium
- **Explanation:** `examples/config.toml`'s arpeggio pool lists five sevenths plus `min6` — no triad — and declares neither tapping opt-in key, so the acceptance day the whole pipeline is pinned against contains no tapping at all. A week of work spanning 11 of 24 modules is invisible to the byte-for-byte oracle.
- **Evidence:** `examples/config.toml:31` `qualities = ["maj7", "min7", "dom7", "m7b5", "min6"]`, with no tap opt-in key in the file. Verified: `grep -c 'tt\|lht'` returns **0** on all nine golden `.atex` files (`golden/book.atex`, `exercise.atex`, `repeat.atex`, and all six under `practice-2026-08-13/`), where `tt`/`lht` are the tap markers defined at `src/melete/alphatab/emit.py:146-147`. `tests/alphatab/test_practice_goldens.py:4` confirms the day is drawn from `examples/config.toml`.
- **Verifier correction:** the specialist framing "the only independent oracle declines to check content" was **overstated and downgraded**. `tests/test_tapping_end_to_end.py` does assert real `.gp` content at eight sites (see S-10). The accurate residual gap is narrower: no test decodes an emitted `<fret>.<string>` beat token back and cross-checks it against the `Score`'s notes across a corpus (`test_alphatex_emit.py:205,261` do this by hand for a single note), and the acceptance goldens themselves are tapping-free.
- **Found by:** Error Handling & Observability, Security & Code Quality

### [F-12] The "family" concept is three parallel hand-written lists, and the module docstring claims the opposite
- **Category:** 3 — Tight coupling
- **Impact:** Medium
- **Explanation:** `families/__init__.py` claims no other module keeps a private family list and that a fifth family costs "nothing anywhere else". Both are false: `vocabulary.AXES["family"]` and `config._AXES_BY_FAMILY` are two more hand-written lists, and `config._pool` indexes the latter with a bare subscript, so a family added to `REGISTRY` alone raises `KeyError` at config load.
- **Evidence:** `src/melete/families/__init__.py:11-14` ("without any of the three keeping a private list of families that could drift from this one") and `:28-30`. Contradicted by `src/melete/vocabulary.py:110-117` and `src/melete/config.py:383-410`; `config.py:597` is `axes = _AXES_BY_FAMILY[family]`. Root cause is direction: `families → vocabulary`, so `vocabulary` cannot read the registry. `tests/test_config.py:823,840-843` exist precisely to catch the drift the docstring calls impossible.
- **Found by:** Coupling & Dependencies

### [F-13] The order of each family's `AXES` tuple is an unguarded cross-module contract
- **Category:** 27 — Temporal coupling
- **Impact:** Medium
- **Explanation:** `_sample` iterates `REGISTRY[family].axes` and both consults `_CONDITIONAL_AXES` and calls `derive` before each draw, so the tuple order is load-bearing in two independent ways — yet `AXES` is documented as presentation order and the only test relating it to the config table compares *sets*.
- **Evidence:** `src/melete/selection.py:431-440`. `params[switch[0]]` at `:433` is a bare subscript: were `intervals.AXES` to list `scale_type` before `context`, that is a bare `KeyError` rather than a §13 message. The `derive` path fails *silently* instead — the coupled axis is drawn from the pool, consuming a draw and writing a spurious `slot.distances` entry, before `params.update(derive(...))` at `:440` overwrites it. `families/__init__.py:91` documents `AXES` as "in the order §7's table lists them"; `tests/test_config.py:842-843` asserts on **sets**. `cli.ordered` (`cli.py:486-488`) independently re-derives the same order.
- **Found by:** Coupling & Dependencies, Structure & Boundaries

### [F-14] Three of `realize`'s four stage adjacencies fail silently if reordered
- **Category:** 27 — Temporal coupling
- **Impact:** Medium
- **Explanation:** The four stages are correct only in one order, and none of the three constraints is enforced by type, assertion or test — only by `realize` being the single call site.
- **Evidence:** `src/melete/pipeline.py:70-78`. (a) `layout.realize_lever` slices the voice by raw `hints.seam`/`hints.cell` indices, so legato must run after or a repeated/dropped note keeps a stale attack. (b) `rhythm.py:179-180` is `accent=accent and note.attack is not Attack.SLURRED` — the `SLURRED` values it tests are *created* by `derive_legato`, so restamping first would stamp accents on notes that later become slurs, with no error. (c) `derive_legato` requires a flat `Note` run; its docstring (`_shared.py:448-450`) concedes "a `Tuplet`, were one present, passes through untouched and ends the current run".
- **Verified:** `rhythm.py:247` is the *only* site in `src/` that constructs a `Tuplet`, so constraint (c) is real and today unviolated.
- **Found by:** Coupling & Dependencies

### [F-15] The only decision trace is written to a field nothing reads, and its docstring justification is false
- **Category:** 21 — No observability plan (+ 17)
- **Impact:** Medium
- **Explanation:** `pipeline.realize` computes the fitter's full account of *why* a meter won and writes it into `Score.params["layout_trace"]`. Nothing in `src/` ever reads `Score.params`. `score.py`'s stated justification for the field's existence is untrue.
- **Evidence:** `grep -rn "layout_trace" src/ tests/` returns exactly one write (`src/melete/pipeline.py:84`) and one read, in `tests/test_pipeline.py:120`. `grep -rn "\.params" src/melete/alphatab/` → zero hits. `session.record` (`session.py:224`) builds from `ExerciseSpec.params`, a different dictionary. `score.py:247` nonetheless claims "`params` travels inside the Score deliberately: the session log receives the exact parameter dictionary that produced the exercise."
- **Compounding:** this is what makes F-01 silent. The trace `"14 notes / cell 1 = 14 beats; chose 2/4 x 7 …; candidates [(2, 7)]; levers []"` names that defect exactly, and is thrown away.
- **Found by:** Structure & Boundaries, Integration & Data, Error Handling & Observability

### [F-16] Back-filling a past date weights it against sessions that came after it
- **Category:** 19 — Lack of idempotency
- **Impact:** Medium
- **Explanation:** `history` excludes only the exact target date and never filters to dates *before* the one being generated, then takes the newest `count` by date. `_distances` assigns distance 1 to the chronologically newest session in the whole log — so `melete generate --date 2026-01-05` run today treats an August session as "one session ago". The docs promote exactly this workflow.
- **Evidence:** `src/melete/session.py:486-488`: `dated = sorted(pair for pair in every if pair[0] != exclude)` then `for on, entry in dated[-count:]`. `src/melete/selection.py:338`. `docs/cli.md:86-87`: "generating a past date is how a missed day is filled in." `tests/test_session.py:368-435` covers window size, ordering and corruption — no test places a session *after* the date being generated.
- **Adjacent:** `docs/cli.md:95-97` says the derived seed means "a re-run of the same date against the same configuration draws the same session" — true only when the surrounding log is unchanged.
- **Found by:** Integration & Data

### [F-17] The tap opt-in surface bypasses the `Family` facade, with two adjacent config keys validated against two different kinds of source of truth
- **Category:** 13 — Inconsistent boundaries (+ 4 high/unstable dependencies, 23 DI misuse)
- **Impact:** Medium
- **Explanation:** `config` imports a family-internal constant directly, hardcodes two family-name literals, and branches on family name — the exact per-family knowledge the `Family` record was introduced to eliminate. `FamilyPool.tapped_values` then re-unions two semantically different identifier sets into one untyped `frozenset[str]` whose meaning is decided by the callee's identity.
- **Evidence:** `src/melete/config.py:42` `from melete.families.arpeggio_tap_shapes import SEVENTH_QUALITIES`; `:89` `_TAPPED_FAMILY = "arpeggios"`, `:97` `_TAPPED_SCALES_FAMILY = "scales"`; `:603-605` `if family == _TAPPED_FAMILY: … elif family == _TAPPED_SCALES_FAMILY:`. `_tapped_scale_types` (`:667`) validates against `vocabulary.accepted("scale_type")` — the shared registry — while `_tapped_qualities` (`:657`) validates against a family-internal tuple. `FamilyPool.tapped_values` at `:178-186`.
- **Found by:** Structure & Boundaries, Coupling & Dependencies, Integration & Data

### [F-18] The reach gate's open-string exclusion is a plucking-hand assumption applied to two-hand tapping
- **Category:** 12 — Hidden side effects
- **Impact:** Medium
- **Explanation:** `hand_span` filters out fret 0 on the stated rationale that "Fret 0 is sounded by the plucking hand while the fretting hand stays where it is." In `_two_hand_box` there is no plucking hand — a fret-0 note is `attack=TAPPED`, tapped by the very hand whose span is being measured — so the gate systematically under-measures the reach.
- **Evidence:** `src/melete/instrument.py:172-179` (the rationale) and `:180` `fretted = [fret for fret in frets if fret > 0]`; applied from `src/melete/families/_shared.py:307-318` and again in `selection._rejected`'s `max_fret_span` check (`selection.py:499`).
- **Executed:** `bass6` two-hand `min` triad at root 25 yields a LEFT hand holding frets `{0, 2, 4}` — every note `attack=TAPPED, hand=LEFT` — measured as span **2** where the true reach is **4**. At the default `position_span=4` no case in the swept space crosses the limit, so it is latent today; at `position_span` 2 or 3 (both legal — `config.py:482` only calls `_positive`) it admits a physically unplayable box.
- **Found by:** Error Handling & Observability

### [F-19] `score.py` holds a renderer-motivated barring pass and a deliberately duplicated table, despite "pure data"
- **Category:** 13 — Inconsistent boundaries (+ 6 leaky abstractions)
- **Impact:** Medium
- **Explanation:** `score.py` declares itself pure data with "no rendering logic whatsoever", but carries ~90 code lines of barring justified by a renderer property, plus a constant duplicated across the blast door from the emitter with no test tying the two together.
- **Evidence:** `src/melete/score.py:5-6` "Everything here is pure data … no rendering logic whatsoever"; `docs/design.md:64` "Pure data." Yet `score.py:47-49` justifies the pass with "the alphaTab renderer does not auto-bar", and `bar()` at `:468` (+`_split_writable:399`, `_plan_pieces:445`) implements it — its only production caller is `alphatab/emit.py:623`. `score._WRITABLE_AUGMENTATIONS` (`:392`) and `emit._AUGMENTATIONS` (`:226`) are acknowledged duplicates ("a future DRY pass could fold the two into a single shared constant"). Verified: `grep -rn "_WRITABLE_AUGMENTATIONS\|_AUGMENTATIONS" tests/` → zero hits.
- **Found by:** Structure & Boundaries, Coupling & Dependencies

### [F-20] Two-dimensional dispatch in arpeggios held together by a comment
- **Category:** 11 — Low cohesion
- **Impact:** Medium
- **Explanation:** Two orthogonal predicates (`hands ∈ {1,2}` × triad/seventh) produce three live journeys, re-tested in four places. The invariant that a two-hand triad never reaches `_ascending_notes` is documented only by an inline comment; violate it and the triad is routed to the seventh box and rejected with an error naming the wrong shape.
- **Evidence:** `src/melete/families/arpeggios.py:588`: `if hands == _TWO_HANDS:  # a two-hand triad never reaches here (see _journey_notes)`. The invariant is actually held at `_journey_notes:621`. The predicate is computed at `:266`, `:588`, `:621` and `:708`.
- **Executed (without editing):** calling `_ascending_notes(bass6, 33, "maj", "root", 2)` directly yields "arpeggios: the two-hand tap box for R11 is a seventh-chord shape, but 'maj' is not a seventh quality. Accepted sevenths: ['maj7', 'min7', 'dom7', 'm7b5', 'dim7']" — for a triad that has a perfectly good triad box.
- **Found by:** Structure & Boundaries

### [F-21] The only third-party code melete executes is the code the audit gate does not scan
- **Category:** 30 — Security as an afterthought
- **Impact:** Medium
- **Explanation:** `pyproject.toml` declares `dependencies = []`, so the audit stage's Python-only tooling scans nothing but the dev toolchain, while the actual runtime third-party code — `@coderline/alphatab`, MPL-2.0 — is never reached by `npm audit` or by any license check.
- **Evidence:** `.vergil/vrg-validate-20260818-195510.log:132-143` — the audit stage runs exactly `uv sync --check --frozen --group dev`, `uv lock --check`, `pip-audit`, `pip-licenses`. The `pip-licenses --allow-only=…` list at `:141` includes "Mozilla Public License 2.0 (MPL 2.0)" but is never applied to the Node tree. CI's `security / trivy` job may cover the lockfile for vulnerabilities, but Trivy does not enforce license policy by default.
- **Found by:** Security & Code Quality

### [F-22] The alphaTab version is declared in five places, installed by a mechanism that reads only one
- **Category:** 31 — Dead code / unused dependencies (configuration drift)
- **Impact:** Medium
- **Explanation:** `vergil.toml`'s `build-command` is what the container actually installs (globally, on `NODE_PATH`); `melete-render/package.json` and `package-lock.json` declare the same version but are never `npm install`ed in CI — `build-cache-files` only hashes the lockfile for cache invalidation. A bump to one and not the other is invisible.
- **Evidence:** `vergil.toml:40` `build-command = "npm install -g @coderline/alphatab@1.8.4"`, `:41` `build-cache-files = ["melete-render/package-lock.json"]`; `melete-render/package.json:8`; `melete-render/package-lock.json:11,15`; `docs/repository-standards.md:190`. Four "spike-confirmed against 1.8.4" comments (`emit.py:19,121,130,164`) would silently describe a different version. No test references any of these files.
- **Found by:** Security & Code Quality

### [F-23] The documented Getting Started install produces a CLI that cannot render
- **Category:** 32 — Missing or inadequate test coverage for critical paths
- **Impact:** Medium
- **Explanation:** `RENDER_JS` walks up from the module's own file to a repo root that exists only in a source checkout, and `melete-render/` is not packaged at all — yet the README documents `uv tool install .` followed by `melete generate`.
- **Evidence:** `src/melete/alphatab/render.py:49` `RENDER_JS = Path(__file__).parents[3] / "melete-render" / "render.js"` (`alphatab → melete → src → repo root`). `pyproject.toml:57-58` is `[tool.setuptools.packages.find]` / `where = ["src"]` with no `package-data`; no `MANIFEST.in` exists. `README.md:39-43` documents the install; `docs/repository-standards.md:47-50` states "daily use … melete is installed on the host with `uv tool install` and run directly." The only test of this path monkeypatches `RENDER_JS` to a known-missing path (`tests/alphatab/test_render.py:154`).
- **Context:** acknowledged extraction-bound debt (`CLAUDE.md`, `melete#82`) — but the README does not say so.
- **Found by:** Security & Code Quality, Coupling & Dependencies

### [F-24] A stale or hand-edited `session.json` produces a traceback on a user-facing read path
- **Category:** 34 — Inconsistent error conventions
- **Impact:** Medium
- **Explanation:** `_replay` validates the recorded family and instrument name, then passes recorded params verbatim to `pipeline.realize`. A bare family `ValueError` is not one of `_HANDLED`'s subclasses and escapes as a traceback — on a file the tool itself wrote a version ago.
- **Evidence:** `src/melete/cli.py:124-130,578`. Executed: a record carrying `hands: 2` with `inversion: "first"` raises `ValueError: arpeggios: the two-hand tap box is a root-position shape; inversion 'first' is deferred (spec §2, §12)`, and `isinstance(e, cli._HANDLED)` → `False`. `session.read` validates types, never param compatibility; no test replays a semantically-incompatible record.
- **Found by:** Security & Code Quality

### [F-25] The replay promise is scoped to parameters, not to output
- **Category:** 19 — Lack of idempotency
- **Impact:** Medium
- **Explanation:** `design.md` says `session.json` "is what makes `melete replay` reproduce a past sheet exactly", but the record holds only `{family, params}` plus seed, instrument name and weight inputs — no melete version, no schema version, no digest of the emitted artifact. Replay re-runs `pipeline.realize` against whatever code is installed now, and reads the instrument profile and tempo ranges from the *current* `config.toml`.
- **Evidence:** `src/melete/session.py:207-227` (`record`); `src/melete/cli.py:514-582`. With 68 commits in 7 days across `families/`, `layout.py`, `rhythm.py` and `emit.py` — including `ce23501` and `7248f1c` re-fingering the tapped triad third — a sheet replayed from last week is a different sheet, and no artifact can detect the divergence. `_REPLAY_INSTRUMENT` catches a renamed profile but not an edited tuning under the same name.
- **Found by:** Integration & Data

### [F-26] Renderer diagnostics are discarded on the success path, in two places
- **Category:** 21 — No observability plan
- **Impact:** Medium
- **Explanation:** `render.js` inspects alphaTab's diagnostic bags only inside the `catch` around `readScore()`, so a non-fatal diagnostic — exactly the class that produces "exit 0, valid ZIP, wrong notation" — is never emitted; and `render.py` discards `completed.stderr` entirely when `returncode == 0`. There is no logging framework anywhere in `src/`.
- **Evidence:** `melete-render/render.js:45-47`: `score = importer.readScore();` / `} catch (err) {` / `dumpDiagnostics(importer);` — the only call site. `src/melete/alphatab/render.py`: `_stderr(completed)` appears only at `:163` and `:177`, both inside error constructors. `grep -rn "^import logging\|^from logging" src/` → zero hits; all output is `print` (21 sites in `cli.py`) plus one stderr write.
- **Limit of verification:** whether alphaTab 1.8.4 populates the bags on a *successful* parse was not confirmed (the package is not installed on the analysis host). The code path is unambiguous regardless.
- **Found by:** Error Handling & Observability

### [F-27] No timeout on the renderer subprocess
- **Category:** 30 — Security as an afterthought (missing resilience control)
- **Impact:** Medium
- **Explanation:** `subprocess.run` is called with no `timeout=`, so a hung `node` produces no message at all, just a wedged CLI — against a documented promise of "Error carrying the renderer's own output". This is the one failure mode an otherwise exemplary module does not cover.
- **Evidence:** `src/melete/alphatab/render.py:111-116`. `docs/cli.md:183`. No test simulates a hanging `node`, though the `fake_node` fixture makes that easy.
- **Found by:** Integration & Data, Security & Code Quality

### [F-28] `session.json` is written non-atomically
- **Category:** 26 — Poor transactional boundaries
- **Impact:** Medium
- **Explanation:** A plain `write_text` with no temp-file-plus-`os.replace`. An interruption mid-write leaves a truncated document; because §13 correctly refuses to skip a corrupt history entry, every subsequent `generate` for any date within the horizon fails until the file is deleted by hand. The blast radius is disproportionate to the write, and this is the project's only durable state.
- **Evidence:** `src/melete/session.py:268-269`. Compounded by `session.history:490-497`, which raises `SessionError` rather than skipping.
- **Found by:** Integration & Data

### [F-29] The validity gate realizes every exercise and throws the result away; the accepted one is realized twice
- **Category:** 8 — Premature optimization (redundant computation) (+ 3)
- **Impact:** Medium
- **Explanation:** `selection._rejected` runs the full pipeline and discards the `Score`; `cli._score` then runs the identical `pipeline.realize` again for every accepted spec. This creates an unenforced invariant — the engraved sheet satisfies `max_notes`/`max_fret_span` only because the second realization is bit-identical to the first, and the one deliberate difference is never checked.
- **Evidence:** `src/melete/selection.py:487` and `src/melete/cli.py:325`; `_score` returns `replace(laid_out, tempo_range=active.pool[spec.family].tempo)` — the Score the gate validated is *not* the Score engraved. At the measured validity rates of 0.15–0.56 (`selection.py:159-172`), each printed exercise costs roughly 2–8 full realizations. Both callers discard the returned `LayoutPlan`.
- **Found by:** Coupling & Dependencies

### [F-30] `_shared.py`'s "decides nothing" claim is stale; five unrelated responsibilities
- **Category:** 29 — "Utility" dumping ground (+ 11 low cohesion)
- **Impact:** Medium
- **Explanation:** The module groups five unrelated concerns — parameter reading, list combinators, fretboard placement, a whole pipeline stage, and a one-line record constructor — with nothing in the placement group calling any of the others. Its docstring's central claim is contradicted by its largest function. It took 8 commits and +251 lines in the review week.
- **Evidence:** `src/melete/families/_shared.py:3-4`: "nothing here decides what an exercise *is* — that judgement stays in the family that makes it." Yet `derive_legato:411` decides hammer-on vs pull-off vs re-tap citing R9/R10/R12/R14, and `directed_by_cell:376` decides what descending means. Members: `Parameters:76`, `realizable:127`, `windowed:144`, `box:187-263`, `_two_hand_box:266`, `there_and_back:323`, `apex_doubled:334`, `apply_direction:357`, `directed_by_cell:376`, `derive_legato:411`, `layout_hints:484`.
- **Found by:** Structure & Boundaries

### [F-31] The pipeline reaches into an underscore-private families submodule for a whole stage
- **Category:** 13 — Inconsistent boundaries
- **Impact:** Medium
- **Explanation:** `pipeline` imports `derive_legato` from `families._shared` — a module whose leading underscore declares it private to the family layer, and whose package docstring explicitly disclaims it as "not a family" — and is its only caller. No family uses it. It is a pipeline stage that happens to be filed under `families/`.
- **Evidence:** `src/melete/pipeline.py:40` `from melete.families._shared import derive_legato`, called at `:72`. `grep -rn "derive_legato" src/` shows definition plus this one import/call.
- **Found by:** Structure & Boundaries, Coupling & Dependencies

### [F-32] Two incompatible mechanisms answer "is this axis sampled or determined?", consulted three lines apart
- **Category:** 13 — Inconsistent boundaries (+ 7 over-abstraction)
- **Impact:** Medium
- **Explanation:** `_CONDITIONAL_AXES` is selector-owned, hardcoded and keyed by `(family, axis)`; `Family.derive` is family-owned. Both are consulted in the same loop and neither knows the other exists. The "general" mechanism has exactly one entry, expressing one predicate shape for one family — and it silently encodes the ordering requirement of F-13.
- **Evidence:** `src/melete/selection.py:193-195` `_CONDITIONAL_AXES = {("intervals", "scale_type"): ("context", "diatonic")}`; consulted at `:432`, `derive` at `:434`. The `_CONDITIONAL_AXES` ordering dependency *is* documented (`selection.py:87`); the `derive` one is not.
- **Found by:** Structure & Boundaries, Coupling & Dependencies

### [F-33] `boxed_span` cannot distinguish "hand ran out" from "note not on the neck"
- **Category:** 20 — Weak error handling strategy
- **Impact:** Medium
- **Explanation:** `box` raises for two structurally different reasons — an unreachable pitch and a span violation — and only the second is `boxed_span`'s intended terminator. Its sibling `per_string`, thirty lines away in the same file, treats the first as a hard error with "The journey is never truncated to fit (spec §5)". The module holds both stances, and `boxed_span` silently takes the one `design.md` calls the failure mode.
- **Evidence:** `src/melete/families/journey.py:76-79`:
  ```python
  try:
      candidate = box(profile, [*used, pitch], strings, (base,), family, axes)
  except ValueError:
      break
  ```
  Contrast `journey.py:39-45`. The one-anchor misuse error (`_shared.py:246-251`) would also be swallowed here.
- **Found by:** Error Handling & Observability

### [F-34] Steering documents contradict the code in four specific, material ways
- **Category:** 24 — Inconsistent API contracts (documentation drift)
- **Impact:** Medium
- **Explanation:** Four concrete contradictions, each of which would mislead a reader forming a mental model before changing anything.
- **Evidence:** (a) `docs/design.md:90` "realize(): family -> fitter -> restamp" — it wires four stages, legato added between fitter and restamp (`pipeline.py:70-78`). (b) `docs/design.md:64` "Pure data." for `score.py` — see F-19. (c) `families/__init__.py:11-14,28-30` — see F-12. (d) `_shared.derive_legato`'s docstring at `:448` says "the barring pass has not grouped tuplets yet", attributing tuplet grouping to the barring pass; verified that `rhythm.py:247` is the only `Tuplet(` construction site in `src/` and `score.bar` never creates one.
- **Weighting:** `docs/design.md:7` self-declares "If something here disagrees with the spec, the spec is correct and this page is stale", which partly discounts (a) and (b). **(c) is not covered by that disclaimer** — it is in a source docstring, not design.md — and is the most material of the four, since it actively tells a contributor that adding a family costs nothing beyond `REGISTRY` when it in fact raises `KeyError` at config load.
- **Found by:** Coupling & Dependencies, Structure & Boundaries

### [F-35] Neither load-bearing boundary has any automated enforcement
- **Category:** 4 — High/unstable dependencies (unenforced constraint)
- **Impact:** Medium
- **Explanation:** `design.md` names two boundaries to understand "before changing anything" and `CLAUDE.md` restates the renderer one, but nothing mechanically prevents a violation. For a codebase that took 68 commits in seven days and an epic that "reaches into most of the pieces", the two rules most likely to be broken by accident are enforced by prose and code review alone.
- **Evidence:** `docs/design.md:264-278`. Verified: no `.importlinter`, no `setup.cfg`; `grep -rn "TID251|banned-api|importlinter" pyproject.toml vergil.toml` → zero hits; no test in `tests/` walks the module graph. `tests/test_package.py` guards the external dependency surface only.
- **Found by:** Coupling & Dependencies

### [F-36] `session.json` has no schema version, and `session.write`'s refusal guard is unreachable
- **Category:** 24 — Inconsistent API contracts (+ 31 dead code)
- **Impact:** Low today — **High as an input to #87**
- **Explanation:** The required-key tuple has no version key and there is no migration path, so an old record fails as "missing required key(s)" or is silently misinterpreted if a key's meaning changed. Separately, the same §13 rule is stated in two places with one copy inert.
- **Evidence:** `src/melete/session.py:81` `_REQUIRED = ("config_hash", "date", "exercises", "instrument", "seed", "weight_inputs")`. `session.write`'s `FileExistsError` at `:260-265` is unreachable: the only caller, `cli.py:290`, always passes `force=True`, documented as intentional at `cli.py:30-32`.
- **Found by:** Integration & Data

### [F-37] Rejected draws consume the shared session RNG, making the golden maximally brittle
- **Category:** 27 — Temporal coupling
- **Impact:** Low-Medium
- **Explanation:** One `Random(seed)` serves the whole session and every rejected attempt has already drawn from it, so the RNG position at slot N+1 depends on how many attempts slots 1..N burned. Any change shifting the valid/invalid boundary reshuffles the entire remainder of the session, leaving no way to distinguish "the fitter changed one exercise" from "the RNG stream moved".
- **Evidence:** `src/melete/selection.py:537-546` and `:605-621`. Deliberate per the `WeightInputs` docstring ("the rejected attempts consumed the generator too"); the brittleness is the unstated consequence.
- **Found by:** Integration & Data

### [F-38] `layout` emits bare strings that must be `rhythm.SUBDIVISIONS` keys, guarded by nothing
- **Category:** 23 — Dependency injection misuse (untyped cross-module contract)
- **Impact:** Low-Medium
- **Explanation:** `_SUBDIVISION_FOR_CELL`'s values are consumed as dict keys in another module that `layout` deliberately does not import. The relationship holds today but no test asserts it, and a violation surfaces as a bare `KeyError` inside `restamp` (see F-10).
- **Evidence:** `src/melete/layout.py:49-56`, used at `:209`, consumed at `src/melete/rhythm.py:164`. Verified: `grep -rn "_SUBDIVISION_FOR_CELL" tests/` → zero hits; the subset relation is `True` today but unasserted. `tests/test_rhythm.py:157` checks against a test-local copy.
- **Found by:** Structure & Boundaries, Coupling & Dependencies

### [F-39] `FamilyPool` does not enforce its own documented invariant
- **Category:** 10 — Feature envy / anemic domain model
- **Impact:** Low-Medium
- **Explanation:** `tapped_values` is documented to rely on "at most one of the two sets is non-empty", but the dataclass has no `__post_init__` and the invariant lives instead in `config._pool`'s family-name branch. Constructed any other way, `tapped_values` silently unions two semantically different identifier sets.
- **Evidence:** `src/melete/config.py:142-186` — fields at `:172-176`, `tapped_values` at `:178-186` with the invariant stated in its docstring and no validation anywhere. Enforced only at `config.py:603-607`.
- **Found by:** Structure & Boundaries

### [F-40] Four domain rules live in the CLI
- **Category:** 25 — Business logic in the UI
- **Impact:** Low-Medium
- **Explanation:** The CLI owns the tempo override (which `realize` deliberately declines), a second copy of the count-vs-shape rule, the reconstruction of the domain's axis ordering, and the recorded-instrument-must-match invariant — mostly because that is where the config happened to be in scope.
- **Evidence:** (a) `src/melete/cli.py:325` `replace(laid_out, tempo_range=active.pool[spec.family].tempo)`; consequence: any non-CLI caller of `realize`, including `tests/test_tapping_end_to_end.py:272`, silently gets the family default. (b) `cli._overridden:307-309` re-implements what `config._session` (`config.py:564-573`) already enforces, with a second copy of the message string (`_COUNT_AGAINST_SHAPE`, `cli.py:255-259`). (c) `cli.ordered:485-488`. (d) `cli._replay`'s `_REPLAY_INSTRUMENT` check.
- **Found by:** Error Handling & Observability

### [F-41] `apply_direction` is dead production code kept alive by its own tests
- **Category:** 31 — Dead code / unused dependencies
- **Impact:** Low
- **Explanation:** No call site in `src/` — the `direction` axis was retired in epic #72 — yet it sits at 100% branch coverage because its test suite is its only consumer, which is precisely the shape the coverage gate cannot detect. Its successor `directed_by_cell` has exactly one production caller, which hardcodes the direction string, so two of its three branches are also unreachable.
- **Evidence:** `grep -rn "apply_direction" src/` returns the definition (`_shared.py:357`) plus five prose docstring mentions and one comment (`intervals.py:162`) — no call. `grep -rn "directed_by_cell" src/` → the definition, one import, and one call: `journey.py:87` `return directed_by_cell(list(order), "up_down", cell)`. Kept alive by ~10 assertions at `tests/families/test_shared.py:129-174`.
- **Found by:** Structure & Boundaries, Coupling & Dependencies, Security & Code Quality

### [F-42] `layout_hints` is zero-value indirection
- **Category:** 7 — Over-abstraction
- **Impact:** Low
- **Explanation:** A pass-through with the same parameter names in the same order, no defaults and no validation. Its only effect is that six family modules import `_shared` instead of `layout`.
- **Evidence:** `src/melete/families/_shared.py:493`: `return LayoutHints(cell=cell, seam=seam, levers=levers)`. Verified: all six call sites pass all three keywords — `arpeggios.py:784,787`, `scales.py:364,469`, `intervals.py:447`, `chromatic.py:259`.
- **Found by:** Structure & Boundaries

### [F-43] The `selection → config` runtime edge buys two constants, one dead in production
- **Category:** 31 — Dead code / unused dependencies (+ 4)
- **Impact:** Low
- **Explanation:** `DEFAULT_HORIZON` is imported only to serve as `weight()`'s default argument, and no production caller ever takes that default. The edge is what makes `selection` transitively depend on `families.REGISTRY` and `families.arpeggio_tap_shapes` twice over.
- **Evidence:** `src/melete/selection.py:107`; `:247` `def weight(sessions_since, horizon: int = DEFAULT_HORIZON)`. Verified: `grep -rn "weight(" src/` returns exactly one call site, `selection.py:375`, which passes `self.horizon` explicitly. Only `tests/test_selection.py:217` exercises the default.
- **Found by:** Coupling & Dependencies, Error Handling & Observability

### [F-44] "Which qualities are sevenths" has two owners that disagree, with no drift guard
- **Category:** 17 — No clear ownership of data
- **Impact:** Low
- **Explanation:** `arpeggios._is_triad` decides by chord arity while `SEVENTH_QUALITIES` is a hand-written 5-tuple. Three of `theory.CHORDS`' four-tone qualities are not members and fall through to one hand, and `config`'s error message reads as a claim about the chord rather than about the box.
- **Evidence:** Executed: `theory.CHORDS` holds twelve qualities of which eight have four tones; `SEVENTH_QUALITIES == ('maj7','min7','dom7','m7b5','dim7')`, so `min_maj7` (genuinely a seventh), `maj6` and `min6` are excluded. `config.py:658-661` reports `min_maj7` as "not a tap-eligible seventh quality". Verified: `grep -rn "SEVENTH_QUALITIES" tests/` → zero hits; nothing asserts the tuple is a subset of the four-tone qualities. This is the one registry edge with **no** drift guard.
- **Found by:** Integration & Data

### [F-45] A package-level import cycle tolerated by CPython's fromlist fallback
- **Category:** 5 — Circular dependencies
- **Impact:** Low
- **Explanation:** `families/__init__` eagerly imports all four family modules, and `intervals` imports back into the partially-initialized package. It resolves today only because CPython falls back to importing the submodule when the package lacks the attribute. The only cycle in the codebase; latent, not active.
- **Evidence:** `src/melete/families/__init__.py:42`; `src/melete/families/intervals.py:105` `from melete.families import journey`. Verified: importing `melete.families`, `melete.families.intervals`, `melete.families.journey`, `melete.families.arpeggios` and `melete.families.scales` each first, in separate processes, all succeed.
- **Found by:** Coupling & Dependencies

### [F-46] A caching policy is welded to the replay file format
- **Category:** 6 — Leaky abstractions
- **Impact:** Low
- **Explanation:** `_Slot.distances` is simultaneously a memoization cache and the `WeightInputs` record written to `session.json`, so a change to *when* distances are computed changes the on-disk artifact and therefore whether a past day replays.
- **Evidence:** `src/melete/selection.py:357-358`, docstring: "`distances` is therefore both the cache and the record `WeightInputs` carries". The dual role is explicit and intentional; the coupling cost is the unstated part.
- **Found by:** Coupling & Dependencies

### [F-47] `[tool.mypy] files = ["src", "tests"]` is dead configuration
- **Category:** 31 — Dead code / unused dependencies (inert configuration)
- **Impact:** Low
- **Explanation:** The pipeline invokes `mypy src/`, and the positional argument overrides `files`, so the test tree — larger than the source — is never strict-typechecked by mypy. `ty` does cover it, but is pinned at a pre-release (`>=0.0.1a1`).
- **Evidence:** `pyproject.toml:75-78` versus `.vergil/vrg-validate-20260818-195510.log:19` `Running (typecheck): mypy src/ --junit-xml quality-mypy.xml`. `docs/repository-standards.md:60-70` presents the mypy row without scope, and its "Do not prune this group" framing implies a parity that does not exist.
- **Found by:** Security & Code Quality

### [F-48] Comments assert a config migration is still pending that has already landed
- **Category:** 24 — Inconsistent API contracts (stale comment)
- **Impact:** Low
- **Explanation:** Two comments in `scales.py` say the retired geometry axes "may still arrive in `params` while the config migration (#72 Task E2) lands"; `config.py` states the opposite in the same repository. Stale prose in a module a contributor reads early.
- **Evidence:** `src/melete/families/scales.py:50-52` and `:374-375`. Contradicted by `src/melete/config.py:413-415`. Verified: `vrg-git log --grep="geometry axes"` → `37d3474 refactor(config): remove the geometry axes and migrate the config (#161) (#172)`.
- **Found by:** Security & Code Quality

### [F-49] `instrument.profile.name` is unvalidated free text; a newline splits the emitted `\subtitle`
- **Category:** 30 — Security as an afterthought (missing input validation)
- **Impact:** Low
- **Explanation:** `config._string` accepts any `str` and `InstrumentProfile.__post_init__` validates tuning, `fret_count` and `position_span` but never `name`. A newline flows into the emitted alphaTex, producing a malformed directive from an entirely legal configuration.
- **Evidence:** `src/melete/config.py:237-240`; `src/melete/instrument.py:86-110`. Executed: `emit._quoted("line1\nline2")` → `'"line1\nline2"'`, a quoted string spanning two physical lines. Empty names and tabs likewise accepted. **Not injection** — the same test confirms `_quoted` correctly neutralizes a forged `\title "pwned"` (see S-13) — but malformed output with no test and no validation.
- **Found by:** Security & Code Quality

### [F-50] The tapped-scale × pattern cross-product is reachable from a legal config and entirely untested
- **Category:** 32 — Missing or inadequate test coverage for critical paths
- **Impact:** Low
- **Explanation:** `scales._derived` pins only `hands` and `traversal`, leaving `pattern` freely sampled, yet every tapped-scale fixture hardcodes `"pattern": "straight"` — while tapped *arpeggio* tests parametrize over four patterns at two layers.
- **Evidence:** `tests/families/test_scales.py:502-514` and `tests/test_pipeline.py:359-364` both hardcode `"pattern": "straight"`; contrast `tests/families/test_arpeggios_tapping.py:272-277` and `tests/test_pipeline.py:178,309`.
- **Executed (bass6, ionian, 3nps, hands=2):** `straight` 36 notes, `thirds` 64, `fourths` 60, `groups_of_3` **96** (exactly `DEFAULT_MAX_NOTES`), `numeric_1235` **112**, `groups_of_4` **120**. **No correctness defect found** — all six realize, stay palindromic, return to the low root, use both hands, plucked-count 0, no cross-string slurs. But the behaviour is unpinned, and the last two are silently rejected by the note-count gate, burning retry budget.
- **Found by:** Security & Code Quality

### [F-51] `realizable` is a `Parameters` method living outside `Parameters`
- **Category:** 10 — Feature envy / anemic domain model
- **Impact:** Low
- **Explanation:** A free function that touches only `read.identifier(axis)` and `read.family`, forcing three families to import two names where one would do.
- **Evidence:** `src/melete/families/_shared.py:127-141`.
- **Found by:** Structure & Boundaries

---

## Epic #87 (Graded exercise ladders) — Where the planned layer lands

This section is diagnosis of the *current* structure's readiness, not a design proposal. Every
specialist was asked the same forward-looking question and four of five independently reached the
same conclusion: **the "selection-time concept only" containment claim does not hold against the
real dependency structure.**

**1. The identity/deviation distinction already exists — three times, incompatibly.** #87 introduces
`IDENTITY` (fixed per ladder) versus `DEVIATIONS` (each with a *plain* value). The question "is this
axis sampled, or fixed by something else?" is already answered by three mechanisms that cannot
express one another: `Family.derive` (family-owned, ordering-dependent — F-13), `selection._CONDITIONAL_AXES`
(selector-owned, hardcoded `(family, axis) → (axis, value)`, one entry — F-32), and
`config.FamilyPool.tapped_*` (config-owned, branched on family-name string literals — F-17). Adding
`IDENTITY`/`PLAIN` as a fourth without collapsing these means "why was this axis not drawn?" has
four possible answers across three layers. This is the single strongest structural argument for
reviewing before building.

**2. The containment claim contradicts its own precedent.** `hands` was framed exactly as #87 frames
itself — a derived selection-time axis. It nonetheless landed as routing inside two families'
`generate` bodies, a new `Note` field, a new pipeline stage, and new emitter tokens: 11 of 24 source
modules, +1,627/−96. #87's `TIERS` ("which deviation is harder") and `PLAIN` ("what this axis looks
like with the technique removed") are both musical judgements a family must realize, and a rung whose
`PLAIN` value the family cannot lay out is a `ValueError` from `generate` — the families are in the
loop.

**3. The `deviation` pseudo-axis has no home in the axis machinery, at either end.** `config._Axis.universe`
is `Callable[[InstrumentProfile], tuple[AxisValue, ...]]` — parameterized by profile, **not by
family** — and `_ROOT`, `_PATTERN`, `_SCALE_TYPE` are shared singletons reused across `_AXES_BY_FAMILY`
entries. An axis whose candidate set is *this family's own axis names* cannot be one shared `_Axis`.
Symmetrically, `vocabulary.AXES` is a flat `axis → {identifier: display}` map with no per-family
dimension. So `deviation` either forces a structural change to both, or becomes the **second**
unregistered axis after `hands` — inheriting F-06 wholesale: invisible to `melete vocabulary` and
`melete families`, unable to use `Parameters`' error contract, and mis-ordered by `cli.ordered`.

**4. Set-level recency is a different accounting model, not a parameterization.** `_Slot.distances`
is keyed by axis name alone and `_coverage_value` reads `spec.params.get(axis)` as a single value. A
`deviation` value that is a *set* would pass through `axis_key`, which hyphen-joins tuples — counting
the combination `"pattern-inversion"` as one opaque value and never crediting `pattern` or `inversion`
individually.

**5. The validity gate does not compose with rungs — but the arithmetic is less alarming than it
first appears.** Two specialists projected catastrophic ladder rejection rates from the documented
per-family single-draw validity figures (`intervals` 0.152, `scales` 0.299, `chromatic` 0.437,
`arpeggios` 0.560), reasoning that an all-or-nothing 4–5 rung ladder compounds toward *p*ⁿ. **The
verifier tested this and the premise is weaker than stated:** `MAX_ATTEMPTS` is a *per-slot* budget
(`_fill` loops it fresh per slot), which is the same unit those rates were measured in, and a
re-measurement of a tapped-scales pool post-epic returned **0.751** validity. Rung validity is also
positively correlated, since rungs share an identity. The honest position is that the compounding
direction is real but the magnitude is unknown — which is exactly why #87's own plan puts a
measurement task first. That decision is well-founded and should not be skipped. Two secondary
effects the plan should account for: cost per attempt multiplies by the rung count, and
`_over_constrained` reports the *modal* rejection reason across attempts, so an over-constrained
ladder would name a failure without saying which rung produced it.

**6. `session._fingerprint` will silently swallow `[ladder]` and `[challenge.*]` too.** It already
omits the two tapping keys (F-02) and is written as an explicit literal dict rather than derived from
`Config`'s fields. Two more config sections that move the draw means two more chances for the same
silent failure, in the one place that decides both the seed and whether replay warns the user.

**7. The clean reset of `session.json` is cheaper in data and dearer in code than stated.** The
justification — "the logs live in gitignored `build/`" — is correct about data: no `session.json`
exists outside `build/` (no fixture, no golden, no example). But the **schema is asserted in Python**
across at least four test modules (`tests/test_session.py` 537 LOC, `test_cli_generate.py` 728,
`test_cli_query.py`, `test_selection.py`). Two structural facts make it easier than it looks (no
version key to remove, no v1 reader to keep, so nothing has to branch) and one makes it harder: the
acceptance goldens are drawn live from `examples/config.toml` through the real selector, so new
config sections invalidate all nine — and those goldens are the only end-to-end reproducibility
guarantee the project has. Losing the safety net during the reset removes it at the moment it is most
needed. The reset is also the natural moment to add the schema version whose absence is F-36.

**8. Observability goes from thin to absent.** Today, when a sheet is musically wrong, the available
evidence is `session.json` (axes and recency distances), `--dry-run` (axes only), and "render it and
look". The fitter's trace is already discarded (F-15); the `derive` hook, `derive_legato`, and the
R1–R14 fingering choices leave no record at all. #87 adds rung ordering, an identity/deviation split,
and tier assignment — three more decisions per exercise, times 25 exercises per day instead of 5.
The diagnostic question changes from "which of five is wrong and why" to "which of 25, at which rung,
under which deviation", and the available evidence does not scale with it. F-01 is the proof that
this already bites: a real, reachable, wrong-meter defect that the system computes a perfect
explanation for and then throws away.

**9. One mechanical interaction worth flagging.** `TIERS` introducing new pattern windows collides
with F-08: `cell = len(window)` is currently ≤ 4 by accident of the four hand-written window tables,
and `_SUBDIVISION_FOR_CELL` tops out at 6. A tier declaring a 7- or 8-note window produces the
swallowed "cell 7 has no subdivision mapping" and surfaces as "the pattern needs a new lever declared
by its family" — advice that sends the fix to the wrong module.

**Scale check (measured, not projected).** Nothing in the emit/session/render path scales worse than
linearly and no resource ceiling is approached: `build/sessions/2026-08-18/session.json` is 6.2 KB
for 5 exercises and `practice.gp` is 11 KB, so 25 exercises is roughly 31 KB of log and 55 KB of
`.gp`. Two things change character rather than magnitude: `--split` becomes 26 sequential Node
launches with no timeout on any of them (F-27), and one book becomes ~350 bars in a single alphaTex
track — a layout-quality question, untested at that scale.

---

## Coverage Checklist

### Flaw/Risk Types 1–34

| # | Type | Status | Finding |
|---|------|--------|---------|
| 1 | Global mutable state | Not observed | — (inverse is S-06) |
| 2 | God object | Not observed | — (hypothesis tested on `arpeggios.py` and rejected: 236 code lines of 788) |
| 3 | Tight coupling | Observed | F-12, F-29 |
| 4 | High/unstable dependencies | Observed | F-17, F-35, F-43 |
| 5 | Circular dependencies | Observed | F-45 (latent) |
| 6 | Leaky abstractions | Observed | F-01, F-19, F-46 |
| 7 | Over-abstraction | Observed | F-42, F-32 |
| 8 | Premature optimization | Observed | F-29 |
| 9 | Shotgun surgery | Observed | F-06 |
| 10 | Feature envy / anemic domain model | Observed | F-39, F-51 |
| 11 | Low cohesion | Observed | F-30, F-20 |
| 12 | Hidden side effects | Observed | F-18 |
| 13 | Inconsistent boundaries | Observed | F-17, F-19, F-31, F-32 |
| 14 | Distributed monolith | Not applicable | Single-process CLI; no service topology |
| 15 | Chatty service calls | Not applicable | No network calls anywhere in `src/` |
| 16 | Synchronous-only integration | Not applicable | Foreground command producing one file before exit; synchronous is correct |
| 17 | No clear ownership of data | Observed | F-06, F-15, F-44 |
| 18 | Shared database across services | Not applicable | No database; only `sessions/` on the local filesystem, one writer |
| 19 | Lack of idempotency | Observed | F-02, F-16, F-25 |
| 20 | Weak error handling strategy | Observed | F-04, F-08, F-33 |
| 21 | No observability plan | Observed | F-01, F-15, F-26 |
| 22 | Configuration sprawl | Observed | F-03 |
| 23 | Dependency injection misuse | Observed | F-38, F-17 |
| 24 | Inconsistent API contracts | Observed | F-07, F-34, F-36, F-48 |
| 25 | Business logic in the UI | Observed | F-40 |
| 26 | Poor transactional boundaries | Observed | F-05, F-28 |
| 27 | Temporal coupling | Observed | F-01, F-13, F-14, F-37 |
| 28 | Magic numbers/strings everywhere | Not observed | — (inverse is S-14; no bare unexplained literal in any decision path read) |
| 29 | "Utility" dumping ground | Observed | F-30 |
| 30 | Security as an afterthought | Observed | F-21, F-27, F-49 |
| 31 | Dead code / unused dependencies | Observed | F-41, F-22, F-43, F-47 |
| 32 | Missing/inadequate test coverage for critical paths | Observed | F-11, F-23, F-50 |
| 33 | Hard-coded credentials or secrets in source | Not observed | Case-insensitive scan of `src/`, `melete-render/`, `tests/`, `examples/`, `*.toml`, `*.md` → zero hits; `ops.yml` passes secrets correctly; workflow permissions scoped per job |
| 34 | Inconsistent error/logging conventions | Observed | F-04, F-09, F-10, F-24 |

### Strength Categories S1–S14

| # | Category | Status | Finding |
|---|----------|--------|---------|
| S1 | Clear modular boundaries | Observed | S-01, S-11 |
| S2 | High cohesion | Observed | S-22 |
| S3 | Loose coupling | Observed | S-02 |
| S4 | Dependency direction is stable | Observed | S-02 |
| S5 | Dependency management hygiene | Observed | S-14, S-04 |
| S6 | Consistent API contracts | Observed | S-05, S-16, S-20 |
| S7 | Robust error handling | Observed | S-03, S-16 |
| S8 | Observability present | Observed | S-09, S-10, S-19 |
| S9 | Configuration discipline | Observed | S-07, S-08 |
| S10 | Security built-in | Observed | S-13, S-21, S-03 |
| S11 | Testability & coverage | Observed | S-04, S-10 |
| S12 | Resilience patterns | Observed | S-03, S-12, S-15 |
| S13 | Domain modeling strength | Observed | S-17 |
| S14 | Simple, pragmatic abstractions | Observed | S-06, S-18 |

---

## Hotspots

**1. The axis-decision machinery — `src/melete/selection.py`, `src/melete/families/__init__.py`, `src/melete/config.py`**
Three incompatible mechanisms answer one question (F-32, F-17), an unguarded tuple-ordering contract
underpins two of them (F-13), one live axis exists in no registry (F-06), the family concept is three
parallel lists (F-12), and pool completeness is validated at draw time (F-03). This is precisely where
epic #87's four new per-family declarations and the `deviation` pseudo-axis must land.

**2. The tapped layout path — `src/melete/families/arpeggios.py`, `src/melete/families/_shared.py`, `src/melete/layout.py`**
Home of the one confirmed user-visible defect (F-01: 2/4 × 7 bars on every two-hand triad, reachable
from a minimal legal config), the swallowed fitter diagnostics that hide its cause (F-08), the
discarded trace that would have explained it (F-15), the comment-held dispatch invariant (F-20), and
the module whose cohesion has eroded furthest (F-30, with dead code F-41 and a no-op wrapper F-42
still inside it).

**3. Durable state — `src/melete/session.py` and `cli._generate`**
The config-hash omission that silently breaks the seed contract (F-02), `--force` destroying a
completed record before a render that can fail (F-05), a non-atomic write whose corruption blocks
every subsequent run (F-28), no schema version (F-36), and back-fill weighting against the future
(F-16). #87 plans a clean reset of exactly this file.

---

## Next Questions

1. F-01 puts every two-hand triad on `bass5`/`bass6` into 2/4 × 7 bars from a minimal legal config, and `examples/config.toml` avoids it only by having no triad in its arpeggio pool — has a generated sheet containing a two-hand triad ever been rendered and looked at by a player?
2. `hands` established the precedent of a derived axis that no registry knows about (F-06), and #87's `deviation` pseudo-axis has the same shape — should the registry gain a notion of derived axes before that second one is minted, or is the carve-out at `tests/test_selection.py:308` intended to be permanent?
3. Three mechanisms currently answer "is this axis sampled or determined?" (F-32, F-17, `Family.derive`) — is there a reading of the domain in which they are genuinely one concept, or do they encode distinctions that a single mechanism would flatten incorrectly?
4. `pipeline.realize`'s four stages are correct only in one order and nothing but the single call site enforces it (F-14) — is the ordering an intrinsic property of the domain, or an artifact of the sequence in which the stages were added?
5. Given that 100% branch coverage did not detect dead code (F-41), the untested tapped-scale cross-product (F-50), or the tapping-free acceptance corpus (F-11), what would a coverage signal have to measure to be informative about whether tomorrow's sheet is right?

---

## Analysis Metadata

- **Agents dispatched:** 5 specialists in parallel — Structure & Boundaries (types 1, 2, 9, 10, 11, 13, 29; S1, S2, S13, S14); Coupling & Dependencies (3, 4, 5, 6, 7, 8, 23, 27; S3, S4, S5); Integration & Data (14–19, 24, 26; S6, S12); Error Handling & Observability (12, 20, 21, 22, 25, 28, 34; S7, S8, S9); Security & Code Quality (30, 31, 32, 33; S10, S11) — followed by 1 verifier.
- **Scope:** 24 source modules (8,768 LOC) + 33 test modules (12,627 LOC) + `melete-render/`, `docs/`, `examples/`, CI and packaging config.
- **Raw findings:** 112 (40 strengths, 72 flaws)
- **Verified findings:** 73 (22 strengths, 51 flaws)
- **Filtered out:** 39 — of which **37 were merges** of the same defect reported by two to four specialists, and **2 were genuine drops**: a convergence-map claim that `MAX_ATTEMPTS` does not survive ladder composition (premise tested and found weaker than stated — the budget is per-slot, the same unit the rates were measured in), and one specialist's overstated framing that "the only independent oracle declines to check content" (corrected downward and merged into F-11, since `test_tapping_end_to_end.py` does assert real `.gp` content at eight sites).
- **By impact:** flaws — 6 high, 30 medium, 15 low; strengths — 13 high, 9 medium.
- **Verification method:** a working Linux CPython 3.14.7 was located and used to settle claims by execution. Because melete declares zero runtime dependencies, `PYTHONPATH=src` runs the whole package. All scripts were written to a scratchpad; **no repository file was created, modified or deleted** during analysis. Ten claims were confirmed empirically, including F-01 (trace captured verbatim, reachability swept across 3 profiles × 9 qualities × 6 patterns × 32 roots × 2 hand counts), F-02 (identical digests and seeds produced), F-03 (11 of 40 seeds succeed on one config file), and F-08 (the misleading message reproduced).
- **Steering files consulted:** `CLAUDE.md`, `~/.claude/CLAUDE.md`, `docs/design.md`, `docs/cli.md`, `docs/configuration.md`, `docs/repository-standards.md`, `docs/reports/tapping-fingering-rules.md`, `pyproject.toml`, `vergil.toml`, `.github/workflows/`
- **Cleared leads (investigated, not defects):** `src/melete/lilypond/` and `tests/lilypond/` contain only untracked `__pycache__` — `vrg-git ls-files` returns nothing for both, so `design.md`'s LilyPond-removal claim is accurate for tracked source; `build/` residue is gitignored and documented as scratch; no hard-coded credentials; no unused dependencies beyond F-41.
