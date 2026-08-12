# Melete Repository Standards

Reference for anyone — human or agent — about to contribute to this
repository. It records the configuration that governs the work: the
repository profile, the toolchain, the checks that must pass, and the
places where melete deliberately departs from the Vergil default.

Where another document is authoritative, this page links to it rather
than restating it. The design specification lives in
[`mnemosys-project/.github`](https://github.com/mnemosys-project/.github)
and always wins over anything written here.

## Table of Contents

- [Repository profile](#repository-profile)
- [Development toolchain](#development-toolchain)
- [Validation](#validation)
- [Repository conventions](#repository-conventions)
- [Post-merge async workflows](#post-merge-async-workflows)
- [External tooling dependencies](#external-tooling-dependencies)
- [CI gates](#ci-gates)
- [Commit and PR scripts](#commit-and-pr-scripts)
- [Local deviations](#local-deviations)

## Repository profile

From `vergil.toml`:

| Key                 | Value             |
| ------------------- | ----------------- |
| `repository-type`   | `application`     |
| `versioning-scheme` | `semver`          |
| `branching-model`   | `library-release` |
| `release-model`     | `tagged-release`  |
| `primary-language`  | `python`          |

`branching-model = "library-release"` was chosen over
`application-promotion` even though melete is an application. Melete has
no deployment pipeline and no environments to promote through, so the
promotion model would describe machinery that does not exist. The choice
is descriptive rather than functional: it names how the branches behave,
not how a release is shipped.

In practice this means `feature/*` branches merge into `develop`,
`develop` merges into `main`, and a tagged release is cut from `main`.

## Development toolchain

Python 3.14, managed by `uv`. Development happens inside
`vrg-container-run` against the `dev-python` container image; daily use
of the tool does not — melete is installed on the host with `uv tool
install` and run directly.

The `dev` dependency group in `pyproject.toml` is **a contract with
`vrg-validate`, not a preference**. Each stage shells out to a fixed set
of executables, and a missing one fails the stage with a bare
`FileNotFoundError` rather than a diagnosis:

| Tool           | Stage that requires it |
| -------------- | ---------------------- |
| `ruff`         | `lint`                 |
| `mypy`         | `typecheck`            |
| `ty`           | `typecheck`            |
| `pytest`       | `test`                 |
| `pytest-cov`   | `test`                 |
| `pip-audit`    | `audit`                |
| `pip-licenses` | `audit`                |

Typecheck runs **both `ty` and `mypy`**; audit runs **both `pip-audit`
and `pip-licenses`**. Dropping either member of either pair does not
relax a check — it breaks the pipeline. Do not prune this group to the
tools you personally use.

`uv.lock` is committed and the audit stage runs `uv sync --check
--frozen` and `uv lock --check`, so a dependency edit that is not
accompanied by a regenerated lockfile fails CI.

## Validation

```bash
vrg-container-run -- vrg-validate
```

This is the **only** validation command. Do not run individual linters,
formatters, or test invocations outside it. If a tool is not invoked by
`vrg-validate`, it is not part of the validation pipeline.

Stages run in order and the first failure stops the run:

`common` → `install` → `lint` → `typecheck` → `test` → `audit`

`common` is language-independent: repository-profile validation,
markdownlint, shellcheck, and yamllint over the files each discovers.

### The pipeline enforces 100% test coverage, including branches

The `test` stage runs pytest with `--cov=src --cov-branch
--cov-fail-under=100`. This is not a target to work toward; it is a gate,
and it is the single constraint that shapes how every module in this
repository is written. Practical consequences:

- Every branch of every conditional needs a test that takes it, not just
  a test that reaches the line.
- Defensive code paths that cannot be triggered from a test are a design
  problem, not a coverage problem. Either make the condition reachable or
  remove it.
- Lines legitimately outside the measurement are excluded through
  `[tool.coverage.report].exclude_lines` in `pyproject.toml`
  (`pragma: no cover`, `if TYPE_CHECKING:`, `if __name__ ==
  "__main__":`). Adding a new exclusion is a decision, not a
  convenience — argue for it in the PR.

The coverage threshold comes from the shared Vergil pipeline, not from
`pyproject.toml`, so it cannot be relaxed locally.

## Repository conventions

### Parallel agent worktrees

Multiple Claude Code agents work this repository in parallel through git
worktrees under `.worktrees/`, named `issue-<N>-<slug>` on branch
`feature/<N>-<slug>`. Sessions **always** start at the project root so
the memory path stays stable and shared, and the main worktree is
**read-only** — every change flows through a worktree on a feature
branch.

`CLAUDE.md` holds the local on-ramp, including the agent prompt
contract; the canonical specification is
[`vergil-tooling/docs/specs/worktree-convention.md`](https://github.com/vergil-project/vergil-tooling/blob/develop/docs/specs/worktree-convention.md).
Read those rather than a paraphrase here.

`.worktrees/` is gitignored.

### `build/` is the scratch directory

Working files that are not source — one-off scripts, rendered
experiments, intermediate output while debugging a layout — go in
`build/`. It is gitignored, so nothing there can be committed by
accident, and clearing it is always safe. Do not scatter scratch files
through `src/`, `tests/`, or the repository root.

Generated practice sheets land in `sessions/`, also gitignored, as do
the `vrg-validate` artifacts (`.coverage`, `coverage.xml`, `junit.xml`,
`licenses.json`, `pip-audit.json`), which every run regenerates.

### `examples/config.toml` is the worked configuration

`examples/config.toml` is the annotated reference configuration: a
complete, valid file exercising every section melete reads, with inline
comments tying each key back to the specification section that defines
it. Treat it as documentation with a compiler — when configuration
handling changes, update it in the same PR.

## Post-merge async workflows

Workflows triggered by a merge that must reach `conclusion: success`
before a PR is considered finished.

| Workflow  | Trigger        | What it does                          |
| --------- | -------------- | ------------------------------------- |
| `cd.yml`  | push to `main` | Tagged release via `cd-release@v2.1`  |

**A merge to `develop` has no post-merge gate.** `cd.yml` does fire on a
push to `develop`, but its only job is guarded by
`if: github.ref == 'refs/heads/main'`, so the run completes as `skipped`
within a second and carries no signal. There is nothing to await on a
feature-branch merge.

Two things that look like post-merge workflows are not:

- `epic-rollup.yml` triggers on `issues: [closed]`, not on a merge. It
  updates the parent epic's checklist and is unrelated to PR completion.
- `[publish].docs = false` in `vergil.toml` — this repository publishes
  no documentation site, so there is no docs build to wait on.

## External tooling dependencies

### alphaTab — a Node dependency baked into the image, not a Python package

**Melete has no runtime Python dependency.** The renderer's dependency
lives outside Python entirely: melete emits alphaTex, and the vendored
`melete-render/` Node tool renders it to a Guitar Pro `.gp` through
alphaTab. Node itself is in the container's base image; alphaTab is added
on top.

Where the dependency comes from:

| Context            | Source                                              |
| ------------------ | --------------------------------------------------- |
| Dev / CI container | `[container].build-command = "npm install -g @coderline/alphatab@1.8.4"` in `vergil.toml` |
| Host               | Node on `PATH`, plus `melete-render/`'s dependencies (`npm install` in that directory) |

The container bakes alphaTab in at **image-build time** rather than
installing it per run. The install must land **outside `/workspace`** — the
runtime bind-mount masks anything under it — so it is a *global* npm
install, and the tooling exposes the npm global root on `NODE_PATH`, which
CommonJS `require()` honours (`melete-render` is CommonJS for exactly this
reason). The version is pinned in `vergil.toml` so a bump is a tracked
config edit, and `build-cache-files` declares
`melete-render/package-lock.json` so a resolved-tree change rebuilds the
image.

On the **host**, alphaTab is a prerequisite the user must satisfy before
melete renders; because the prerequisite is invisible until something
fails, a missing Node produces an explicit message naming the resolution,
never a stack trace.

`src/melete/alphatab/render.py` is the only module that knows a renderer
binary exists. That boundary is deliberate: a change to how the renderer is
invoked touches exactly that one module.

One open thread a contributor should know about before investing here:

- [`melete#82`](https://github.com/mnemosys-project/melete/issues/82) —
  `melete-render/` is a vendored, acknowledged extraction-bound technical
  debt. It is deliberately a "dumb" alphaTex → `.gp` renderer with no
  musical knowledge; read #82 before building it out in place.

### Everything else comes from the container

`markdownlint`, `shellcheck`, `yamllint`, `uv`, and the Python
toolchain are supplied by the `dev-python` image. They are not host
prerequisites, which is why `vrg-container-run` is part of the
validation command rather than an optional wrapper.

## CI gates

Required status checks on `develop`, **read from the branch's actual
required contexts** (`vrg-gh pr checks <n> --required`) rather than
inferred from the workflow file:

- `quality / common`
- `quality / lint / 3.14`
- `quality / typecheck / 3.14`
- `test / unit / 3.14`
- `audit / dependencies / 3.14`
- `security / codeql`
- `security / semgrep`
- `security / trivy`
- `version / version-bump`
- `CodeQL`
- `Semgrep OSS`
- `Trivy`

All twelve come from `.github/workflows/ci.yml`, which composes the
shared `vergil-actions` reusable workflows at `@v2.1`. The `matrix` and
`evidence` jobs each of those workflows also emits (`quality / matrix`,
`test / evidence`, and so on) run on every PR but are **not** required
contexts.

**Verify this list against the ruleset rather than trusting a tool that
reports compliance.** `vrg-github-repo-config audit` does not evaluate
rulesets; it reported this repository compliant throughout the bootstrap
epic while the ruleset required a status context CI could not emit,
which left every PR unmergeable with all checks green. That is the defect
behind the `integration-tests` deviation below.

Local hard gates (installed git hooks, enforced through `vrg-commit`):

- Branch naming — branching-model-aware prefix validation.
- Commit message lint — Conventional Commits required.

Agent session gate (`.claude/hooks/guard.sh`, a `PreToolUse` hook wired
in `.claude/settings.json`): raw `git` and `gh` are denied. Use
`vrg-git` and `vrg-gh`. The shim hard-denies even when `vergil-tooling`
is absent, so the policy cannot be bypassed by an incomplete
environment.

## Commit and PR scripts

Agents **must** use the wrapper scripts. Do not construct commit
messages or PR bodies by hand — the wrappers resolve the correct
`Co-Authored-By` identity from `vergil.toml`, and the git hooks validate
what they produce.

### Committing

```bash
vrg-commit \
  --type TYPE --scope SCOPE --message MESSAGE \
  [--body BODY] [--allow-empty]
```

- `--type` (required):
  `feat|fix|docs|style|refactor|test|chore|ci|build|revert`
- `--scope` (required): conventional commit scope
- `--message` (required): commit description
- `--body` (optional): detailed body — the *why*, including any
  `Refs: #N` trailer
- `--allow-empty` (optional): commit with nothing staged, e.g. to
  re-trigger CI

### Reporting a branch ready

Agents do not open, merge, or finalize pull requests. Work finishes by
pushing the branch and recording the PR metadata for the human submit
step:

```bash
vrg-git push -u origin feature/<N>-<slug>
vrg-pr-workflow report-ready \
  --issue N --title TEXT --summary TEXT --notes TEXT \
  [--linkage KEYWORD]
```

`report-ready` freezes the branch. Further commits require an explicit
`vrg-pr-workflow unfreeze`; `vrg-pr-workflow status` prints the current
state.

The human then runs `vrg-submit-pr`, which reads the recorded metadata,
detects the target branch and merge strategy, and opens the PR.

## Local deviations

### `integration-tests = false` — CI's integration job, not the tests

`[ci].integration-tests` is `false` in `vergil.toml`. **This is not a
reduction in testing.** The `@pytest.mark.integration` tests — the
renderer integration test and the CLI end-to-end smoke tests — are never
deselected: `addopts` is only `--strict-markers`, so they execute in the
ordinary pytest run and are already covered in CI by `test / unit /
3.14`, against the alphaTab renderer the container installs.

What the flag switches off is CI's *claim* to run a suite it has no job
to run. Setting it `true` adds `test / integration / 3.14` to the branch
ruleset's required checks, but the shared `ci-test.yml@v2.1` emits only
`unit`. Requiring a context that no job ever reports blocks every PR
while all checks are green — the unmergeable state that
[`melete#23`](https://github.com/mnemosys-project/melete/issues/23)
fixed by setting this false, and that
[`melete#52`](https://github.com/mnemosys-project/melete/issues/52) and
[`melete#64`](https://github.com/mnemosys-project/melete/issues/64)
revisited.

Two of the three preconditions for flipping it back are met: the
container carries the renderer
([`vergil-tooling#2718`](https://github.com/vergil-project/vergil-tooling/issues/2718)),
and
[`vergil-tooling#2720`](https://github.com/vergil-project/vergil-tooling/issues/2720)
added a parity guard that now fails loudly on the mismatch. The emitting
job is still owed by the open
[`vergil-tooling#2721`](https://github.com/vergil-project/vergil-tooling/issues/2721),
which records the underlying gap: integration tests are not a
first-class Vergil feature. **Flip this only once #2721 lands.**

### An `application` on the `library-release` branching model

See [Repository profile](#repository-profile). Melete has no deployment
pipeline and no environments, so `application-promotion` would describe
machinery that does not exist.

### No runtime Python dependencies

`[project].dependencies` is empty and stays empty. The renderer's
dependency is Node with alphaTab, which lives outside Python entirely —
there is no package relationship to it in `pyproject.toml`. See
[External tooling dependencies](#external-tooling-dependencies).

### No documentation site

`[publish].docs = false`. Documentation lives in `docs/` in this
repository and in the epic record in `mnemosys-project/.github`; nothing
is deployed. Note the practical consequence: `vrg-validate`'s
markdownlint step discovers `docs/site/**/*.md` and `README.md`, so
files under `docs/` are not linted here. Match the existing style —
80-column prose, a table of contents, ATX headings — by hand.
