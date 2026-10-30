# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## Overview

Melete is a practice exercise generator: it builds parameterized bass
exercises and engraves them as standard notation and tablature, one Guitar Pro
`.gp` file per day. Python, no runtime Python dependencies; rendering goes
through alphaTab via a vendored Node tool. Start with
[`docs/design.md`](docs/design.md); repository conventions, toolchain and
local deviations are in
[`docs/repository-standards.md`](docs/repository-standards.md).

## The renderer boundary

Melete engraves through alphaTab: the emitter writes alphaTex, and the vendored
`melete-render/` Node tool renders that to a Guitar Pro `.gp`. Only
`src/melete/alphatab/` (`emit.py`, `render.py`), `melete-render/`,
`tests/alphatab/` (including the `golden/` fixtures) and the alphaTab install
in `vergil.toml`'s `[container].build-command` are renderer-specific; every
other module is renderer-agnostic and must stay that way. `score.py` is the
seam that keeps it so — families produce a `Score`, the emitter consumes one,
and neither imports the other. Do not let alphaTab knowledge leak past it.

`melete-render/` is a vendored Node tool and acknowledged extraction-bound tech
debt (`melete#82`); it lives inside this boundary until it is extracted.

See [`docs/design.md`](docs/design.md#the-renderer-boundary) and epic
`mnemosys-project/.github#46`.

## Working constraints

- **Generated output stays in `build/`.** Running melete writes `.gp`, `.atex`
  and `session.json` to `./sessions/<date>/` under the working directory. In
  development, run it from the gitignored `build/` directory, never from the
  repo root, a sibling repository or the VM scratchpad. Scratch files of any
  kind go in `build/` too.
- **`examples/config.toml` is the worked configuration.** When configuration
  handling changes, update it in the same PR.

<!-- vergil:template:claude-md:begin -->
## Memory

Never write, edit or delete memory files without explicit human approval.
Propose the entry and where it belongs first, then wait for the decision.

## Worktrees

- Sessions always start at the project root, never inside `.worktrees/`.
- One worktree per issue: `.worktrees/issue-<N>-<slug>/` on branch
  `feature/<N>-<slug>`. Remove it once its branch lands.
- The main worktree is read-only, bar ignored `build/` scratch; every edit goes through a worktree.
- Read, Edit and Write use the worktree's absolute path. Bash commands `cd`
  into the worktree first or use absolute paths.
- The full convention: <https://github.com/vergil-project/vergil-tooling/blob/develop/docs/specs/worktree-convention.md>.
- Brief each parallel sub-agent with its [Agent prompt contract](https://github.com/vergil-project/vergil-tooling/blob/develop/docs/specs/worktree-convention.md#agent-prompt-contract).

## Git and GitHub

Use `vrg-git` and `vrg-gh` only; the hook guard blocks raw `git` and `gh`. If a
command is not available through the wrappers, explain why and ask the human to
run it with `! <command>` in the prompt.

## Validation

`vrg-container-run -- vrg-validate` is the only validation command. Don't run
linters, formatters or tests outside it; a tool it doesn't invoke is not part
of the pipeline.

## PR handoff

- Agents never run `vrg-submit-pr`. Submitting, merging and finalizing a PR are
  human actions.
- Hand off with `vrg-pr-workflow report-ready --issue <N> --title --summary
  --notes`. It pushes the branch itself. Leave `--linkage` at its default (`Ref`).
- A delta touching `.github/workflows/**` makes GitHub refuse the agent push.
  That is expected: report-ready records the state anyway and the human's
  `vrg-submit-pr` pushes the branch.
- After report-ready the branch is frozen: no new commits and no push that
  advances it; more work is a new follow-up issue. Re-running report-ready to
  fix the prose is allowed. `vrg-pr-workflow unfreeze` is the only way to lift it.
- The report-ready title, summary and notes are public (the relay ref is
  world-readable): never put secrets in them.

## Local settings

`.claude/settings.local.json` must stay absent or exactly `{}`; the agent tools
refuse otherwise. See the [ownership model](https://github.com/vergil-project/vergil-tooling/blob/develop/docs/site/docs/guides/claude-config-ownership.md).

## Engineering principles

- Correctness over cost over speed. Never ship known-broken code with a
  follow-up fix; if something is wrong, fix it now.
- No silent failures: no swallowed exceptions, no `except: return ""`, no
  fallbacks that hide errors. A failure hidden in code becomes a hallucination
  at the AI layer.

## paad

paad usage policy and deviations:
<https://github.com/vergil-project/vergil-claude-plugin/blob/develop/docs/paad-policy.md>.
<!-- vergil:template:claude-md:end -->
